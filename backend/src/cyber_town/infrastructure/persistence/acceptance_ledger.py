"""Bounded, cross-process SQLite ledger for explicitly authorized model acceptance."""

from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4

from cyber_town.config import DEEPSEEK_MODEL

_AUTHORIZATION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_BUSY_TIMEOUT_MILLISECONDS = 2_000
_TOTAL_MAX_CALLS = 12
_TOTAL_MAX_MICRO_USD = 50_000


class AcceptanceLedgerError(RuntimeError):
    """Acceptance evidence is unavailable or has unresolved provider outcomes."""


class AcceptanceBudgetError(AcceptanceLedgerError):
    """A requested real-model call would exceed its independently approved budget."""


class AcceptanceStep(StrEnum):
    """The only task steps eligible for separately authorized real-model calls."""

    STEP_5 = "step_5"
    STEP_7 = "step_7"


_STEP_LIMITS: dict[AcceptanceStep, tuple[int, int]] = {
    AcceptanceStep.STEP_5: (8, 35_000),
    AcceptanceStep.STEP_7: (4, 15_000),
}


@dataclass(frozen=True, slots=True)
class AcceptanceSummary:
    """Public totals that contain usage metadata but no model or player content."""

    total_calls: int
    pending_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_micro_usd: int


class AcceptanceLedger:
    """Reserve bounded calls atomically and settle official usage before assertions."""

    def __init__(self, *, database_path: Path, allowed_root: Path) -> None:
        if not isinstance(database_path, Path) or not isinstance(allowed_root, Path):
            raise TypeError("Acceptance ledger boundaries must be paths")

        resolved_root = allowed_root.resolve(strict=False)
        resolved_database = database_path.resolve(strict=False)
        if not resolved_database.is_relative_to(resolved_root):
            raise ValueError("Acceptance ledger must stay inside its approved root")
        if resolved_database.suffix != ".sqlite3":
            raise ValueError("Acceptance ledger must use an approved SQLite filename")
        if not resolved_root.is_dir() or not resolved_database.parent.is_dir():
            raise ValueError("Acceptance ledger parent must already exist")
        for current in (database_path, *database_path.parents):
            if current.is_symlink() or current.is_junction():
                raise ValueError("Acceptance ledger must not traverse symbolic links")
            if current.resolve(strict=False) == resolved_root:
                break

        self.database_path = resolved_database

    def initialize(self) -> None:
        """Create or validate the minimal metadata-only ledger without resetting it."""

        try:
            with closing(self._connect()) as connection:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise AcceptanceLedgerError("Acceptance ledger is unavailable")
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS acceptance_calls ("
                        "reservation_id TEXT PRIMARY KEY, "
                        "authorization_id TEXT NOT NULL, "
                        "step TEXT NOT NULL CHECK(step IN ('step_5', 'step_7')), "
                        "model TEXT NOT NULL, "
                        "status TEXT NOT NULL "
                        "CHECK(status IN ('reserved', 'completed', 'unknown')), "
                        "reserved_micro_usd INTEGER NOT NULL CHECK(reserved_micro_usd > 0), "
                        "actual_micro_usd INTEGER CHECK(actual_micro_usd >= 0), "
                        "prompt_tokens INTEGER CHECK(prompt_tokens >= 0), "
                        "completion_tokens INTEGER CHECK(completion_tokens >= 0), "
                        "created_at INTEGER NOT NULL CHECK(created_at > 0), "
                        "completed_at INTEGER CHECK(completed_at > 0))"
                    )
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS acceptance_calls_step_status "
                        "ON acceptance_calls(step, status)"
                    )
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise AcceptanceLedgerError("Acceptance ledger is unavailable") from error

    def reserve(
        self,
        *,
        authorization_id: str,
        step: AcceptanceStep,
        model: str,
        reserved_micro_usd: int,
    ) -> UUID:
        """Atomically persist authorization and conservative cost before dispatch."""

        if (
            not isinstance(authorization_id, str)
            or _AUTHORIZATION_ID.fullmatch(authorization_id) is None
        ):
            raise ValueError("Acceptance requires an explicit safe authorization identifier")
        if not isinstance(step, AcceptanceStep):
            raise TypeError("Acceptance requires an independently approved task step")
        if model != DEEPSEEK_MODEL:
            raise ValueError("Acceptance model does not match its approved version")
        if type(reserved_micro_usd) is not int:
            raise TypeError("Acceptance cost reservation must use integer micro-USD")
        if reserved_micro_usd <= 0:
            raise ValueError("Acceptance cost reservation must be positive")

        reservation_id = uuid4()
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._check_budget(connection, step, reserved_micro_usd)
                    connection.execute(
                        "INSERT INTO acceptance_calls "
                        "(reservation_id, authorization_id, step, model, status, "
                        "reserved_micro_usd, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(reservation_id),
                            authorization_id,
                            step.value,
                            model,
                            "reserved",
                            reserved_micro_usd,
                            int(time.time()),
                        ),
                    )
                    connection.commit()
                except (sqlite3.Error, AcceptanceLedgerError):
                    connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise AcceptanceLedgerError("Acceptance ledger is unavailable") from error
        return reservation_id

    def record_usage(
        self,
        reservation_id: UUID,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        actual_micro_usd: int,
    ) -> None:
        """Durably settle official usage immediately after provider completion."""

        if not isinstance(reservation_id, UUID):
            raise TypeError("Acceptance reservation must be a validated UUID")
        for name, value in (
            ("prompt tokens", prompt_tokens),
            ("completion tokens", completion_tokens),
            ("actual micro-USD", actual_micro_usd),
        ):
            if type(value) is not int:
                raise TypeError(f"Acceptance {name} must be an integer")
            if value <= 0:
                raise ValueError(f"Acceptance {name} must be positive")

        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    record = connection.execute(
                        "SELECT status, reserved_micro_usd FROM acceptance_calls "
                        "WHERE reservation_id = ?",
                        (str(reservation_id),),
                    ).fetchone()
                    if record is None or record[0] != "reserved":
                        raise AcceptanceLedgerError("Acceptance reservation is unavailable")
                    if actual_micro_usd > record[1]:
                        connection.execute(
                            "UPDATE acceptance_calls SET status = 'unknown' "
                            "WHERE reservation_id = ?",
                            (str(reservation_id),),
                        )
                        connection.commit()
                        raise AcceptanceBudgetError(
                            "Acceptance actual cost exceeds its atomic reservation"
                        )
                    connection.execute(
                        "UPDATE acceptance_calls SET status = 'completed', "
                        "prompt_tokens = ?, completion_tokens = ?, actual_micro_usd = ?, "
                        "completed_at = ? WHERE reservation_id = ?",
                        (
                            prompt_tokens,
                            completion_tokens,
                            actual_micro_usd,
                            int(time.time()),
                            str(reservation_id),
                        ),
                    )
                    connection.commit()
                except (sqlite3.Error, AcceptanceLedgerError):
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise AcceptanceLedgerError("Acceptance ledger is unavailable") from error

    def mark_unknown(self, reservation_id: UUID) -> None:
        """Persist an unresolved external outcome; all further calls remain blocked."""

        if not isinstance(reservation_id, UUID):
            raise TypeError("Acceptance reservation must be a validated UUID")
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                changed = connection.execute(
                    "UPDATE acceptance_calls SET status = 'unknown' "
                    "WHERE reservation_id = ? AND status = 'reserved'",
                    (str(reservation_id),),
                ).rowcount
                if changed != 1:
                    connection.rollback()
                    raise AcceptanceLedgerError("Acceptance reservation is unavailable")
                connection.commit()
        except sqlite3.Error as error:
            raise AcceptanceLedgerError("Acceptance ledger is unavailable") from error

    def summary(self) -> AcceptanceSummary:
        """Read bounded aggregate usage without exposing any request or response text."""

        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT COUNT(*), "
                    "COALESCE(SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(prompt_tokens), 0), "
                    "COALESCE(SUM(completion_tokens), 0), "
                    "COALESCE(SUM(actual_micro_usd), 0) FROM acceptance_calls"
                ).fetchone()
                if row is None:
                    raise AcceptanceLedgerError("Acceptance ledger summary is unavailable")
                return AcceptanceSummary(*row)
        except sqlite3.Error as error:
            raise AcceptanceLedgerError("Acceptance ledger is unavailable") from error

    @staticmethod
    def _check_budget(
        connection: sqlite3.Connection, step: AcceptanceStep, reserved_micro_usd: int
    ) -> None:
        unresolved = connection.execute(
            "SELECT COUNT(*) FROM acceptance_calls WHERE status IN ('reserved', 'unknown')"
        ).fetchone()
        if unresolved is not None and unresolved[0]:
            raise AcceptanceLedgerError("Acceptance has an unresolved provider reservation")

        total = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(actual_micro_usd), 0) FROM acceptance_calls"
        ).fetchone()
        scoped = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(actual_micro_usd), 0) "
            "FROM acceptance_calls WHERE step = ?",
            (step.value,),
        ).fetchone()
        if total is None or scoped is None:
            raise AcceptanceLedgerError("Acceptance ledger budget is unavailable")
        maximum_calls, maximum_cost = _STEP_LIMITS[step]
        if (
            total[0] >= _TOTAL_MAX_CALLS
            or total[1] + reserved_micro_usd > _TOTAL_MAX_MICRO_USD
            or scoped[0] >= maximum_calls
            or scoped[1] + reserved_micro_usd > maximum_cost
        ):
            raise AcceptanceBudgetError("Acceptance exceeds its independently approved budget")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=_BUSY_TIMEOUT_MILLISECONDS / 1_000,
            isolation_level=None,
        )
        try:
            connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MILLISECONDS:d}")
        except sqlite3.Error:
            connection.close()
            raise
        return connection

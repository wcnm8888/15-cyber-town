from __future__ import annotations

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

import pytest

from cyber_town.infrastructure.persistence.acceptance_ledger import (
    AcceptanceBudgetError,
    AcceptanceLedger,
    AcceptanceLedgerError,
    AcceptanceStep,
)

MODEL = "deepseek-v4-flash"
AUTHORIZATION = "f-005-step-5-synthetic-authorization"


@pytest.fixture
def ledger(tmp_path: Path) -> AcceptanceLedger:
    result = AcceptanceLedger(database_path=tmp_path / "ledger.sqlite3", allowed_root=tmp_path)
    result.initialize()
    return result


def reserve(
    ledger: AcceptanceLedger,
    *,
    step: AcceptanceStep = AcceptanceStep.STEP_5,
    reserved_micro_usd: int = 1_000,
) -> UUID:
    return ledger.reserve(
        authorization_id=AUTHORIZATION,
        step=step,
        model=MODEL,
        reserved_micro_usd=reserved_micro_usd,
    )


def settle(ledger: AcceptanceLedger, reservation_id: UUID, *, cost: int = 100) -> None:
    ledger.record_usage(
        reservation_id,
        prompt_tokens=12,
        completion_tokens=7,
        actual_micro_usd=cost,
    )


def test_initialization_only_uses_explicit_existing_isolated_parent(tmp_path: Path) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    ledger = AcceptanceLedger(database_path=database_path, allowed_root=tmp_path)

    assert not database_path.exists()
    ledger.initialize()
    ledger.initialize()

    assert database_path.is_file()
    assert ledger.summary().total_calls == 0


@pytest.mark.parametrize("suffix", [".db", ".txt", ""])
def test_ledger_rejects_unapproved_database_filenames(tmp_path: Path, suffix: str) -> None:
    with pytest.raises(ValueError):
        AcceptanceLedger(database_path=tmp_path / f"ledger{suffix}", allowed_root=tmp_path)


def test_ledger_rejects_paths_outside_the_approved_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        AcceptanceLedger(database_path=tmp_path.parent / "escape.sqlite3", allowed_root=tmp_path)


def test_reservation_is_persisted_before_a_provider_could_be_called(
    ledger: AcceptanceLedger,
) -> None:
    reservation_id = reserve(ledger)

    with sqlite3.connect(ledger.database_path) as connection:
        row = connection.execute(
            "SELECT authorization_id, step, model, status, reserved_micro_usd "
            "FROM acceptance_calls WHERE reservation_id = ?",
            (str(reservation_id),),
        ).fetchone()

    assert row == (AUTHORIZATION, "step_5", MODEL, "reserved", 1_000)
    assert ledger.summary().pending_calls == 1


def test_usage_is_durably_recorded_before_any_later_semantic_assertion(
    ledger: AcceptanceLedger,
) -> None:
    reservation_id = reserve(ledger)
    settle(ledger, reservation_id, cost=347)

    summary = ledger.summary()
    assert summary.total_calls == 1
    assert summary.pending_calls == 0
    assert summary.total_prompt_tokens == 12
    assert summary.total_completion_tokens == 7
    assert summary.total_micro_usd == 347


@pytest.mark.parametrize("bad_step", ["step_4", "step_6", "step_8", "step_5"])
def test_reservation_rejects_unapproved_or_untyped_steps(
    ledger: AcceptanceLedger, bad_step: str
) -> None:
    with pytest.raises((TypeError, ValueError)):
        ledger.reserve(
            authorization_id=AUTHORIZATION,
            step=bad_step,  # type: ignore[arg-type]
            model=MODEL,
            reserved_micro_usd=1_000,
        )


@pytest.mark.parametrize("bad_model", ["deepseek-chat", "", "deepseek-v4-flash "])
def test_reservation_rejects_model_drift(ledger: AcceptanceLedger, bad_model: str) -> None:
    with pytest.raises(ValueError):
        ledger.reserve(
            authorization_id=AUTHORIZATION,
            step=AcceptanceStep.STEP_5,
            model=bad_model,
            reserved_micro_usd=1_000,
        )


@pytest.mark.parametrize("bad_authorization", ["", "  ", "synthetic\nvalue"])
def test_reservation_requires_a_safe_explicit_authorization_identifier(
    ledger: AcceptanceLedger, bad_authorization: str
) -> None:
    with pytest.raises(ValueError):
        ledger.reserve(
            authorization_id=bad_authorization,
            step=AcceptanceStep.STEP_5,
            model=MODEL,
            reserved_micro_usd=1_000,
        )


@pytest.mark.parametrize("bad_cost", [0, -1, 1.5, True, 35_001])
def test_reservation_rejects_invalid_or_over_budget_costs(
    ledger: AcceptanceLedger, bad_cost: object
) -> None:
    with pytest.raises((TypeError, ValueError, AcceptanceBudgetError)):
        ledger.reserve(
            authorization_id=AUTHORIZATION,
            step=AcceptanceStep.STEP_5,
            model=MODEL,
            reserved_micro_usd=bad_cost,  # type: ignore[arg-type]
        )


def test_step_five_cannot_exceed_eight_calls(ledger: AcceptanceLedger) -> None:
    for _ in range(8):
        settle(ledger, reserve(ledger))

    with pytest.raises(AcceptanceBudgetError):
        reserve(ledger)
    assert ledger.summary().total_calls == 8


def test_step_seven_cannot_exceed_four_calls(ledger: AcceptanceLedger) -> None:
    for _ in range(4):
        settle(ledger, reserve(ledger, step=AcceptanceStep.STEP_7))

    with pytest.raises(AcceptanceBudgetError):
        reserve(ledger, step=AcceptanceStep.STEP_7)
    assert ledger.summary().total_calls == 4


def test_step_five_cost_limit_is_enforced_before_provider_dispatch(
    ledger: AcceptanceLedger,
) -> None:
    first = reserve(ledger, reserved_micro_usd=20_000)
    settle(ledger, first, cost=20_000)

    with pytest.raises(AcceptanceBudgetError):
        reserve(ledger, reserved_micro_usd=15_001)


def test_step_seven_cost_limit_is_enforced_before_provider_dispatch(
    ledger: AcceptanceLedger,
) -> None:
    first = reserve(ledger, step=AcceptanceStep.STEP_7, reserved_micro_usd=10_000)
    settle(ledger, first, cost=10_000)

    with pytest.raises(AcceptanceBudgetError):
        reserve(ledger, step=AcceptanceStep.STEP_7, reserved_micro_usd=5_001)


def test_unresolved_reservation_blocks_all_new_calls_across_instances(
    ledger: AcceptanceLedger,
) -> None:
    reserve(ledger)
    restarted = AcceptanceLedger(
        database_path=ledger.database_path, allowed_root=ledger.database_path.parent
    )
    restarted.initialize()

    with pytest.raises(AcceptanceLedgerError):
        reserve(restarted)


def test_unknown_provider_outcome_fails_closed_after_restart(ledger: AcceptanceLedger) -> None:
    reservation_id = reserve(ledger)
    ledger.mark_unknown(reservation_id)

    restarted = AcceptanceLedger(
        database_path=ledger.database_path, allowed_root=ledger.database_path.parent
    )
    restarted.initialize()
    with pytest.raises(AcceptanceLedgerError):
        reserve(restarted, step=AcceptanceStep.STEP_7)


@pytest.mark.parametrize(
    "prompt_tokens,completion_tokens",
    [(-1, 1), (1, -1), (True, 1), (1, True), (0, 0), (0, 1), (1, 0)],
)
def test_usage_rejects_missing_or_invalid_official_token_counts(
    ledger: AcceptanceLedger, prompt_tokens: int, completion_tokens: int
) -> None:
    reservation_id = reserve(ledger)
    with pytest.raises((TypeError, ValueError)):
        ledger.record_usage(
            reservation_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            actual_micro_usd=100,
        )
    assert ledger.summary().pending_calls == 1


def test_completed_provider_call_cannot_be_settled_with_zero_cost(
    ledger: AcceptanceLedger,
) -> None:
    reservation_id = reserve(ledger)

    with pytest.raises(ValueError):
        ledger.record_usage(
            reservation_id,
            prompt_tokens=1,
            completion_tokens=1,
            actual_micro_usd=0,
        )

    assert ledger.summary().pending_calls == 1
    assert ledger.summary().total_micro_usd == 0


def test_usage_above_the_atomic_reservation_fails_closed(ledger: AcceptanceLedger) -> None:
    reservation_id = reserve(ledger, reserved_micro_usd=100)

    with pytest.raises(AcceptanceBudgetError):
        settle(ledger, reservation_id, cost=101)
    with pytest.raises(AcceptanceLedgerError):
        reserve(ledger)


def test_usage_cannot_be_recorded_twice(ledger: AcceptanceLedger) -> None:
    reservation_id = reserve(ledger)
    settle(ledger, reservation_id)

    with pytest.raises(AcceptanceLedgerError):
        settle(ledger, reservation_id)


def test_concurrent_instances_cannot_bypass_atomic_reservation(
    ledger: AcceptanceLedger,
) -> None:
    def attempt() -> bool:
        instance = AcceptanceLedger(
            database_path=ledger.database_path, allowed_root=ledger.database_path.parent
        )
        try:
            reserve(instance)
        except AcceptanceLedgerError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _index: attempt(), range(8)))

    assert sum(outcomes) == 1
    assert ledger.summary().pending_calls == 1


def test_a_new_python_process_observes_the_same_pending_reservation(
    ledger: AcceptanceLedger,
) -> None:
    reserve(ledger)
    code = (
        "from pathlib import Path; "
        "from cyber_town.infrastructure.persistence.acceptance_ledger "
        "import AcceptanceLedger, AcceptanceStep; "
        f"ledger=AcceptanceLedger(database_path=Path({str(ledger.database_path)!r}), "
        f"allowed_root=Path({str(ledger.database_path.parent)!r})); "
        "ledger.reserve(authorization_id='child-synthetic', step=AcceptanceStep.STEP_5, "
        "model='deepseek-v4-flash', reserved_micro_usd=1)"
    )

    result = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True, timeout=15
    )

    assert result.returncode != 0
    assert "unresolved" in result.stderr.lower()
    assert ledger.summary().pending_calls == 1


def test_ledger_schema_cannot_store_prompt_player_message_reply_or_credential(
    ledger: AcceptanceLedger,
) -> None:
    with sqlite3.connect(ledger.database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(acceptance_calls)").fetchall()
        }

    assert columns == {
        "reservation_id",
        "authorization_id",
        "step",
        "model",
        "status",
        "reserved_micro_usd",
        "actual_micro_usd",
        "prompt_tokens",
        "completion_tokens",
        "created_at",
        "completed_at",
    }


def test_corrupt_ledger_fails_closed_without_overwrite(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt.sqlite3"
    database_path.write_bytes(b"synthetic-corrupt-not-a-database")
    ledger = AcceptanceLedger(database_path=database_path, allowed_root=tmp_path)

    with pytest.raises(AcceptanceLedgerError):
        ledger.initialize()
    assert database_path.read_bytes() == b"synthetic-corrupt-not-a-database"

"""Strict SQLite persistence and read-only querying for metadata-only observability."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Lock
from uuid import UUID

from cyber_town.application.observability import (
    OBSERVABILITY_SCHEMA_VERSION,
    AttemptKind,
    DurableObservabilityRecorder,
    ObservabilityRecord,
    RecordStatus,
    StageOutcome,
    TerminalOutcome,
    TraceErrorCode,
    TraceMetadata,
    TraceReasonCode,
    TraceStage,
    TraceStageMetadata,
)
from cyber_town.application.observability_evaluation import EvaluationReport

OBSERVABILITY_MIGRATIONS = ((1, "0001_observability.sql"),)
_BUSY_TIMEOUT_MILLISECONDS = 500
_TRACE_RETENTION_AGE = timedelta(days=7)
_TRACE_RETENTION_COUNT = 10_000
_EVALUATION_RETENTION_AGE = timedelta(days=30)
_EVALUATION_RETENTION_COUNT = 50
_TAG_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_VERSION_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?$")
_CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
_REQUIRED_TABLES = frozenset(
    {
        "schema_migrations",
        "trace_runs",
        "trace_stage_events",
        "execution_links",
        "evaluation_runs",
        "evaluation_cases",
        "replay_index",
    }
)


class ObservabilityStorageError(RuntimeError):
    """The metadata-only observability store cannot be used safely."""


class ObservabilityConflictError(ObservabilityStorageError):
    """A unique trace, execution owner, evaluation, or replay already exists."""


class ReplayMode(StrEnum):
    METADATA_ONLY_NOT_EXECUTABLE = "metadata_only_not_executable"
    SYNTHETIC_FIXTURE_EXECUTABLE = "synthetic_fixture_executable"


def _require_utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"Observability {label} type is invalid")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"Observability {label} must use UTC")
    return value


def _epoch_milliseconds(value: datetime) -> int:
    return round(_require_utc(value, "timestamp").timestamp() * 1_000)


def _utc_text(milliseconds: int | None) -> str | None:
    if milliseconds is None:
        return None
    return (
        datetime.fromtimestamp(milliseconds / 1_000, tz=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _require_version(value: object, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > 64 or _VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"Observability {label} is invalid")
    return value


def _require_digest(value: object) -> str:
    if not isinstance(value, str) or _TAG_PATTERN.fullmatch(value) is None:
        raise ValueError("Observability digest is invalid")
    return value


@dataclass(frozen=True, slots=True)
class ReplayIndexEntry:
    replay_id: UUID
    schema_version: int
    trace_id: UUID | None
    request_id: UUID | None
    execution_id: UUID | None
    fixture_version: str | None
    case_id: str | None
    evaluator_version: str
    persona_version: str | None
    terminal_outcome: TerminalOutcome | None
    digest: str
    execution_mode: ReplayMode
    created_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.replay_id, UUID):
            raise TypeError("Observability replay identifier type is invalid")
        if self.schema_version != OBSERVABILITY_SCHEMA_VERSION:
            raise ValueError("Observability replay schema version is invalid")
        for value in (self.trace_id, self.request_id, self.execution_id):
            if value is not None and not isinstance(value, UUID):
                raise TypeError("Observability replay linkage type is invalid")
        _require_version(self.evaluator_version, "evaluator version")
        _require_version(self.persona_version, "persona version", optional=True)
        _require_digest(self.digest)
        _require_utc(self.created_at_utc, "replay timestamp")
        if not isinstance(self.execution_mode, ReplayMode):
            raise TypeError("Observability replay mode type is invalid")
        if self.terminal_outcome is not None and not isinstance(
            self.terminal_outcome, TerminalOutcome
        ):
            raise TypeError("Observability replay outcome type is invalid")
        if self.execution_mode is ReplayMode.METADATA_ONLY_NOT_EXECUTABLE:
            if (
                self.trace_id is None
                or self.fixture_version is not None
                or self.case_id is not None
            ):
                raise ValueError("Metadata-only replay linkage is invalid")
        else:
            if (
                self.trace_id is not None
                or self.request_id is not None
                or self.execution_id is not None
                or _require_version(self.fixture_version, "fixture version") is None
                or not isinstance(self.case_id, str)
                or len(self.case_id) > 64
                or _CASE_ID_PATTERN.fullmatch(self.case_id) is None
            ):
                raise ValueError("Synthetic replay linkage is invalid")

    @classmethod
    def metadata_only(
        cls,
        *,
        replay_id: UUID,
        trace: TraceMetadata,
        digest: str,
        created_at_utc: datetime,
    ) -> ReplayIndexEntry:
        if not isinstance(trace, TraceMetadata):
            raise TypeError("Observability replay trace type is invalid")
        return cls(
            replay_id=replay_id,
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=trace.trace_id,
            request_id=trace.request_id,
            execution_id=trace.execution_id,
            fixture_version=None,
            case_id=None,
            evaluator_version="metadata-index-v1",
            persona_version=trace.persona_version,
            terminal_outcome=trace.terminal_outcome,
            digest=digest,
            execution_mode=ReplayMode.METADATA_ONLY_NOT_EXECUTABLE,
            created_at_utc=created_at_utc,
        )

    @classmethod
    def synthetic_fixture(
        cls,
        *,
        replay_id: UUID,
        fixture_version: str,
        case_id: str,
        evaluator_version: str,
        persona_version: str | None,
        digest: str,
        created_at_utc: datetime,
    ) -> ReplayIndexEntry:
        return cls(
            replay_id=replay_id,
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=None,
            request_id=None,
            execution_id=None,
            fixture_version=fixture_version,
            case_id=case_id,
            evaluator_version=evaluator_version,
            persona_version=persona_version,
            terminal_outcome=None,
            digest=digest,
            execution_mode=ReplayMode.SYNTHETIC_FIXTURE_EXECUTABLE,
            created_at_utc=created_at_utc,
        )


@dataclass(frozen=True, slots=True)
class RetentionMarkSummary:
    trace_count: int
    stage_count: int
    execution_link_count: int
    replay_count: int
    evaluation_count: int
    evaluation_case_count: int


@dataclass(frozen=True, slots=True)
class ObservabilityQuery:
    trace_id: UUID | None = None
    request_id: UUID | None = None
    since_utc: datetime | None = None
    until_utc: datetime | None = None
    terminal_outcome: TerminalOutcome | None = None
    error_code: TraceErrorCode | None = None
    persona_version: str | None = None
    scope_tag: str | None = None
    limit: int = 50

    def __post_init__(self) -> None:
        for value in (self.trace_id, self.request_id):
            if value is not None and not isinstance(value, UUID):
                raise TypeError("Observability query identifier type is invalid")
        if self.since_utc is not None:
            _require_utc(self.since_utc, "query start")
        if self.until_utc is not None:
            _require_utc(self.until_utc, "query end")
        if (
            self.since_utc is not None
            and self.until_utc is not None
            and self.until_utc < self.since_utc
        ):
            raise ValueError("Observability query time window is invalid")
        if self.terminal_outcome is not None and not isinstance(
            self.terminal_outcome, TerminalOutcome
        ):
            raise TypeError("Observability query outcome type is invalid")
        if self.error_code is not None and not isinstance(self.error_code, TraceErrorCode):
            raise TypeError("Observability query error type is invalid")
        _require_version(self.persona_version, "query persona version", optional=True)
        if self.scope_tag is not None and _TAG_PATTERN.fullmatch(self.scope_tag) is None:
            raise ValueError("Observability query scope tag is invalid")
        if type(self.limit) is not int or not 1 <= self.limit <= 200:
            raise ValueError("Observability query limit is invalid")


class SqliteObservabilityRepository(DurableObservabilityRecorder):
    """Persist strict records and expose only allowlisted read-only summaries."""

    TRACE_QUERY_FIELDS = frozenset(
        {
            "schema_version",
            "trace_id",
            "request_id",
            "execution_id",
            "attempt_kind",
            "player_scope_tag",
            "npc_scope_tag",
            "conversation_scope_tag",
            "persona_version",
            "provider_kind",
            "record_status",
            "terminal_outcome",
            "error_code",
            "reason_code",
            "provider_dispatch_count",
            "started_at_utc",
            "finished_at_utc",
            "total_latency_ms",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cost_micro_usd",
            "retention_status",
        }
    )
    EVALUATION_QUERY_FIELDS = frozenset(
        {
            "run_id",
            "schema_version",
            "evaluator_version",
            "fixture_version",
            "started_at_utc",
            "finished_at_utc",
            "case_count",
            "passed_count",
            "failed_count",
            "trace_completeness_ppm",
            "stage_consistency_ppm",
            "scope_leak_count",
            "forbidden_content_hit_count",
            "provider_attribution_error_count",
            "nonzero_cost_case_count",
            "canonical_digest",
            "retention_status",
        }
    )
    REPLAY_QUERY_FIELDS = frozenset(
        {
            "replay_id",
            "schema_version",
            "trace_id",
            "request_id",
            "execution_id",
            "fixture_version",
            "case_id",
            "evaluator_version",
            "persona_version",
            "terminal_outcome",
            "digest",
            "execution_mode",
            "created_at_utc",
            "retention_status",
        }
    )

    def __init__(self, *, database_path: Path, allowed_root: Path) -> None:
        if not isinstance(database_path, Path) or not isinstance(allowed_root, Path):
            raise TypeError("Observability database boundaries must be paths")
        self._allowed_root = allowed_root.resolve(strict=False)
        resolved_root = self._allowed_root
        resolved_database = database_path.resolve(strict=False)
        if not resolved_database.is_relative_to(resolved_root):
            raise ValueError("Observability database must stay inside its approved root")
        if resolved_database.suffix != ".sqlite3":
            raise ValueError("Observability database must use an approved SQLite filename")
        if not resolved_root.is_dir() or not resolved_database.parent.is_dir():
            raise ValueError("Observability database parent must already exist")
        for current in (database_path, *database_path.parents):
            if current.is_symlink() or current.is_junction():
                raise ValueError("Observability database must not traverse symbolic links")
            if current.resolve(strict=False) == resolved_root:
                break
        self.database_path = resolved_database
        self._busy_timeout_milliseconds = _BUSY_TIMEOUT_MILLISECONDS
        self._pending_lock = Lock()
        self._pending_stages: dict[UUID, list[TraceStageMetadata]] = {}

    def __repr__(self) -> str:
        return "SqliteObservabilityRepository()"

    def initialize(self) -> None:
        migration_path = Path(__file__).parent / "migrations" / OBSERVABILITY_MIGRATIONS[0][1]
        try:
            migration_bytes = migration_path.read_bytes()
            migration = migration_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ObservabilityStorageError(
                "Observability schema migration is unavailable"
            ) from error
        checksum = hashlib.sha256(migration_bytes).hexdigest()
        try:
            with closing(self._connect()) as connection:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ObservabilityStorageError("Observability storage is unavailable")
                existing_tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                }
                if existing_tables and "schema_migrations" not in existing_tables:
                    raise ObservabilityStorageError("Observability schema version is unavailable")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations ("
                        "version INTEGER PRIMARY KEY CHECK (version > 0), "
                        "name TEXT NOT NULL UNIQUE, "
                        "checksum TEXT NOT NULL CHECK (length(checksum) = 64), "
                        "applied_at_ms INTEGER NOT NULL CHECK (applied_at_ms > 0)"
                        ") STRICT"
                    )
                    existing = connection.execute(
                        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
                    ).fetchall()
                    expected = [(1, OBSERVABILITY_MIGRATIONS[0][1], checksum)]
                    if existing != expected[: len(existing)]:
                        raise ObservabilityStorageError(
                            "Observability schema version is unavailable"
                        )
                    if not existing:
                        for statement in self._migration_statements(migration):
                            connection.execute(statement)
                        connection.execute(
                            "INSERT INTO schema_migrations "
                            "(version, name, checksum, applied_at_ms) VALUES (?, ?, ?, ?)",
                            (
                                1,
                                OBSERVABILITY_MIGRATIONS[0][1],
                                checksum,
                                _epoch_milliseconds(datetime.now(UTC)),
                            ),
                        )
                    if connection.execute("PRAGMA user_version").fetchone() != (1,):
                        raise ObservabilityStorageError(
                            "Observability schema version is unavailable"
                        )
                    self._validate_required_tables(connection)
                    connection.commit()
                except (sqlite3.Error, ObservabilityStorageError):
                    connection.rollback()
                    raise
        except ObservabilityStorageError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    @staticmethod
    def _migration_statements(script: str) -> tuple[str, ...]:
        statements: list[str] = []
        buffer = ""
        for line in script.splitlines(keepends=True):
            buffer += line
            if sqlite3.complete_statement(buffer):
                statement = buffer.strip()
                if statement:
                    statements.append(statement)
                buffer = ""
        if buffer.strip():
            raise ObservabilityStorageError("Observability schema migration is unavailable")
        return tuple(statements)

    def record(self, record: ObservabilityRecord) -> None:
        if isinstance(record, TraceStageMetadata):
            with self._pending_lock:
                self._pending_stages.setdefault(record.trace_id, []).append(record)
            return
        if not isinstance(record, TraceMetadata):
            raise TypeError("Observability record type is invalid")
        with self._pending_lock:
            stages = tuple(self._pending_stages.pop(record.trace_id, ()))
        self.save_trace(record, stages)

    def snapshot(self) -> tuple[ObservabilityRecord, ...]:
        with self._pending_lock:
            return tuple(
                stage
                for trace_id in sorted(self._pending_stages, key=str)
                for stage in self._pending_stages[trace_id]
            )

    def start_trace(self, trace: TraceMetadata) -> None:
        if not isinstance(trace, TraceMetadata) or trace.record_status is not RecordStatus.OPEN:
            raise ValueError("Observability open trace is invalid")
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._insert_trace(connection, trace)
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    def record_progress(self, trace: TraceMetadata, stage: TraceStageMetadata) -> None:
        if (
            not isinstance(trace, TraceMetadata)
            or trace.record_status is not RecordStatus.OPEN
            or not isinstance(stage, TraceStageMetadata)
            or stage.trace_id != trace.trace_id
        ):
            raise ValueError("Observability trace progress is invalid")
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._update_open_trace(connection, trace)
                    self._upsert_stage(connection, stage)
                    connection.commit()
                except (sqlite3.Error, ObservabilityConflictError):
                    connection.rollback()
                    raise
        except ObservabilityConflictError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    def finish_trace(
        self,
        trace: TraceMetadata,
        stages: Sequence[TraceStageMetadata],
    ) -> None:
        if not isinstance(trace, TraceMetadata) or trace.record_status is RecordStatus.OPEN:
            raise ValueError("Observability terminal trace is invalid")
        self._validate_complete_stages(trace, stages)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT record_status FROM trace_runs WHERE trace_id = ?",
                        (str(trace.trace_id),),
                    ).fetchone()
                    if existing is None:
                        self._insert_trace(connection, trace)
                    elif existing != (RecordStatus.OPEN.value,):
                        raise ObservabilityConflictError("Observability record already exists")
                    for stage in stages:
                        self._upsert_stage(connection, stage)
                    if existing is not None:
                        self._update_open_trace(connection, trace)
                    self._validate_persisted_stages(connection, trace.trace_id)
                    self._insert_execution_link_if_needed(connection, trace)
                    connection.commit()
                except (sqlite3.Error, ObservabilityConflictError):
                    connection.rollback()
                    raise
        except ObservabilityConflictError:
            raise
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    def save_trace(
        self,
        trace: TraceMetadata,
        stages: Sequence[TraceStageMetadata],
    ) -> None:
        if not isinstance(trace, TraceMetadata):
            raise TypeError("Observability trace type is invalid")
        self._validate_complete_stages(trace, stages)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._insert_trace(connection, trace)
                    for stage in stages:
                        self._upsert_stage(connection, stage)
                    self._insert_execution_link_if_needed(connection, trace)
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    @staticmethod
    def _insert_trace(connection: sqlite3.Connection, trace: TraceMetadata) -> None:
        tags = trace.scope_tags
        connection.execute(
            "INSERT INTO trace_runs ("
            "trace_id, schema_version, request_id, execution_id, attempt_kind, "
            "player_scope_tag, npc_scope_tag, conversation_scope_tag, persona_version, "
            "provider_kind, record_status, terminal_outcome, error_code, reason_code, "
            "idempotency_outcome, short_term_outcome, long_term_outcome, "
            "relationship_outcome, retryable, from_cache, provider_dispatch_count, "
            "started_at_ms, finished_at_ms, total_latency_ms, provider_wait_ms, "
            "provider_latency_ms, context_budget_units, selected_short_term_turns, "
            "selected_long_term_facts, input_chars, output_chars, prompt_tokens, "
            "completion_tokens, total_tokens, cost_micro_usd"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(trace.trace_id),
                trace.schema_version,
                None if trace.request_id is None else str(trace.request_id),
                None if trace.execution_id is None else str(trace.execution_id),
                trace.attempt_kind.value,
                None if tags is None else tags.player_scope_tag,
                None if tags is None else tags.npc_scope_tag,
                None if tags is None else tags.conversation_scope_tag,
                trace.persona_version,
                trace.provider_kind.value,
                trace.record_status.value,
                None if trace.terminal_outcome is None else trace.terminal_outcome.value,
                trace.error_code.value,
                trace.reason_code.value,
                trace.idempotency_outcome.value,
                trace.short_term_outcome.value,
                trace.long_term_outcome.value,
                trace.relationship_outcome.value,
                int(trace.retryable),
                int(trace.from_cache),
                trace.provider_dispatch_count,
                _epoch_milliseconds(trace.started_at_utc),
                None
                if trace.finished_at_utc is None
                else _epoch_milliseconds(trace.finished_at_utc),
                trace.total_latency_ms,
                trace.provider_wait_ms,
                trace.provider_latency_ms,
                trace.context_budget_units,
                trace.selected_short_term_turns,
                trace.selected_long_term_facts,
                trace.input_chars,
                trace.output_chars,
                trace.prompt_tokens,
                trace.completion_tokens,
                trace.total_tokens,
                trace.cost_micro_usd,
            ),
        )

    @staticmethod
    def _update_open_trace(connection: sqlite3.Connection, trace: TraceMetadata) -> None:
        tags = trace.scope_tags
        updated = connection.execute(
            "UPDATE trace_runs SET schema_version = ?, request_id = ?, execution_id = ?, "
            "attempt_kind = ?, player_scope_tag = ?, npc_scope_tag = ?, "
            "conversation_scope_tag = ?, persona_version = ?, provider_kind = ?, "
            "record_status = ?, terminal_outcome = ?, error_code = ?, reason_code = ?, "
            "idempotency_outcome = ?, short_term_outcome = ?, long_term_outcome = ?, "
            "relationship_outcome = ?, retryable = ?, from_cache = ?, "
            "provider_dispatch_count = ?, started_at_ms = ?, finished_at_ms = ?, "
            "total_latency_ms = ?, provider_wait_ms = ?, provider_latency_ms = ?, "
            "context_budget_units = ?, selected_short_term_turns = ?, "
            "selected_long_term_facts = ?, input_chars = ?, output_chars = ?, "
            "prompt_tokens = ?, completion_tokens = ?, total_tokens = ?, cost_micro_usd = ? "
            "WHERE trace_id = ? AND record_status = 'open'",
            (
                trace.schema_version,
                None if trace.request_id is None else str(trace.request_id),
                None if trace.execution_id is None else str(trace.execution_id),
                trace.attempt_kind.value,
                None if tags is None else tags.player_scope_tag,
                None if tags is None else tags.npc_scope_tag,
                None if tags is None else tags.conversation_scope_tag,
                trace.persona_version,
                trace.provider_kind.value,
                trace.record_status.value,
                None if trace.terminal_outcome is None else trace.terminal_outcome.value,
                trace.error_code.value,
                trace.reason_code.value,
                trace.idempotency_outcome.value,
                trace.short_term_outcome.value,
                trace.long_term_outcome.value,
                trace.relationship_outcome.value,
                int(trace.retryable),
                int(trace.from_cache),
                trace.provider_dispatch_count,
                _epoch_milliseconds(trace.started_at_utc),
                None
                if trace.finished_at_utc is None
                else _epoch_milliseconds(trace.finished_at_utc),
                trace.total_latency_ms,
                trace.provider_wait_ms,
                trace.provider_latency_ms,
                trace.context_budget_units,
                trace.selected_short_term_turns,
                trace.selected_long_term_facts,
                trace.input_chars,
                trace.output_chars,
                trace.prompt_tokens,
                trace.completion_tokens,
                trace.total_tokens,
                trace.cost_micro_usd,
                str(trace.trace_id),
            ),
        )
        if updated.rowcount != 1:
            raise ObservabilityConflictError("Observability open trace is unavailable")

    @staticmethod
    def _validate_complete_stages(
        trace: TraceMetadata,
        stages: Sequence[TraceStageMetadata],
    ) -> None:
        expected = tuple(TraceStage)
        actual = tuple(stage.stage for stage in stages)
        if (
            len(stages) != len(expected)
            or actual != expected
            or any(not isinstance(stage, TraceStageMetadata) for stage in stages)
            or any(stage.trace_id != trace.trace_id for stage in stages)
        ):
            raise ValueError("Observability trace stage set is invalid")

    @staticmethod
    def _upsert_stage(connection: sqlite3.Connection, stage: TraceStageMetadata) -> None:
        connection.execute(
            "INSERT INTO trace_stage_events ("
            "trace_id, sequence, schema_version, stage, outcome, reason_code, "
            "error_code, started_at_ms, finished_at_ms, latency_ms, item_count"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(trace_id, sequence) DO UPDATE SET "
            "schema_version = excluded.schema_version, stage = excluded.stage, "
            "outcome = excluded.outcome, reason_code = excluded.reason_code, "
            "error_code = excluded.error_code, started_at_ms = excluded.started_at_ms, "
            "finished_at_ms = excluded.finished_at_ms, latency_ms = excluded.latency_ms, "
            "item_count = excluded.item_count",
            (
                str(stage.trace_id),
                stage.sequence,
                stage.schema_version,
                stage.stage.value,
                stage.outcome.value,
                stage.reason_code.value,
                stage.error_code.value,
                _epoch_milliseconds(stage.started_at_utc),
                None
                if stage.finished_at_utc is None
                else _epoch_milliseconds(stage.finished_at_utc),
                stage.latency_ms,
                stage.item_count,
            ),
        )

    @staticmethod
    def _validate_persisted_stages(connection: sqlite3.Connection, trace_id: UUID) -> None:
        actual = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT stage FROM trace_stage_events WHERE trace_id = ? ORDER BY sequence",
                (str(trace_id),),
            )
        )
        if actual != tuple(stage.value for stage in TraceStage):
            raise ObservabilityConflictError("Observability trace stage set is invalid")

    @staticmethod
    def _insert_execution_link_if_needed(
        connection: sqlite3.Connection,
        trace: TraceMetadata,
    ) -> None:
        if trace.execution_id is None:
            return
        link_kind = (
            "dispatch_owner"
            if trace.provider_dispatch_count == 1
            else (
                "shared_waiter"
                if trace.attempt_kind is AttemptKind.CONCURRENT_WAITER
                else "local_execution"
            )
        )
        existing = connection.execute(
            "SELECT execution_id, link_kind, provider_dispatch_count "
            "FROM execution_links WHERE trace_id = ?",
            (str(trace.trace_id),),
        ).fetchone()
        expected = (str(trace.execution_id), link_kind, trace.provider_dispatch_count)
        if existing is None:
            connection.execute(
                "INSERT INTO execution_links "
                "(trace_id, execution_id, link_kind, provider_dispatch_count) "
                "VALUES (?, ?, ?, ?)",
                (str(trace.trace_id), *expected),
            )
        elif existing != expected:
            raise ObservabilityConflictError("Observability execution link is inconsistent")

    def save_evaluation(
        self,
        *,
        run_id: UUID,
        report: EvaluationReport,
        started_at_utc: datetime,
        finished_at_utc: datetime,
    ) -> None:
        if not isinstance(run_id, UUID) or not isinstance(report, EvaluationReport):
            raise TypeError("Observability evaluation record type is invalid")
        started = _epoch_milliseconds(started_at_utc)
        finished = _epoch_milliseconds(finished_at_utc)
        if finished < started:
            raise ValueError("Observability evaluation timestamps are inconsistent")
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "INSERT INTO evaluation_runs ("
                        "run_id, schema_version, evaluator_version, fixture_version, "
                        "started_at_ms, finished_at_ms, case_count, passed_count, failed_count, "
                        "trace_completeness_ppm, stage_consistency_ppm, scope_leak_count, "
                        "forbidden_content_hit_count, provider_attribution_error_count, "
                        "nonzero_cost_case_count, canonical_digest"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(run_id),
                            report.schema_version,
                            report.evaluator_version,
                            report.fixture_version,
                            started,
                            finished,
                            report.case_count,
                            report.passed_count,
                            report.failed_count,
                            report.trace_completeness_ppm,
                            report.stage_consistency_ppm,
                            report.scope_leak_count,
                            report.forbidden_content_hit_count,
                            report.provider_attribution_error_count,
                            report.nonzero_cost_case_count,
                            report.canonical_digest,
                        ),
                    )
                    connection.executemany(
                        "INSERT INTO evaluation_cases "
                        "(run_id, sequence, case_id, dimension, passed, failure_code) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            (
                                str(run_id),
                                sequence,
                                verdict.case_id,
                                verdict.dimension.value,
                                int(verdict.passed),
                                verdict.failure_code.value,
                            )
                            for sequence, verdict in enumerate(report.verdicts, start=1)
                        ],
                    )
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    def save_replay_index(self, entry: ReplayIndexEntry) -> None:
        if not isinstance(entry, ReplayIndexEntry):
            raise TypeError("Observability replay index type is invalid")
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    "INSERT INTO replay_index ("
                    "replay_id, schema_version, trace_id, request_id, execution_id, "
                    "fixture_version, case_id, evaluator_version, persona_version, "
                    "terminal_outcome, digest, execution_mode, created_at_ms"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(entry.replay_id),
                        entry.schema_version,
                        None if entry.trace_id is None else str(entry.trace_id),
                        None if entry.request_id is None else str(entry.request_id),
                        None if entry.execution_id is None else str(entry.execution_id),
                        entry.fixture_version,
                        entry.case_id,
                        entry.evaluator_version,
                        entry.persona_version,
                        None if entry.terminal_outcome is None else entry.terminal_outcome.value,
                        entry.digest,
                        entry.execution_mode.value,
                        _epoch_milliseconds(entry.created_at_utc),
                    ),
                )
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    def recover_open_traces(self, *, now_utc: datetime) -> int:
        now_ms = _epoch_milliseconds(now_utc)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    rows = connection.execute(
                        "SELECT trace_id, started_at_ms, execution_id, attempt_kind, "
                        "provider_dispatch_count FROM trace_runs WHERE record_status = 'open' "
                        "ORDER BY started_at_ms, trace_id"
                    ).fetchall()
                    for trace_id, started_at_ms, execution_id, attempt_kind, dispatch_count in rows:
                        finished_ms = max(now_ms, int(started_at_ms))
                        for sequence, stage in enumerate(TraceStage, start=1):
                            if stage is TraceStage.TERMINAL:
                                connection.execute(
                                    "INSERT INTO trace_stage_events ("
                                    "trace_id, sequence, schema_version, stage, outcome, "
                                    "reason_code, error_code, started_at_ms, finished_at_ms, "
                                    "latency_ms, item_count) VALUES "
                                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0) "
                                    "ON CONFLICT(trace_id, sequence) DO UPDATE SET "
                                    "outcome = excluded.outcome, "
                                    "reason_code = excluded.reason_code, "
                                    "error_code = excluded.error_code, "
                                    "started_at_ms = excluded.started_at_ms, "
                                    "finished_at_ms = excluded.finished_at_ms, latency_ms = 0, "
                                    "item_count = 0",
                                    (
                                        str(trace_id),
                                        sequence,
                                        OBSERVABILITY_SCHEMA_VERSION,
                                        stage.value,
                                        StageOutcome.FAILED.value,
                                        TraceReasonCode.RESTART_RECOVERY.value,
                                        TraceErrorCode.INTERNAL_ERROR.value,
                                        finished_ms,
                                        finished_ms,
                                    ),
                                )
                            else:
                                connection.execute(
                                    "INSERT INTO trace_stage_events ("
                                    "trace_id, sequence, schema_version, stage, outcome, "
                                    "reason_code, error_code, started_at_ms, finished_at_ms, "
                                    "latency_ms, item_count) VALUES "
                                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0) "
                                    "ON CONFLICT(trace_id, sequence) DO NOTHING",
                                    (
                                        str(trace_id),
                                        sequence,
                                        OBSERVABILITY_SCHEMA_VERSION,
                                        stage.value,
                                        StageOutcome.NOT_REACHED.value,
                                        TraceReasonCode.NOT_REACHED.value,
                                        TraceErrorCode.NONE.value,
                                        finished_ms,
                                        finished_ms,
                                    ),
                                )
                        updated = connection.execute(
                            "UPDATE trace_runs SET record_status = 'partial', "
                            "terminal_outcome = ?, error_code = ?, reason_code = ?, retryable = 1, "
                            "finished_at_ms = ?, total_latency_ms = MAX(0, ? - started_at_ms) "
                            "WHERE trace_id = ? AND record_status = 'open'",
                            (
                                TerminalOutcome.ABANDONED_AFTER_RESTART.value,
                                TraceErrorCode.INTERNAL_ERROR.value,
                                TraceReasonCode.RESTART_RECOVERY.value,
                                finished_ms,
                                finished_ms,
                                str(trace_id),
                            ),
                        )
                        if updated.rowcount != 1:
                            raise ObservabilityConflictError(
                                "Observability open trace is unavailable"
                            )
                        if execution_id is not None:
                            link_kind = (
                                "dispatch_owner"
                                if int(dispatch_count) == 1
                                else (
                                    "shared_waiter"
                                    if str(attempt_kind) == AttemptKind.CONCURRENT_WAITER.value
                                    else "local_execution"
                                )
                            )
                            expected = (str(execution_id), link_kind, int(dispatch_count))
                            existing = connection.execute(
                                "SELECT execution_id, link_kind, provider_dispatch_count "
                                "FROM execution_links WHERE trace_id = ?",
                                (str(trace_id),),
                            ).fetchone()
                            if existing is None:
                                connection.execute(
                                    "INSERT INTO execution_links "
                                    "(trace_id, execution_id, link_kind, "
                                    "provider_dispatch_count) VALUES (?, ?, ?, ?)",
                                    (str(trace_id), *expected),
                                )
                            elif existing != expected:
                                raise ObservabilityConflictError(
                                    "Observability execution link is inconsistent"
                                )
                        self._validate_persisted_stages(connection, UUID(str(trace_id)))
                    connection.commit()
                except (sqlite3.Error, ObservabilityConflictError):
                    connection.rollback()
                    raise
        except ObservabilityConflictError:
            raise
        except sqlite3.IntegrityError as error:
            raise ObservabilityConflictError("Observability record already exists") from error
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return len(rows)

    def mark_expired(self, *, now_utc: datetime) -> RetentionMarkSummary:
        now_ms = _epoch_milliseconds(now_utc)
        trace_cutoff = _epoch_milliseconds(now_utc - _TRACE_RETENTION_AGE)
        evaluation_cutoff = _epoch_milliseconds(now_utc - _EVALUATION_RETENTION_AGE)
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    trace_count = connection.execute(
                        "UPDATE trace_runs SET retention_status = 'expired', "
                        "marked_expired_at_ms = ? WHERE retention_status = 'active' "
                        "AND record_status <> 'open' AND (finished_at_ms < ? OR trace_id IN ("
                        "SELECT trace_id FROM trace_runs WHERE record_status <> 'open' "
                        "ORDER BY finished_at_ms DESC, trace_id DESC LIMIT -1 OFFSET ?))",
                        (now_ms, trace_cutoff, _TRACE_RETENTION_COUNT),
                    ).rowcount
                    stage_count = connection.execute(
                        "UPDATE trace_stage_events SET retention_status = 'expired' "
                        "WHERE retention_status = 'active' AND trace_id IN ("
                        "SELECT trace_id FROM trace_runs WHERE retention_status = 'expired')"
                    ).rowcount
                    execution_count = connection.execute(
                        "UPDATE execution_links SET retention_status = 'expired' "
                        "WHERE retention_status = 'active' AND trace_id IN ("
                        "SELECT trace_id FROM trace_runs WHERE retention_status = 'expired')"
                    ).rowcount
                    replay_count = connection.execute(
                        "UPDATE replay_index SET retention_status = 'expired', "
                        "marked_expired_at_ms = ? WHERE retention_status = 'active' AND ("
                        "created_at_ms < ? OR trace_id IN ("
                        "SELECT trace_id FROM trace_runs WHERE retention_status = 'expired') OR "
                        "replay_id IN (SELECT replay_id FROM replay_index "
                        "ORDER BY created_at_ms DESC, replay_id DESC LIMIT -1 OFFSET ?))",
                        (now_ms, trace_cutoff, _TRACE_RETENTION_COUNT),
                    ).rowcount
                    evaluation_count = connection.execute(
                        "UPDATE evaluation_runs SET retention_status = 'expired', "
                        "marked_expired_at_ms = ? WHERE retention_status = 'active' AND ("
                        "finished_at_ms < ? OR run_id IN (SELECT run_id FROM evaluation_runs "
                        "ORDER BY finished_at_ms DESC, run_id DESC LIMIT -1 OFFSET ?))",
                        (now_ms, evaluation_cutoff, _EVALUATION_RETENTION_COUNT),
                    ).rowcount
                    evaluation_case_count = connection.execute(
                        "UPDATE evaluation_cases SET retention_status = 'expired' "
                        "WHERE retention_status = 'active' AND run_id IN ("
                        "SELECT run_id FROM evaluation_runs WHERE retention_status = 'expired')"
                    ).rowcount
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return RetentionMarkSummary(
            trace_count=trace_count,
            stage_count=stage_count,
            execution_link_count=execution_count,
            replay_count=replay_count,
            evaluation_count=evaluation_count,
            evaluation_case_count=evaluation_case_count,
        )

    def query_traces(self, query: ObservabilityQuery) -> tuple[dict[str, object], ...]:
        if not isinstance(query, ObservabilityQuery):
            raise TypeError("Observability query type is invalid")
        conditions: list[str] = []
        parameters: list[object] = []
        if query.trace_id is not None:
            conditions.append("trace_id = ?")
            parameters.append(str(query.trace_id))
        if query.request_id is not None:
            conditions.append("request_id = ?")
            parameters.append(str(query.request_id))
        if query.since_utc is not None:
            conditions.append("started_at_ms >= ?")
            parameters.append(_epoch_milliseconds(query.since_utc))
        if query.until_utc is not None:
            conditions.append("started_at_ms <= ?")
            parameters.append(_epoch_milliseconds(query.until_utc))
        if query.terminal_outcome is not None:
            conditions.append("terminal_outcome = ?")
            parameters.append(query.terminal_outcome.value)
        if query.error_code is not None:
            conditions.append("error_code = ?")
            parameters.append(query.error_code.value)
        if query.persona_version is not None:
            conditions.append("persona_version = ?")
            parameters.append(query.persona_version)
        if query.scope_tag is not None:
            conditions.append(
                "(player_scope_tag = ? OR npc_scope_tag = ? OR conversation_scope_tag = ?)"
            )
            parameters.extend((query.scope_tag, query.scope_tag, query.scope_tag))
        where = "" if not conditions else " WHERE " + " AND ".join(conditions)
        parameters.append(query.limit)
        sql = (
            "SELECT schema_version, trace_id, request_id, execution_id, attempt_kind, "
            "player_scope_tag, npc_scope_tag, conversation_scope_tag, persona_version, "
            "provider_kind, record_status, terminal_outcome, error_code, reason_code, "
            "provider_dispatch_count, started_at_ms, finished_at_ms, total_latency_ms, "
            "prompt_tokens, completion_tokens, total_tokens, cost_micro_usd, retention_status "
            "FROM trace_runs" + where + " ORDER BY started_at_ms DESC, trace_id DESC LIMIT ?"
        )
        try:
            with closing(self._connect_read_only()) as connection:
                connection.row_factory = sqlite3.Row
                self._validate_read_schema(connection)
                rows = connection.execute(sql, parameters).fetchall()
        except ObservabilityStorageError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return tuple(self._query_row(row) for row in rows)

    def query_evaluations(self, *, limit: int = 50) -> tuple[dict[str, object], ...]:
        self._require_limit(limit)
        try:
            with closing(self._connect_read_only()) as connection:
                connection.row_factory = sqlite3.Row
                self._validate_read_schema(connection)
                rows = connection.execute(
                    "SELECT run_id, schema_version, evaluator_version, fixture_version, "
                    "started_at_ms, finished_at_ms, case_count, passed_count, failed_count, "
                    "trace_completeness_ppm, stage_consistency_ppm, scope_leak_count, "
                    "forbidden_content_hit_count, provider_attribution_error_count, "
                    "nonzero_cost_case_count, canonical_digest, retention_status "
                    "FROM evaluation_runs ORDER BY started_at_ms DESC, run_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except ObservabilityStorageError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return tuple(
            {
                "run_id": str(row["run_id"]),
                "schema_version": int(row["schema_version"]),
                "evaluator_version": str(row["evaluator_version"]),
                "fixture_version": str(row["fixture_version"]),
                "started_at_utc": _utc_text(int(row["started_at_ms"])),
                "finished_at_utc": _utc_text(int(row["finished_at_ms"])),
                "case_count": int(row["case_count"]),
                "passed_count": int(row["passed_count"]),
                "failed_count": int(row["failed_count"]),
                "trace_completeness_ppm": int(row["trace_completeness_ppm"]),
                "stage_consistency_ppm": int(row["stage_consistency_ppm"]),
                "scope_leak_count": int(row["scope_leak_count"]),
                "forbidden_content_hit_count": int(row["forbidden_content_hit_count"]),
                "provider_attribution_error_count": int(row["provider_attribution_error_count"]),
                "nonzero_cost_case_count": int(row["nonzero_cost_case_count"]),
                "canonical_digest": str(row["canonical_digest"]),
                "retention_status": str(row["retention_status"]),
            }
            for row in rows
        )

    def query_replay_index(self, *, limit: int = 50) -> tuple[dict[str, object], ...]:
        self._require_limit(limit)
        try:
            with closing(self._connect_read_only()) as connection:
                connection.row_factory = sqlite3.Row
                self._validate_read_schema(connection)
                rows = connection.execute(
                    "SELECT replay_id, schema_version, trace_id, request_id, execution_id, "
                    "fixture_version, case_id, evaluator_version, persona_version, "
                    "terminal_outcome, digest, execution_mode, created_at_ms, retention_status "
                    "FROM replay_index ORDER BY created_at_ms DESC, replay_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        except ObservabilityStorageError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return tuple(
            {
                "replay_id": str(row["replay_id"]),
                "schema_version": int(row["schema_version"]),
                "trace_id": None if row["trace_id"] is None else str(row["trace_id"]),
                "request_id": None if row["request_id"] is None else str(row["request_id"]),
                "execution_id": (None if row["execution_id"] is None else str(row["execution_id"])),
                "fixture_version": row["fixture_version"],
                "case_id": row["case_id"],
                "evaluator_version": str(row["evaluator_version"]),
                "persona_version": row["persona_version"],
                "terminal_outcome": row["terminal_outcome"],
                "digest": str(row["digest"]),
                "execution_mode": str(row["execution_mode"]),
                "created_at_utc": _utc_text(int(row["created_at_ms"])),
                "retention_status": str(row["retention_status"]),
            }
            for row in rows
        )

    @staticmethod
    def _query_row(row: sqlite3.Row) -> dict[str, object]:
        return {
            "schema_version": int(row["schema_version"]),
            "trace_id": str(row["trace_id"]),
            "request_id": None if row["request_id"] is None else str(row["request_id"]),
            "execution_id": (None if row["execution_id"] is None else str(row["execution_id"])),
            "attempt_kind": str(row["attempt_kind"]),
            "player_scope_tag": row["player_scope_tag"],
            "npc_scope_tag": row["npc_scope_tag"],
            "conversation_scope_tag": row["conversation_scope_tag"],
            "persona_version": row["persona_version"],
            "provider_kind": str(row["provider_kind"]),
            "record_status": str(row["record_status"]),
            "terminal_outcome": row["terminal_outcome"],
            "error_code": str(row["error_code"]),
            "reason_code": str(row["reason_code"]),
            "provider_dispatch_count": int(row["provider_dispatch_count"]),
            "started_at_utc": _utc_text(int(row["started_at_ms"])),
            "finished_at_utc": (
                None if row["finished_at_ms"] is None else _utc_text(int(row["finished_at_ms"]))
            ),
            "total_latency_ms": int(row["total_latency_ms"]),
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "total_tokens": int(row["total_tokens"]),
            "cost_micro_usd": int(row["cost_micro_usd"]),
            "retention_status": str(row["retention_status"]),
        }

    def retention_summary(self) -> dict[str, int]:
        try:
            with closing(self._connect_read_only()) as connection:
                self._validate_read_schema(connection)
                counts = {
                    f"{status}_{category}_count": int(
                        connection.execute(
                            f"SELECT COUNT(*) FROM {table} WHERE retention_status = ?",
                            (status,),
                        ).fetchone()[0]
                    )
                    for category, table in (
                        ("trace", "trace_runs"),
                        ("evaluation", "evaluation_runs"),
                        ("replay", "replay_index"),
                    )
                    for status in ("active", "expired")
                }
        except ObservabilityStorageError:
            raise
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error
        return counts

    @staticmethod
    def _require_limit(limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Observability query limit is invalid")

    def _validate_current_path(self) -> None:
        resolved_database = self.database_path.resolve(strict=False)
        if not resolved_database.is_relative_to(self._allowed_root):
            raise ObservabilityStorageError("Observability storage is unavailable")
        for current in (self.database_path, *self.database_path.parents):
            if current.is_symlink() or current.is_junction():
                raise ObservabilityStorageError("Observability storage is unavailable")
            if current.resolve(strict=False) == self._allowed_root:
                break

    def _connect(self) -> sqlite3.Connection:
        self._validate_current_path()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=self._busy_timeout_milliseconds / 1_000,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_milliseconds:d}")
            return connection
        except sqlite3.Error:
            if connection is not None:
                connection.close()
            raise

    def _connect_read_only(self) -> sqlite3.Connection:
        self._validate_current_path()
        if not self.database_path.is_file():
            raise ObservabilityStorageError("Observability storage is unavailable")
        try:
            return sqlite3.connect(
                f"{self.database_path.as_uri()}?mode=ro",
                uri=True,
                timeout=self._busy_timeout_milliseconds / 1_000,
            )
        except sqlite3.Error as error:
            raise ObservabilityStorageError("Observability storage is unavailable") from error

    @staticmethod
    def _validate_read_schema(connection: sqlite3.Connection) -> None:
        try:
            migration = connection.execute(
                "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            if (
                len(migration) != 1
                or migration[0][0] != 1
                or migration[0][1] != "0001_observability.sql"
                or not isinstance(migration[0][2], str)
                or _TAG_PATTERN.fullmatch(migration[0][2]) is None
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                or connection.execute("PRAGMA quick_check").fetchone()[0] != "ok"
            ):
                raise ObservabilityStorageError("Observability schema version is unavailable")
            SqliteObservabilityRepository._validate_required_tables(connection)
        except sqlite3.Error as error:
            raise ObservabilityStorageError(
                "Observability schema version is unavailable"
            ) from error

    @staticmethod
    def _validate_required_tables(connection: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != _REQUIRED_TABLES:
            raise ObservabilityStorageError("Observability schema version is unavailable")

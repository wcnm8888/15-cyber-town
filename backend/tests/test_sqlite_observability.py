from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import cyber_town.infrastructure.observability.sqlite_observability as sqlite_observability
from cyber_town.application.observability import (
    OBSERVABILITY_SCHEMA_VERSION,
    AttemptKind,
    DialogueObservability,
    IdempotencyOutcome,
    LongTermOutcome,
    ProviderKind,
    RecordStatus,
    RelationshipOutcome,
    ScopeTags,
    ShortTermOutcome,
    StageOutcome,
    TerminalOutcome,
    TraceErrorCode,
    TraceMetadata,
    TraceReasonCode,
    TraceStage,
    TraceStageMetadata,
)
from cyber_town.application.observability_evaluation import (
    build_baseline_observations,
    evaluate_observability,
    load_evaluation_fixture,
)
from cyber_town.infrastructure.observability.sqlite_observability import (
    OBSERVABILITY_MIGRATIONS,
    ObservabilityConflictError,
    ObservabilityQuery,
    ObservabilityStorageError,
    ReplayIndexEntry,
    ReplayMode,
    SqliteObservabilityRepository,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "f008_observability_evaluation_v1.json"
SYNTHETIC_KEY = b"f008-step4-synthetic-key-not-for-production"
NOW = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)


def _trace(
    *,
    trace_id: UUID | None = None,
    request_id: UUID | None = None,
    execution_id: UUID | None = None,
    started_at: datetime = NOW,
    terminal_outcome: TerminalOutcome = TerminalOutcome.COMPLETED,
    record_status: RecordStatus = RecordStatus.COMPLETE,
    provider_dispatch_count: int = 1,
) -> TraceMetadata:
    trace_id = trace_id or uuid4()
    request_id = request_id or uuid4()
    execution_id = execution_id or uuid4()
    return TraceMetadata(
        schema_version=OBSERVABILITY_SCHEMA_VERSION,
        trace_id=trace_id,
        request_id=request_id,
        execution_id=execution_id,
        attempt_kind=AttemptKind.INITIAL,
        scope_tags=ScopeTags.from_identifiers(
            key=SYNTHETIC_KEY,
            player_id="synthetic_player",
            npc_id="neon_guide",
            conversation_id="00000000-0000-4000-8000-000000000001",
        ),
        persona_version="nia-v1",
        provider_kind=ProviderKind.FAKE,
        record_status=record_status,
        terminal_outcome=terminal_outcome if record_status is not RecordStatus.OPEN else None,
        error_code=TraceErrorCode.NONE,
        reason_code=TraceReasonCode.COMPLETED,
        idempotency_outcome=IdempotencyOutcome.NEW,
        short_term_outcome=ShortTermOutcome.COMMITTED,
        long_term_outcome=LongTermOutcome.EMPTY,
        relationship_outcome=RelationshipOutcome.INERT,
        retryable=False,
        from_cache=False,
        provider_dispatch_count=provider_dispatch_count,
        started_at_utc=started_at,
        finished_at_utc=(
            None if record_status is RecordStatus.OPEN else started_at + timedelta(milliseconds=8)
        ),
        total_latency_ms=8,
        provider_wait_ms=1,
        provider_latency_ms=2,
        context_budget_units=32,
        selected_short_term_turns=1,
        selected_long_term_facts=0,
        input_chars=12,
        output_chars=18,
        prompt_tokens=3,
        completion_tokens=4,
        total_tokens=7,
        cost_micro_usd=0,
    )


def _stages(trace: TraceMetadata) -> tuple[TraceStageMetadata, ...]:
    finished = trace.finished_at_utc or trace.started_at_utc
    return tuple(
        TraceStageMetadata(
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=trace.trace_id,
            stage=stage,
            sequence=sequence,
            outcome=StageOutcome.COMPLETED,
            reason_code=TraceReasonCode.COMPLETED,
            error_code=TraceErrorCode.NONE,
            started_at_utc=trace.started_at_utc,
            finished_at_utc=finished,
            latency_ms=0,
            item_count=0,
        )
        for sequence, stage in enumerate(TraceStage, start=1)
    )


def _repository(tmp_path: Path) -> SqliteObservabilityRepository:
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    return repository


def test_migration_is_independent_strict_and_versioned(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    with sqlite3.connect(repository.database_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        migration = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchone()
        strict_tables = {
            str(row[1]) for row in connection.execute("PRAGMA table_list") if int(row[5]) == 1
        }
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)

    assert OBSERVABILITY_MIGRATIONS == ((1, "0001_observability.sql"),)
    assert {
        "trace_runs",
        "trace_stage_events",
        "execution_links",
        "evaluation_runs",
        "evaluation_cases",
        "replay_index",
    } <= tables
    assert migration is not None and migration[:2] == (1, "0001_observability.sql")
    assert len(str(migration[2])) == 64
    assert {
        "trace_runs",
        "trace_stage_events",
        "execution_links",
        "evaluation_runs",
        "evaluation_cases",
        "replay_index",
    } <= strict_tables


def test_initialize_is_repeatable_and_rejects_migration_drift(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.initialize()

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("UPDATE schema_migrations SET checksum = ?", ("0" * 64,))

    with pytest.raises(ObservabilityStorageError, match="schema"):
        repository.initialize()


def test_repository_rejects_paths_outside_root_and_reparse_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="approved root"):
        SqliteObservabilityRepository(
            database_path=tmp_path.parent / "outside.sqlite3",
            allowed_root=tmp_path,
        )

    original_is_junction = Path.is_junction

    def is_junction(path: Path) -> bool:
        return path == tmp_path or original_is_junction(path)

    monkeypatch.setattr(Path, "is_junction", is_junction)
    with pytest.raises(ValueError, match="symbolic"):
        SqliteObservabilityRepository(
            database_path=tmp_path / "observability.sqlite3",
            allowed_root=tmp_path,
        )


def test_trace_stages_and_execution_link_commit_atomically(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    trace = _trace()

    for stage in _stages(trace):
        repository.record(stage)
    repository.record(trace)

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_runs").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM trace_stage_events").fetchone() == (14,)
        assert connection.execute("SELECT COUNT(*) FROM execution_links").fetchone() == (1,)
        assert connection.execute(
            "SELECT link_kind, provider_dispatch_count FROM execution_links"
        ).fetchone() == ("dispatch_owner", 1)


def test_duplicate_trace_rolls_back_children_and_reports_safe_conflict(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))

    with pytest.raises(ObservabilityConflictError, match="already exists"):
        repository.save_trace(trace, _stages(trace))

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_runs").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM trace_stage_events").fetchone() == (14,)


def test_incomplete_or_cross_trace_stage_set_fails_before_persistence(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    trace = _trace()

    with pytest.raises(ValueError, match="stage set"):
        repository.save_trace(trace, _stages(trace)[:-1])
    foreign_stage = replace(_stages(trace)[0], trace_id=uuid4())
    with pytest.raises(ValueError, match="stage set"):
        repository.save_trace(trace, (foreign_stage, *_stages(trace)[1:]))

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_runs").fetchone() == (0,)


def test_execution_has_at_most_one_dispatch_owner(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    execution_id = uuid4()
    first = _trace(execution_id=execution_id)
    repository.save_trace(first, _stages(first))
    second = _trace(execution_id=execution_id)

    with pytest.raises(ObservabilityConflictError):
        repository.save_trace(second, _stages(second))


def test_evaluation_report_and_cases_are_metadata_only(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    report = evaluate_observability(
        fixture,
        build_baseline_observations(fixture),
        SYNTHETIC_KEY,
    )

    repository.save_evaluation(
        run_id=uuid4(),
        report=report,
        started_at_utc=NOW,
        finished_at_utc=NOW + timedelta(seconds=1),
    )

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone() == (1,)
        assert connection.execute("SELECT COUNT(*) FROM evaluation_cases").fetchone() == (24,)
        assert connection.execute(
            "SELECT forbidden_content_hit_count, scope_leak_count FROM evaluation_runs"
        ).fetchone() == (0, 0)
    rows = repository.query_evaluations(limit=1)
    assert len(rows) == 1
    assert set(rows[0]) == repository.EVALUATION_QUERY_FIELDS


def test_replay_index_separates_real_metadata_from_synthetic_fixture(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))
    real = ReplayIndexEntry.metadata_only(
        replay_id=uuid4(),
        trace=trace,
        digest="1" * 64,
        created_at_utc=NOW,
    )
    synthetic = ReplayIndexEntry.synthetic_fixture(
        replay_id=uuid4(),
        fixture_version="f-008-observability-fixture-v1",
        case_id="persona-nia",
        evaluator_version="f-008-evaluator-v1",
        persona_version="nia-v1",
        digest="2" * 64,
        created_at_utc=NOW,
    )

    repository.save_replay_index(real)
    repository.save_replay_index(synthetic)

    with sqlite3.connect(repository.database_path) as connection:
        rows = connection.execute(
            "SELECT execution_mode, trace_id, fixture_version, case_id "
            "FROM replay_index ORDER BY execution_mode"
        ).fetchall()
    assert rows == [
        (ReplayMode.METADATA_ONLY_NOT_EXECUTABLE.value, str(trace.trace_id), None, None),
        (
            ReplayMode.SYNTHETIC_FIXTURE_EXECUTABLE.value,
            None,
            "f-008-observability-fixture-v1",
            "persona-nia",
        ),
    ]
    query_rows = repository.query_replay_index(limit=2)
    assert len(query_rows) == 2
    assert all(set(row) == repository.REPLAY_QUERY_FIELDS for row in query_rows)


def test_retention_marks_terminal_rows_without_deleting_or_touching_open_trace(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    old = _trace(started_at=NOW - timedelta(days=8))
    recent = _trace(started_at=NOW - timedelta(days=1))
    opened = _trace(
        started_at=NOW - timedelta(days=40),
        record_status=RecordStatus.OPEN,
        terminal_outcome=TerminalOutcome.COMPLETED,
    )
    repository.save_trace(old, _stages(old))
    repository.save_trace(recent, _stages(recent))
    repository.save_trace(opened, _stages(opened))

    summary = repository.mark_expired(now_utc=NOW)

    assert summary.trace_count == 1
    with sqlite3.connect(repository.database_path) as connection:
        rows = connection.execute(
            "SELECT trace_id, retention_status FROM trace_runs ORDER BY trace_id"
        ).fetchall()
        assert len(rows) == 3
        status_by_id = {UUID(row[0]): row[1] for row in rows}
        assert status_by_id[old.trace_id] == "expired"
        assert status_by_id[recent.trace_id] == "active"
        assert status_by_id[opened.trace_id] == "active"
        assert connection.execute("SELECT COUNT(*) FROM trace_stage_events").fetchone() == (42,)


def test_retention_count_caps_mark_oldest_trace_and_evaluation_without_deleting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sqlite_observability, "_TRACE_RETENTION_COUNT", 2)
    monkeypatch.setattr(sqlite_observability, "_EVALUATION_RETENTION_COUNT", 2)
    repository = _repository(tmp_path)
    traces = tuple(_trace(started_at=NOW - timedelta(hours=offset)) for offset in (3, 2, 1))
    for trace in traces:
        repository.save_trace(trace, _stages(trace))

    fixture = load_evaluation_fixture(FIXTURE_PATH)
    report = evaluate_observability(
        fixture,
        build_baseline_observations(fixture),
        SYNTHETIC_KEY,
    )
    run_ids = (uuid4(), uuid4(), uuid4())
    for offset, run_id in zip((3, 2, 1), run_ids, strict=True):
        repository.save_evaluation(
            run_id=run_id,
            report=report,
            started_at_utc=NOW - timedelta(hours=offset),
            finished_at_utc=NOW - timedelta(hours=offset) + timedelta(seconds=1),
        )

    summary = repository.mark_expired(now_utc=NOW)

    assert summary.trace_count == 1
    assert summary.stage_count == 14
    assert summary.evaluation_count == 1
    assert summary.evaluation_case_count == 24
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_runs").fetchone() == (3,)
        assert connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone() == (3,)
        assert connection.execute("SELECT COUNT(*) FROM evaluation_cases").fetchone() == (72,)


def test_lock_conflict_rolls_back_without_partial_trace(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    blocker = sqlite3.connect(repository.database_path, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    trace = _trace()
    try:
        with pytest.raises(ObservabilityStorageError, match="unavailable"):
            repository.save_trace(trace, _stages(trace))
    finally:
        blocker.rollback()
        blocker.close()

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_runs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM trace_stage_events").fetchone() == (0,)


def test_sqlite_recorder_failure_isolated_by_dialogue_observability_boundary(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "uninitialized.sqlite3",
        allowed_root=tmp_path,
    )
    boundary = DialogueObservability(recorder=repository, scope_key=SYNTHETIC_KEY)

    boundary.record_validation_failure(uuid4())

    assert "observability_unavailable" in caplog.text
    assert len(repository.snapshot()) == 0


def test_wrong_schema_and_corrupt_storage_fail_closed_with_safe_errors(tmp_path: Path) -> None:
    wrong = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(wrong) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    repository = SqliteObservabilityRepository(database_path=wrong, allowed_root=tmp_path)
    with pytest.raises(ObservabilityStorageError, match="schema") as wrong_error:
        repository.initialize()
    assert str(wrong) not in str(wrong_error.value)

    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"synthetic-corrupt-database")
    repository = SqliteObservabilityRepository(database_path=corrupt, allowed_root=tmp_path)
    with pytest.raises(ObservabilityStorageError, match="unavailable") as corrupt_error:
        repository.initialize()
    assert str(corrupt) not in str(corrupt_error.value)


def test_query_is_allowlisted_bounded_and_does_not_create_missing_database(tmp_path: Path) -> None:
    missing = SqliteObservabilityRepository(
        database_path=tmp_path / "missing.sqlite3",
        allowed_root=tmp_path,
    )
    with pytest.raises(ObservabilityStorageError, match="unavailable"):
        missing.query_traces(ObservabilityQuery())
    assert not missing.database_path.exists()

    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))
    rows = repository.query_traces(
        ObservabilityQuery(trace_id=trace.trace_id, persona_version="nia-v1", limit=1)
    )
    assert len(rows) == 1
    assert set(rows[0]) == repository.TRACE_QUERY_FIELDS
    with pytest.raises(ValueError, match="limit"):
        ObservabilityQuery(limit=201)


def test_database_and_query_surfaces_contain_no_forbidden_payload(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    trace = _trace()
    repository.save_trace(trace, _stages(trace))
    surfaces = [
        repository.database_path.read_bytes().decode("latin-1"),
        repr(repository),
        repr(repository.query_traces(ObservabilityQuery())),
    ]
    for sidecar in (
        Path(f"{repository.database_path}-wal"),
        Path(f"{repository.database_path}-shm"),
    ):
        if sidecar.exists():
            surfaces.append(sidecar.read_bytes().decode("latin-1"))

    forbidden = (
        "raw-player-sentinel",
        "raw-npc-sentinel",
        "raw-conversation-sentinel",
        "message-sentinel",
        "reply-sentinel",
        "system-prompt-sentinel",
        "memory-body-sentinel",
        "relationship-suggestion-sentinel",
        "provider-body-sentinel",
        "api-key-sentinel",
    )
    assert all(value not in surface for value in forbidden for surface in surfaces)

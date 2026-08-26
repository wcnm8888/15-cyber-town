from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from cyber_town.application.observability import (
    DialogueObservability,
    ProviderKind,
    RecordStatus,
    StageOutcome,
    TerminalOutcome,
    TraceReasonCode,
    TraceStage,
)
from cyber_town.application.observability_evaluation import (
    load_evaluation_fixture,
    replay_synthetic_case,
)
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.observability.sqlite_observability import (
    ObservabilityQuery,
    ReplayIndexEntry,
    ReplayMode,
    SqliteObservabilityRepository,
)
from test_observability_integration import (
    completion,
    request,
    run,
    service,
)
from test_sqlite_observability import _stages, _trace

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "f008_observability_evaluation_v1.json"
SYNTHETIC_KEY = b"f008-step5-synthetic-key-not-for-production"


def test_synthetic_fixture_replays_one_exact_case_with_stable_metadata_digest() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)

    first = replay_synthetic_case(
        fixture=fixture,
        case_id="persona-nia",
        scope_key=SYNTHETIC_KEY,
    )
    second = replay_synthetic_case(
        fixture=fixture,
        case_id="persona-nia",
        scope_key=SYNTHETIC_KEY,
    )

    assert first == second
    assert first.case_id == "persona-nia"
    assert first.passed is True
    assert len(first.canonical_digest) == 64
    assert set(first.as_dict()) == {
        "evaluator_version",
        "fixture_version",
        "schema_version",
        "case_id",
        "dimension",
        "passed",
        "failure_code",
        "canonical_digest",
    }


def test_synthetic_replay_rejects_unknown_case_without_echoing_identifier() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    unknown = "unknown_case_payload_must_not_echo"

    try:
        replay_synthetic_case(fixture=fixture, case_id=unknown, scope_key=SYNTHETIC_KEY)
    except ValueError as error:
        assert str(error) == "Synthetic replay case is unavailable"
        assert unknown not in repr(error)
    else:
        raise AssertionError("Unknown synthetic replay case was accepted")


def test_synthetic_replay_index_resolves_to_exact_versioned_case(tmp_path: Path) -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    result = replay_synthetic_case(
        fixture=fixture,
        case_id="persona-rhea",
        scope_key=SYNTHETIC_KEY,
    )
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    repository.save_replay_index(
        ReplayIndexEntry.synthetic_fixture(
            replay_id=uuid4(),
            fixture_version=result.fixture_version,
            case_id=result.case_id,
            evaluator_version=result.evaluator_version,
            persona_version="rhea-v1",
            digest=result.canonical_digest,
            created_at_utc=datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
        )
    )

    indexed = repository.query_replay_index(limit=1)[0]
    assert indexed["execution_mode"] == ReplayMode.SYNTHETIC_FIXTURE_EXECUTABLE.value
    assert indexed["fixture_version"] == result.fixture_version
    assert indexed["case_id"] == result.case_id
    assert indexed["digest"] == result.canonical_digest


def test_durable_recorder_persists_open_trace_and_initial_stages(tmp_path: Path) -> None:
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    observability = DialogueObservability(
        recorder=repository,
        scope_key=SYNTHETIC_KEY,
        provider_kind=ProviderKind.FAKE,
        wall_clock=lambda: datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
        monotonic_clock=lambda: 1.0,
    )

    trace = observability.start_validated(
        trace_id=uuid4(),
        request_id=uuid4(),
        player_id="synthetic_player",
        npc_id="neon_guide",
        conversation_id=uuid4(),
        input_chars=9,
    )

    assert trace is not None
    summaries = repository.query_traces(ObservabilityQuery(limit=10))
    assert len(summaries) == 1
    assert summaries[0]["record_status"] == "open"
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trace_stage_events").fetchone() == (2,)


def test_durable_recorder_finalizes_all_stages_and_restart_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    observability = DialogueObservability(
        recorder=repository,
        scope_key=SYNTHETIC_KEY,
        provider_kind=ProviderKind.FAKE,
        wall_clock=lambda: datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
        monotonic_clock=lambda: 1.0,
    )
    trace = observability.start_validated(
        trace_id=uuid4(),
        request_id=uuid4(),
        player_id="synthetic_player",
        npc_id="signal_archivist",
        conversation_id=uuid4(),
        input_chars=5,
    )
    assert trace is not None
    trace.persona_version = "ivo-v1"
    trace.stage(TraceStage.PERSONA_RESOLUTION, StageOutcome.COMPLETED)
    trace.finish(
        terminal_outcome=TerminalOutcome.COMPLETED,
        reason_code=TraceReasonCode.COMPLETED,
    )

    summaries = repository.query_traces(ObservabilityQuery(limit=10))
    assert len(summaries) == 1
    assert summaries[0]["record_status"] == "complete"
    assert summaries[0]["terminal_outcome"] == "completed"
    with sqlite3.connect(repository.database_path) as connection:
        stages = connection.execute(
            "SELECT stage FROM trace_stage_events ORDER BY sequence"
        ).fetchall()
    assert tuple(stage for (stage,) in stages) == tuple(stage.value for stage in TraceStage)
    assert repository.recover_open_traces(now_utc=datetime(2026, 8, 26, 9, 0, tzinfo=UTC)) == 0


def test_sqlite_recorder_captures_real_fake_dialogue_without_raw_payload(
    tmp_path: Path,
) -> None:
    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    completion_provider = FakeProvider([completion()])
    application = service(completion_provider, repository)

    response = run(application.execute(request(), trace_id=uuid4()))

    assert response.status.value == "completed"
    assert completion_provider.call_count == 1
    summaries = repository.query_traces(ObservabilityQuery(limit=10))
    assert len(summaries) == 1
    assert summaries[0]["record_status"] == "complete"
    assert summaries[0]["provider_dispatch_count"] == 1
    forbidden = (
        b"synthetic_player",
        b"neon_guide",
        b"Synthetic safe message",
        b"Synthetic safe reply",
    )
    surfaces = tuple(
        path.read_bytes()
        for path in (
            repository.database_path,
            Path(f"{repository.database_path}-wal"),
            Path(f"{repository.database_path}-shm"),
        )
        if path.is_file()
    )
    assert all(value not in surface for value in forbidden for surface in surfaces)


def _percentile(samples: list[float], percentile: float) -> float:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def test_fake_only_recorder_performance_and_growth_baseline(tmp_path: Path) -> None:
    sample_count = 30
    no_recorder = DialogueObservability()
    no_recorder_samples: list[float] = []
    no_recorder_started = perf_counter()
    for _ in range(sample_count):
        sample_started = perf_counter()
        assert (
            no_recorder.start_validated(
                trace_id=uuid4(),
                request_id=uuid4(),
                player_id="synthetic_player",
                npc_id="neon_guide",
                conversation_id=uuid4(),
                input_chars=8,
            )
            is None
        )
        no_recorder_samples.append((perf_counter() - sample_started) * 1_000)
    no_recorder_elapsed = perf_counter() - no_recorder_started

    repository = SqliteObservabilityRepository(
        database_path=tmp_path / "observability.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    initial_size = repository.database_path.stat().st_size
    sqlite_observability = DialogueObservability(
        recorder=repository,
        scope_key=SYNTHETIC_KEY,
        provider_kind=ProviderKind.FAKE,
    )
    sqlite_samples: list[float] = []
    sqlite_started = perf_counter()
    for _ in range(sample_count):
        sample_started = perf_counter()
        trace = sqlite_observability.start_validated(
            trace_id=uuid4(),
            request_id=uuid4(),
            player_id="synthetic_player",
            npc_id="night_courier",
            conversation_id=uuid4(),
            input_chars=8,
        )
        assert trace is not None
        trace.persona_version = "rhea-v1"
        trace.stage(TraceStage.PERSONA_RESOLUTION)
        trace.finish(
            terminal_outcome=TerminalOutcome.COMPLETED,
            reason_code=TraceReasonCode.COMPLETED,
        )
        sqlite_samples.append((perf_counter() - sample_started) * 1_000)
    sqlite_elapsed = perf_counter() - sqlite_started
    final_size = repository.database_path.stat().st_size

    baseline = {
        "sample_count": sample_count,
        "no_recorder": {
            "p50_ms": round(_percentile(no_recorder_samples, 0.50), 3),
            "p95_ms": round(_percentile(no_recorder_samples, 0.95), 3),
            "p99_ms": round(_percentile(no_recorder_samples, 0.99), 3),
            "throughput_per_second": round(sample_count / no_recorder_elapsed, 3),
            "database_growth_bytes": 0,
        },
        "sqlite_recorder": {
            "p50_ms": round(_percentile(sqlite_samples, 0.50), 3),
            "p95_ms": round(_percentile(sqlite_samples, 0.95), 3),
            "p99_ms": round(_percentile(sqlite_samples, 0.99), 3),
            "throughput_per_second": round(sample_count / sqlite_elapsed, 3),
            "database_growth_bytes": final_size - initial_size,
        },
    }
    print("STEP5_PERFORMANCE=" + json.dumps(baseline, sort_keys=True))
    assert final_size > initial_size
    assert len(repository.query_traces(ObservabilityQuery(limit=sample_count))) == sample_count


def test_restart_recovers_only_open_traces_as_abandoned(tmp_path: Path) -> None:
    database_path = tmp_path / "observability.sqlite3"
    repository = SqliteObservabilityRepository(
        database_path=database_path,
        allowed_root=tmp_path,
    )
    repository.initialize()
    open_trace = _trace(record_status=RecordStatus.OPEN)
    completed_trace = _trace(started_at=open_trace.started_at_utc + timedelta(seconds=1))
    repository.save_trace(open_trace, _stages(open_trace))
    repository.save_trace(completed_trace, _stages(completed_trace))

    restarted = SqliteObservabilityRepository(
        database_path=database_path,
        allowed_root=tmp_path,
    )
    restarted.initialize()
    recovered_count = restarted.recover_open_traces(now_utc=datetime(2026, 8, 26, 9, 0, tzinfo=UTC))

    traces = restarted.query_traces(ObservabilityQuery(limit=10))
    by_trace = {trace["trace_id"]: trace for trace in traces}
    assert recovered_count == 1
    assert by_trace[str(open_trace.trace_id)]["record_status"] == "partial"
    assert by_trace[str(open_trace.trace_id)]["terminal_outcome"] == (
        TerminalOutcome.ABANDONED_AFTER_RESTART.value
    )
    assert by_trace[str(open_trace.trace_id)]["reason_code"] == "restart_recovery"
    assert by_trace[str(completed_trace.trace_id)]["record_status"] == "complete"
    assert by_trace[str(completed_trace.trace_id)]["terminal_outcome"] == "completed"

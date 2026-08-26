from __future__ import annotations

import hashlib
import hmac
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from cyber_town.application.observability import (
    OBSERVABILITY_SCHEMA_VERSION,
    AttemptKind,
    IdempotencyOutcome,
    InMemoryObservabilityRecorder,
    LongTermOutcome,
    NoOpObservabilityRecorder,
    ObservabilityRecorder,
    ProviderKind,
    RecordStatus,
    RelationshipOutcome,
    ScopeDimension,
    ScopeTags,
    ShortTermOutcome,
    StageOutcome,
    TerminalOutcome,
    TraceErrorCode,
    TraceLinkageError,
    TraceMetadata,
    TraceReasonCode,
    TraceStage,
    TraceStageMetadata,
    derive_scope_tag,
    validate_trace_linkage,
)

TRACE_ID = UUID("11111111-1111-4111-8111-111111111111")
SECOND_TRACE_ID = UUID("22222222-2222-4222-8222-222222222222")
THIRD_TRACE_ID = UUID("33333333-3333-4333-8333-333333333333")
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
EXECUTION_ID = UUID("55555555-5555-4555-8555-555555555555")
STARTED_AT = datetime(2026, 8, 26, 6, 30, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(milliseconds=25)
SYNTHETIC_HMAC_KEY = b"synthetic-f008-scope-key-material"


def scope_tags() -> ScopeTags:
    return ScopeTags.from_identifiers(
        key=SYNTHETIC_HMAC_KEY,
        player_id="synthetic_player",
        npc_id="neon_guide",
        conversation_id="66666666-6666-4666-8666-666666666666",
    )


def metadata(**overrides: Any) -> TraceMetadata:
    values: dict[str, object] = {
        "schema_version": OBSERVABILITY_SCHEMA_VERSION,
        "trace_id": TRACE_ID,
        "request_id": REQUEST_ID,
        "execution_id": EXECUTION_ID,
        "attempt_kind": AttemptKind.INITIAL,
        "scope_tags": scope_tags(),
        "persona_version": "nia-v1",
        "provider_kind": ProviderKind.FAKE,
        "record_status": RecordStatus.COMPLETE,
        "terminal_outcome": TerminalOutcome.COMPLETED,
        "error_code": TraceErrorCode.NONE,
        "reason_code": TraceReasonCode.COMPLETED,
        "idempotency_outcome": IdempotencyOutcome.NEW,
        "short_term_outcome": ShortTermOutcome.COMMITTED,
        "long_term_outcome": LongTermOutcome.EMPTY,
        "relationship_outcome": RelationshipOutcome.APPLIED,
        "retryable": False,
        "from_cache": False,
        "provider_dispatch_count": 1,
        "started_at_utc": STARTED_AT,
        "finished_at_utc": FINISHED_AT,
        "total_latency_ms": 25,
        "provider_wait_ms": 2,
        "provider_latency_ms": 20,
        "context_budget_units": 512,
        "selected_short_term_turns": 2,
        "selected_long_term_facts": 1,
        "input_chars": 14,
        "output_chars": 22,
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "total_tokens": 13,
        "cost_micro_usd": 0,
    }
    values.update(overrides)
    return TraceMetadata(**values)  # type: ignore[arg-type]


def test_observability_enums_are_exact_and_versioned() -> None:
    assert OBSERVABILITY_SCHEMA_VERSION == 1
    assert {stage.value for stage in TraceStage} == {
        "http_received",
        "request_validation",
        "persona_resolution",
        "idempotency_resolution",
        "scope_lock",
        "short_term_selection",
        "long_term_retrieval",
        "context_budget_selection",
        "provider_queue",
        "provider_completion",
        "relationship_evaluation",
        "state_commit",
        "response_mapping",
        "terminal",
    }
    assert {outcome.value for outcome in TerminalOutcome} == {
        "completed",
        "degraded",
        "rejected",
        "failed",
        "cancelled",
        "orphaned",
        "replayed",
        "conflict",
        "abandoned_after_restart",
    }
    assert {kind.value for kind in ProviderKind} == {
        "fake",
        "deepseek",
        "local-fallback",
        "local-memory",
        "disabled",
        "unknown",
    }
    with pytest.raises(ValueError):
        TraceStage("provider_raw_payload")


@pytest.mark.parametrize("dimension", list(ScopeDimension))
def test_scope_tags_use_versioned_domain_separation(dimension: ScopeDimension) -> None:
    identifier = "synthetic_identifier"
    expected_payload = (
        f"cyber-town:f008:scope:v{OBSERVABILITY_SCHEMA_VERSION}:{dimension.value}\0{identifier}"
    ).encode()

    tag = derive_scope_tag(
        key=SYNTHETIC_HMAC_KEY,
        dimension=dimension,
        identifier=identifier,
    )

    assert tag == hmac.new(SYNTHETIC_HMAC_KEY, expected_payload, hashlib.sha256).hexdigest()
    assert len(tag) == 64
    assert tag == tag.lower()


def test_scope_dimensions_cannot_collapse_for_the_same_identifier() -> None:
    tags = {
        derive_scope_tag(
            key=SYNTHETIC_HMAC_KEY,
            dimension=dimension,
            identifier="same_identifier",
        )
        for dimension in ScopeDimension
    }

    assert len(tags) == len(ScopeDimension)


@pytest.mark.parametrize("bad_key", [None, "secret", b"", b"too-short", bytearray(b"x" * 32)])
def test_scope_tag_rejects_invalid_keys_without_echoing_them(bad_key: object) -> None:
    with pytest.raises((TypeError, ValueError)) as captured:
        derive_scope_tag(
            key=bad_key,  # type: ignore[arg-type]
            dimension=ScopeDimension.PLAYER,
            identifier="safe_identifier",
        )

    assert repr(bad_key) not in str(captured.value)


@pytest.mark.parametrize(
    "bad_identifier",
    [None, 7, True, "", " ", " padded", "padded ", "x" * 65],
)
def test_scope_tag_rejects_invalid_identifiers_without_echoing_them(
    bad_identifier: object,
) -> None:
    with pytest.raises((TypeError, ValueError)) as captured:
        derive_scope_tag(
            key=SYNTHETIC_HMAC_KEY,
            dimension=ScopeDimension.NPC,
            identifier=bad_identifier,  # type: ignore[arg-type]
        )

    assert repr(bad_identifier) not in str(captured.value)


def test_scope_tags_are_strict_frozen_values() -> None:
    tags = scope_tags()

    assert not hasattr(tags, "__dict__")
    assert all(len(value) == 64 for value in tags.as_dict().values())
    with pytest.raises(FrozenInstanceError):
        tags.player_scope_tag = "0" * 64  # type: ignore[misc]
    with pytest.raises(ValueError, match="Scope tag is invalid"):
        ScopeTags("not-a-tag", "0" * 64, "1" * 64)


def test_trace_metadata_is_strict_frozen_and_serializes_only_allowlisted_fields() -> None:
    record = metadata()

    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.retryable = True  # type: ignore[misc]
    assert record.as_dict() == {
        "schema_version": 1,
        "trace_id": str(TRACE_ID),
        "request_id": str(REQUEST_ID),
        "execution_id": str(EXECUTION_ID),
        "attempt_kind": "initial",
        **scope_tags().as_dict(),
        "persona_version": "nia-v1",
        "provider_kind": "fake",
        "record_status": "complete",
        "terminal_outcome": "completed",
        "error_code": "none",
        "reason_code": "completed",
        "idempotency_outcome": "new",
        "short_term_outcome": "committed",
        "long_term_outcome": "empty",
        "relationship_outcome": "applied",
        "retryable": False,
        "from_cache": False,
        "provider_dispatch_count": 1,
        "started_at_utc": "2026-08-26T06:30:00.000Z",
        "finished_at_utc": "2026-08-26T06:30:00.025Z",
        "total_latency_ms": 25,
        "provider_wait_ms": 2,
        "provider_latency_ms": 20,
        "context_budget_units": 512,
        "selected_short_term_turns": 2,
        "selected_long_term_facts": 1,
        "input_chars": 14,
        "output_chars": 22,
        "prompt_tokens": 9,
        "completion_tokens": 4,
        "total_tokens": 13,
        "cost_micro_usd": 0,
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("schema_version", 2),
        ("retryable", 1),
        ("from_cache", 0),
        ("provider_dispatch_count", -1),
        ("provider_dispatch_count", 2),
        ("total_latency_ms", -1),
        ("prompt_tokens", True),
        ("completion_tokens", -1),
        ("cost_micro_usd", 1),
        ("persona_version", "INVALID VERSION"),
    ],
)
def test_trace_metadata_rejects_invalid_values_without_echoing_them(
    field: str,
    bad_value: object,
) -> None:
    with pytest.raises((TypeError, ValueError)) as captured:
        metadata(**{field: bad_value})

    assert repr(bad_value) not in str(captured.value)


def test_trace_metadata_enforces_lifecycle_and_token_invariants() -> None:
    with pytest.raises(ValueError, match="Open trace cannot have a terminal outcome"):
        metadata(record_status=RecordStatus.OPEN)
    with pytest.raises(ValueError, match="Completed trace requires a terminal outcome"):
        metadata(terminal_outcome=None)
    with pytest.raises(ValueError, match="Trace timestamps are inconsistent"):
        metadata(finished_at_utc=STARTED_AT - timedelta(milliseconds=1))
    with pytest.raises(ValueError, match="Token totals are inconsistent"):
        metadata(total_tokens=14)


def test_validation_failure_has_no_trusted_request_scope_or_execution() -> None:
    record = metadata(
        request_id=None,
        execution_id=None,
        attempt_kind=AttemptKind.VALIDATION_FAILURE,
        scope_tags=None,
        persona_version=None,
        provider_kind=ProviderKind.UNKNOWN,
        terminal_outcome=TerminalOutcome.REJECTED,
        error_code=TraceErrorCode.VALIDATION_ERROR,
        reason_code=TraceReasonCode.NOT_REACHED,
        idempotency_outcome=IdempotencyOutcome.NOT_REACHED,
        short_term_outcome=ShortTermOutcome.NOT_REACHED,
        long_term_outcome=LongTermOutcome.NOT_REACHED,
        relationship_outcome=RelationshipOutcome.NOT_REACHED,
        provider_dispatch_count=0,
        total_latency_ms=1,
        provider_wait_ms=0,
        provider_latency_ms=0,
        context_budget_units=0,
        selected_short_term_turns=0,
        selected_long_term_facts=0,
        input_chars=0,
        output_chars=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )

    assert record.request_id is None
    assert record.scope_tags is None
    assert record.as_dict()["player_scope_tag"] is None


def test_non_validation_attempt_requires_request_and_scope() -> None:
    with pytest.raises(ValueError, match="Validated trace requires request and scope metadata"):
        metadata(request_id=None, scope_tags=None)
    with pytest.raises(ValueError, match="Validation failure cannot carry trusted metadata"):
        metadata(attempt_kind=AttemptKind.VALIDATION_FAILURE)


def test_cache_replay_has_no_new_execution_or_provider_dispatch() -> None:
    replay = metadata(
        trace_id=SECOND_TRACE_ID,
        execution_id=None,
        attempt_kind=AttemptKind.CACHE_REPLAY,
        terminal_outcome=TerminalOutcome.REPLAYED,
        reason_code=TraceReasonCode.CACHE_REPLAY,
        idempotency_outcome=IdempotencyOutcome.CACHE_REPLAY,
        from_cache=True,
        provider_dispatch_count=0,
    )

    assert replay.execution_id is None
    with pytest.raises(ValueError, match="Cache replay invariants are inconsistent"):
        replace(replay, provider_dispatch_count=1)


def test_stage_metadata_enforces_order_and_safe_lifecycle() -> None:
    stage = TraceStageMetadata(
        schema_version=OBSERVABILITY_SCHEMA_VERSION,
        trace_id=TRACE_ID,
        stage=TraceStage.PROVIDER_COMPLETION,
        sequence=10,
        outcome=StageOutcome.COMPLETED,
        reason_code=TraceReasonCode.COMPLETED,
        error_code=TraceErrorCode.NONE,
        started_at_utc=STARTED_AT,
        finished_at_utc=FINISHED_AT,
        latency_ms=25,
        item_count=1,
    )

    assert not hasattr(stage, "__dict__")
    assert stage.as_dict()["stage"] == "provider_completion"
    with pytest.raises(ValueError, match="Trace stage sequence is invalid"):
        replace(stage, sequence=9)
    with pytest.raises(ValueError, match="Started stage cannot have a finish timestamp"):
        replace(stage, outcome=StageOutcome.STARTED)


def test_recorders_accept_only_frozen_observability_records() -> None:
    record = metadata()
    stage = TraceStageMetadata(
        schema_version=1,
        trace_id=TRACE_ID,
        stage=TraceStage.TERMINAL,
        sequence=14,
        outcome=StageOutcome.COMPLETED,
        reason_code=TraceReasonCode.COMPLETED,
        error_code=TraceErrorCode.NONE,
        started_at_utc=STARTED_AT,
        finished_at_utc=FINISHED_AT,
        latency_ms=0,
        item_count=0,
    )
    recorder: ObservabilityRecorder = InMemoryObservabilityRecorder()

    recorder.record(record)
    recorder.record(stage)

    assert isinstance(record, TraceMetadata)
    assert recorder.snapshot() == (record, stage)
    NoOpObservabilityRecorder().record(record)
    with pytest.raises(TypeError, match="Observability record type is invalid"):
        recorder.record({"message": "private"})  # type: ignore[arg-type]


def test_linkage_allows_many_traces_for_one_actual_execution() -> None:
    owner = metadata()
    waiter = metadata(
        trace_id=SECOND_TRACE_ID,
        attempt_kind=AttemptKind.CONCURRENT_WAITER,
        idempotency_outcome=IdempotencyOutcome.INFLIGHT_SHARED,
        reason_code=TraceReasonCode.SHARED_EXECUTION,
        provider_dispatch_count=0,
    )

    validate_trace_linkage((owner, waiter))


def test_linkage_rejects_duplicate_trace_or_cross_request_execution() -> None:
    owner = metadata()
    with pytest.raises(TraceLinkageError, match="Trace identifier is duplicated"):
        validate_trace_linkage((owner, owner))

    other_request = metadata(
        trace_id=THIRD_TRACE_ID,
        request_id=UUID("77777777-7777-4777-8777-777777777777"),
        attempt_kind=AttemptKind.CONCURRENT_WAITER,
        idempotency_outcome=IdempotencyOutcome.INFLIGHT_SHARED,
        reason_code=TraceReasonCode.SHARED_EXECUTION,
        provider_dispatch_count=0,
    )
    with pytest.raises(TraceLinkageError, match="Execution crossed logical request scope"):
        validate_trace_linkage((owner, other_request))


def test_forbidden_sentinels_never_reach_serialization_repr_log_or_snapshot(
    caplog: pytest.LogCaptureFixture,
) -> None:
    forbidden = (
        "private-player-sentinel-983401",
        "private-npc-sentinel-983402",
        "private-conversation-sentinel-983403",
        "private-message-sentinel-983404",
        "private-reply-sentinel-983405",
        "private-system-prompt-sentinel-983406",
        "private-memory-sentinel-983407",
        "private-relationship-sentinel-983408",
        "private-provider-body-sentinel-983409",
        "private-api-key-sentinel-983410",
    )
    tags = ScopeTags.from_identifiers(
        key=SYNTHETIC_HMAC_KEY,
        player_id=forbidden[0],
        npc_id=forbidden[1],
        conversation_id=forbidden[2],
    )
    record = metadata(scope_tags=tags)
    recorder = InMemoryObservabilityRecorder()
    recorder.record(record)
    surfaces = "\n".join(
        (
            repr(tags),
            repr(record),
            repr(record.as_dict()),
            repr(recorder),
            repr(recorder.snapshot()),
            caplog.text,
        )
    )

    for sentinel in forbidden:
        assert sentinel not in surfaces

    payload = metadata().__class__
    with pytest.raises(TypeError) as captured:
        payload(message=forbidden[3])  # type: ignore[call-arg]
    assert forbidden[3] not in str(captured.value)

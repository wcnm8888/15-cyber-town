from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from cyber_town.api.app import create_app
from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.memory import ConversationScope, ShortTermSessionStore
from cyber_town.application.observability import (
    AttemptKind,
    IdempotencyOutcome,
    InMemoryObservabilityRecorder,
    LongTermOutcome,
    ObservabilityRecord,
    ProviderKind,
    RelationshipOutcome,
    ShortTermOutcome,
    StageOutcome,
    TerminalOutcome,
    TraceErrorCode,
    TraceMetadata,
    TraceReasonCode,
    TraceStage,
    TraceStageMetadata,
    validate_trace_linkage,
)
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderLongTermFact,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.contracts.v1 import DialogueRequestV1, DialogueStatus
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import LongTermMemoryStorageError
from cyber_town.infrastructure.persistence.sqlite_relationship import RelationshipStorageError

SYNTHETIC_SCOPE_KEY = b"synthetic-f008-step2-scope-key"
REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")
TRACE_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_TRACE_ID = UUID("44444444-4444-4444-8444-444444444444")


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def completion(
    content: object = "Synthetic safe reply",
    *,
    finish_reason: object = "stop",
    relationship_suggestion: object = None,
) -> ProviderCompletion:
    return ProviderCompletion(
        content=content,
        finish_reason=finish_reason,
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="fake-model",
        usage=ProviderUsage(prompt_tokens=7, completion_tokens=3),
        relationship_suggestion=relationship_suggestion,
    )


def request(
    *,
    message: str = "Synthetic safe message",
    npc_id: str = "neon_guide",
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=REQUEST_ID,
        player_id="synthetic_player",
        npc_id=npc_id,
        conversation_id=CONVERSATION_ID,
        message=message,
    )


def service(
    provider: Any,
    recorder: Any,
    **overrides: Any,
) -> DialogueService:
    values: dict[str, object] = {
        "personas": {"neon_guide": load_bundled_persona("nia_v1.json")},
        "provider": provider,
        "config": DialogueExecutionConfig(
            model="fake-model",
            temperature=0.0,
            max_tokens=64,
            timeout_seconds=2.0,
            max_concurrency=2,
            idempotency_ttl_seconds=60.0,
            idempotency_max_entries=32,
        ),
        "observability_recorder": recorder,
        "observability_scope_key": SYNTHETIC_SCOPE_KEY,
        "observability_provider_kind": ProviderKind.FAKE,
    }
    values.update(overrides)
    return DialogueService(**values)  # type: ignore[arg-type]


def traces(recorder: InMemoryObservabilityRecorder) -> tuple[TraceMetadata, ...]:
    return tuple(item for item in recorder.snapshot() if isinstance(item, TraceMetadata))


def stages(recorder: InMemoryObservabilityRecorder) -> tuple[TraceStageMetadata, ...]:
    return tuple(item for item in recorder.snapshot() if isinstance(item, TraceStageMetadata))


def test_completed_request_records_allowlisted_end_to_end_metadata() -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([completion()])

    response = run(service(provider, recorder).execute(request(), trace_id=TRACE_ID))

    assert response.status is DialogueStatus.COMPLETED
    assert provider.call_count == 1
    assert {item.stage for item in stages(recorder)} == set(TraceStage)
    trace = traces(recorder)[0]
    assert trace.trace_id == TRACE_ID
    assert trace.request_id == REQUEST_ID
    assert trace.execution_id is not None
    assert trace.attempt_kind is AttemptKind.INITIAL
    assert trace.idempotency_outcome is IdempotencyOutcome.NEW
    assert trace.short_term_outcome is ShortTermOutcome.COMMITTED
    assert trace.long_term_outcome is LongTermOutcome.NOT_CONFIGURED
    assert trace.relationship_outcome is RelationshipOutcome.NOT_CONFIGURED
    assert trace.terminal_outcome is TerminalOutcome.COMPLETED
    assert trace.provider_dispatch_count == 1
    assert trace.prompt_tokens == 7
    assert trace.completion_tokens == 3
    assert trace.scope_tags is not None
    assert all(len(value) == 64 for value in trace.scope_tags.as_dict().values())


def test_cache_replay_has_a_new_trace_without_execution_or_dispatch() -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([completion()])
    application = service(provider, recorder)

    run(application.execute(request(), trace_id=TRACE_ID))
    run(application.execute(request(), trace_id=SECOND_TRACE_ID))

    recorded = traces(recorder)
    assert len(recorded) == 2
    owner, replay = recorded
    assert owner.execution_id is not None
    assert replay.trace_id == SECOND_TRACE_ID
    assert replay.execution_id is None
    assert replay.attempt_kind is AttemptKind.CACHE_REPLAY
    assert replay.idempotency_outcome is IdempotencyOutcome.CACHE_REPLAY
    assert replay.terminal_outcome is TerminalOutcome.REPLAYED
    assert replay.provider_dispatch_count == 0
    assert replay.total_tokens == 0
    assert replay.provider_latency_ms == 0
    assert provider.call_count == 1
    validate_trace_linkage(recorded)


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.call_count = 0

    async def complete(self, provider_request: ProviderRequest) -> ProviderCompletion:
        del provider_request
        self.call_count += 1
        self.started.set()
        await self.release.wait()
        return completion()


async def exercise_shared_execution() -> tuple[tuple[TraceMetadata, ...], int]:
    recorder = InMemoryObservabilityRecorder()
    provider = BlockingProvider()
    application = service(provider, recorder)
    owner = asyncio.create_task(application.execute(request(), trace_id=TRACE_ID))
    await provider.started.wait()
    waiter = asyncio.create_task(application.execute(request(), trace_id=SECOND_TRACE_ID))
    await asyncio.sleep(0)
    provider.release.set()
    await asyncio.gather(owner, waiter)
    return traces(recorder), provider.call_count


def test_concurrent_waiter_shares_only_the_actual_execution() -> None:
    recorded, call_count = run(exercise_shared_execution())

    assert call_count == 1
    assert len(recorded) == 2
    owner = next(item for item in recorded if item.attempt_kind is AttemptKind.INITIAL)
    waiter = next(item for item in recorded if item.attempt_kind is AttemptKind.CONCURRENT_WAITER)
    assert owner.execution_id == waiter.execution_id
    assert owner.provider_dispatch_count == 1
    assert waiter.provider_dispatch_count == 0
    assert waiter.total_tokens == 0
    assert waiter.provider_latency_ms == 0
    assert waiter.idempotency_outcome is IdempotencyOutcome.INFLIGHT_SHARED
    validate_trace_linkage(recorded)


def test_unknown_npc_is_rejected_before_provider_and_state_stages() -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([completion()])

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service(provider, recorder).execute(request(npc_id="unknown_npc"), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.NPC_NOT_FOUND
    trace = traces(recorder)[0]
    assert trace.terminal_outcome is TerminalOutcome.REJECTED
    assert trace.error_code is TraceErrorCode.NPC_NOT_FOUND
    assert trace.execution_id is None
    assert trace.provider_dispatch_count == 0
    assert provider.call_count == 0
    persona_stage = next(
        item for item in stages(recorder) if item.stage is TraceStage.PERSONA_RESOLUTION
    )
    assert persona_stage.outcome is StageOutcome.FAILED


@pytest.mark.anyio
async def test_http_validation_failure_records_no_untrusted_scope_or_request() -> None:
    recorder = InMemoryObservabilityRecorder()
    application = create_app(observability_recorder=recorder)
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    payload = {
        "request_id": str(REQUEST_ID),
        "player_id": "private-invalid-player",
        "npc_id": "neon_guide",
        "conversation_id": str(CONVERSATION_ID),
        "message": "private-invalid-message",
        "unexpected": True,
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/dialogue", json=payload)

    assert response.status_code == 422
    trace = traces(recorder)[0]
    assert trace.trace_id == UUID(response.json()["trace_id"])
    assert trace.attempt_kind is AttemptKind.VALIDATION_FAILURE
    assert trace.request_id is None
    assert trace.scope_tags is None
    assert trace.execution_id is None
    assert trace.provider_dispatch_count == 0
    assert trace.error_code is TraceErrorCode.VALIDATION_ERROR
    serialized = repr(tuple(item.as_dict() for item in recorder.snapshot()))
    assert "private-invalid-player" not in serialized
    assert "private-invalid-message" not in serialized


@pytest.mark.anyio
async def test_http_success_preserves_v1_and_matches_the_internal_trace() -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([completion()])
    application = create_app(dialogue_service=service(provider, recorder))
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/dialogue",
            json=request().model_dump(mode="json"),
        )

    assert response.status_code == 200
    assert set(response.json()) == {
        "request_id",
        "trace_id",
        "npc_id",
        "conversation_id",
        "reply",
        "status",
        "provider",
    }
    assert traces(recorder)[0].trace_id == UUID(response.json()["trace_id"])


@pytest.mark.parametrize(
    ("provider_outcome", "error_code"),
    [
        (ProviderTimeoutError("private-provider-detail"), TraceErrorCode.PROVIDER_TIMEOUT),
        (
            ProviderUnavailableError("private-unavailable-detail"),
            TraceErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            ProviderCompletion(
                content="private-provider-body",
                finish_reason="length",
                choice_count=1,
                tool_calls_present=False,
                reasoning_content_present=False,
                provider="fake",
                model="fake-model",
            ),
            TraceErrorCode.PROVIDER_INVALID_RESPONSE,
        ),
    ],
)
def test_provider_failures_are_classified_without_details(
    provider_outcome: ProviderCompletion | Exception,
    error_code: TraceErrorCode,
) -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([provider_outcome])

    with pytest.raises(DialogueUseCaseError):
        run(service(provider, recorder).execute(request(), trace_id=TRACE_ID))

    trace = traces(recorder)[0]
    assert trace.error_code is error_code
    assert trace.terminal_outcome is TerminalOutcome.FAILED
    surfaces = repr(tuple(item.as_dict() for item in recorder.snapshot()))
    assert "private-provider-detail" not in surfaces
    assert "private-unavailable-detail" not in surfaces
    assert "private-provider-body" not in surfaces


class RaisingRecorder:
    def record(self, record: ObservabilityRecord) -> None:
        del record
        raise RuntimeError("private-recorder-detail")

    def snapshot(self) -> tuple[ObservabilityRecord, ...]:
        raise RuntimeError("private-recorder-detail")


def test_recorder_failure_cannot_change_dialogue_or_duplicate_provider(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = FakeProvider([completion(relationship_suggestion={"category": "neutral"})])
    relationships = SyntheticRelationshipService()
    sessions = ShortTermSessionStore()
    application = service(
        provider,
        RaisingRecorder(),
        relationship_service=relationships,
        session_store=sessions,
    )

    with caplog.at_level(logging.WARNING):
        response = run(application.execute(request(), trace_id=TRACE_ID))
        replay = run(application.execute(request(), trace_id=SECOND_TRACE_ID))

    assert response.status is DialogueStatus.COMPLETED
    assert replay.status is DialogueStatus.COMPLETED
    assert provider.call_count == 1
    assert relationships.call_count == 1
    scope = ConversationScope("synthetic_player", "neon_guide", CONVERSATION_ID)
    assert len(sessions.history(scope)) == 1
    assert "private-recorder-detail" not in caplog.text


@pytest.mark.anyio
async def test_validation_recorder_failure_preserves_the_public_422() -> None:
    application = create_app(observability_recorder=RaisingRecorder())
    transport = ASGITransport(app=application, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/dialogue", json={"private": "invalid"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_content_filter_degradation_and_logs_contain_no_raw_scope_or_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = InMemoryObservabilityRecorder()
    private_message = "private-message-step2-sentinel"
    provider = FakeProvider(
        [completion("private-reply-step2-sentinel", finish_reason="content_filter")]
    )

    with caplog.at_level(logging.INFO, logger="cyber_town.dialogue"):
        response = run(
            service(provider, recorder).execute(
                request(message=private_message),
                trace_id=TRACE_ID,
            )
        )

    trace = traces(recorder)[0]
    assert response.status is DialogueStatus.DEGRADED
    assert trace.terminal_outcome is TerminalOutcome.DEGRADED
    assert trace.reason_code is TraceReasonCode.DEGRADED_CONTENT_FILTER
    assert trace.provider_kind is ProviderKind.LOCAL_FALLBACK
    surfaces = caplog.text + repr(tuple(vars(item) for item in caplog.records))
    for forbidden in (
        "synthetic_player",
        "neon_guide",
        str(CONVERSATION_ID),
        private_message,
        "private-reply-step2-sentinel",
    ):
        assert forbidden not in surfaces


def test_retry_after_failed_execution_gets_a_new_execution_identifier() -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([ProviderTimeoutError("private-first-failure"), completion()])
    application = service(provider, recorder)

    with pytest.raises(DialogueUseCaseError):
        run(application.execute(request(), trace_id=TRACE_ID))
    response = run(application.execute(request(), trace_id=SECOND_TRACE_ID))

    assert response.status is DialogueStatus.COMPLETED
    first, retry = traces(recorder)
    assert first.attempt_kind is AttemptKind.INITIAL
    assert retry.attempt_kind is AttemptKind.RETRY
    assert first.execution_id is not None
    assert retry.execution_id is not None
    assert first.execution_id != retry.execution_id
    assert provider.call_count == 2


class SyntheticRetriever:
    def retrieve(self, scope: object, message: str) -> tuple[ProviderLongTermFact, ...]:
        del scope, message
        return (ProviderLongTermFact("game_alias", "Synthetic_Alias"),)

    def is_recall_request(self, message: str) -> bool:
        del message
        return False

    def is_suppressed_recall(self, scope: object, message: str) -> bool:
        del scope, message
        return False


class SyntheticRelationshipService:
    def __init__(self) -> None:
        self.call_count = 0

    def record_completed_dialogue(self, **values: object) -> Any:
        del values
        self.call_count += 1
        return type("SyntheticRelationshipEvent", (), {"applied_delta": 2})()


class FailingRetriever(SyntheticRetriever):
    def retrieve(self, scope: object, message: str) -> tuple[ProviderLongTermFact, ...]:
        del scope, message
        raise LongTermMemoryStorageError("private-long-term-detail")


class FailingRelationshipService(SyntheticRelationshipService):
    def record_completed_dialogue(self, **values: object) -> Any:
        del values
        self.call_count += 1
        raise RelationshipStorageError("private-relationship-detail")


def test_long_term_relationship_and_short_term_outcomes_are_metadata_only() -> None:
    recorder = InMemoryObservabilityRecorder()
    suggestion = {"private-relationship-suggestion": "must-not-appear"}
    provider = FakeProvider([completion(relationship_suggestion=suggestion)])
    relationships = SyntheticRelationshipService()
    application = service(
        provider,
        recorder,
        long_term_retriever=SyntheticRetriever(),
        relationship_service=relationships,
    )

    run(application.execute(request(), trace_id=TRACE_ID))

    trace = traces(recorder)[0]
    assert trace.long_term_outcome is LongTermOutcome.RETRIEVED
    assert trace.selected_long_term_facts == 1
    assert trace.relationship_outcome is RelationshipOutcome.APPLIED
    assert trace.short_term_outcome is ShortTermOutcome.COMMITTED
    assert relationships.call_count == 1
    serialized = repr(tuple(item.as_dict() for item in recorder.snapshot()))
    assert "Synthetic_Alias" not in serialized
    assert "private-relationship-suggestion" not in serialized


@pytest.mark.parametrize(
    ("overrides", "expected_long_term", "expected_relationship"),
    [
        (
            {"long_term_retriever": FailingRetriever()},
            LongTermOutcome.FAILED,
            RelationshipOutcome.NOT_REACHED,
        ),
        (
            {"relationship_service": FailingRelationshipService()},
            LongTermOutcome.NOT_CONFIGURED,
            RelationshipOutcome.FAILED,
        ),
    ],
)
def test_state_component_failures_abort_before_commit_without_exposing_details(
    overrides: dict[str, object],
    expected_long_term: LongTermOutcome,
    expected_relationship: RelationshipOutcome,
) -> None:
    recorder = InMemoryObservabilityRecorder()
    provider = FakeProvider([completion()])

    with pytest.raises(DialogueUseCaseError):
        run(service(provider, recorder, **overrides).execute(request(), trace_id=TRACE_ID))

    trace = traces(recorder)[0]
    assert trace.long_term_outcome is expected_long_term
    assert trace.relationship_outcome is expected_relationship
    assert trace.short_term_outcome is ShortTermOutcome.ABORTED
    state_commit = next(item for item in stages(recorder) if item.stage is TraceStage.STATE_COMMIT)
    assert state_commit.outcome is StageOutcome.NOT_REACHED
    surfaces = repr(tuple(item.as_dict() for item in recorder.snapshot()))
    assert "private-long-term-detail" not in surfaces
    assert "private-relationship-detail" not in surfaces


class CancellationResistantProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.call_count = 0

    async def complete(self, provider_request: ProviderRequest) -> ProviderCompletion:
        del provider_request
        self.call_count += 1
        self.started.set()
        try:
            await asyncio.Event().wait()
            raise AssertionError("Synthetic cancellation provider unexpectedly resumed")
        except asyncio.CancelledError:
            self.cancelled.set()
            return completion()


async def exercise_orphaned_late_result() -> tuple[
    TraceMetadata, tuple[TraceStageMetadata, ...], int
]:
    recorder = InMemoryObservabilityRecorder()
    provider = CancellationResistantProvider()
    application = service(provider, recorder)
    pending = asyncio.create_task(application.execute(request(), trace_id=TRACE_ID))
    await provider.started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    for _ in range(8):
        await asyncio.sleep(0)
        if provider.cancelled.is_set():
            break
    return traces(recorder)[0], stages(recorder), provider.call_count


def test_cancelled_last_waiter_marks_orphan_and_rejects_late_state_commit() -> None:
    trace, recorded_stages, call_count = run(exercise_orphaned_late_result())

    assert call_count == 1
    assert trace.terminal_outcome is TerminalOutcome.ORPHANED
    assert trace.reason_code is TraceReasonCode.ORPHANED
    assert trace.short_term_outcome in {ShortTermOutcome.SELECTED, ShortTermOutcome.EMPTY}
    state_commit = next(item for item in recorded_stages if item.stage is TraceStage.STATE_COMMIT)
    assert state_commit.outcome is StageOutcome.NOT_REACHED

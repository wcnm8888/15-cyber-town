from __future__ import annotations

import asyncio
import inspect
import logging
import traceback
from collections.abc import Coroutine
from typing import Any
from uuid import UUID

import pytest

from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderProtocol,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.contracts.v1 import (
    ApiErrorCode,
    DialogueRequestV1,
    DialogueStatus,
)
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")
TRACE_ID = UUID("33333333-3333-4333-8333-333333333333")
SECOND_TRACE_ID = UUID("44444444-4444-4444-8444-444444444444")


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def make_request(
    *,
    request_id: UUID = REQUEST_ID,
    message: str = "Where can I find a quiet street tonight?",
    npc_id: str = "neon_guide",
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=request_id,
        player_id="local_player",
        npc_id=npc_id,
        conversation_id=CONVERSATION_ID,
        message=message,
    )


def completion(
    content: object = "The east arcade is quiet after midnight.",
    *,
    finish_reason: object = "stop",
    choice_count: int = 1,
    tool_calls_present: bool = False,
    reasoning_content_present: bool = False,
    provider: Any = "fake",
    model: Any = "fake-model",
) -> ProviderCompletion:
    return ProviderCompletion(
        content=content,
        finish_reason=finish_reason,
        choice_count=choice_count,
        tool_calls_present=tool_calls_present,
        reasoning_content_present=reasoning_content_present,
        provider=provider,
        model=model,
        usage=ProviderUsage(prompt_tokens=20, completion_tokens=8),
    )


def make_service(
    provider: ProviderProtocol,
    *,
    clock: Any | None = None,
    max_entries: int = 256,
    timeout_seconds: float = 12.0,
) -> DialogueService:
    return DialogueService(
        personas={"neon_guide": load_bundled_persona("nia_v1.json")},
        provider=provider,
        config=DialogueExecutionConfig(
            model="deepseek-v4-flash",
            temperature=0.6,
            max_tokens=256,
            timeout_seconds=timeout_seconds,
            max_concurrency=2,
            idempotency_ttl_seconds=600.0,
            idempotency_max_entries=max_entries,
        ),
        clock=clock,
    )


def test_success_builds_frozen_prompt_and_strict_response() -> None:
    provider = FakeProvider([completion()])
    service = make_service(provider)

    response = run(service.execute(make_request(), trace_id=TRACE_ID))

    assert response.request_id == REQUEST_ID
    assert response.trace_id == TRACE_ID
    assert response.npc_id == "neon_guide"
    assert response.conversation_id == CONVERSATION_ID
    assert response.reply == "The east arcade is quiet after midnight."
    assert response.status is DialogueStatus.COMPLETED
    assert response.provider == "fake"
    assert provider.call_count == 1
    assert provider.requests[0].system_prompt.startswith("You are Nia")
    assert provider.requests[0].user_message == make_request().message
    assert provider.requests[0].model == "deepseek-v4-flash"
    assert provider.requests[0].temperature == 0.6
    assert provider.requests[0].max_tokens == 256
    assert provider.requests[0].timeout_seconds == 12.0
    assert provider.requests[0].thinking_enabled is False
    assert provider.requests[0].stream is False


def test_unknown_npc_fails_without_calling_provider() -> None:
    provider = FakeProvider([completion()])
    service = make_service(provider)

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(make_request(npc_id="unknown_npc"), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.NPC_NOT_FOUND
    assert captured.value.code is ApiErrorCode.NPC_NOT_FOUND
    assert captured.value.retryable is False
    assert provider.call_count == 0


@pytest.mark.parametrize(
    "invalid_completion",
    [
        completion(None),
        completion(123),
        completion(""),
        completion("   "),
        completion("x" * 4_001),
        completion(finish_reason="length"),
        completion(finish_reason=None),
        completion(choice_count=0),
        completion(choice_count=2),
        completion(tool_calls_present=True),
        completion(reasoning_content_present=True),
        completion(provider=None),
        completion(provider=""),
        completion(provider="p" * 65),
        completion(model=None),
        completion(model=""),
        completion(model="m" * 65),
    ],
)
def test_invalid_provider_outputs_fail_closed(invalid_completion: ProviderCompletion) -> None:
    service = make_service(FakeProvider([invalid_completion]))

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(make_request(), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.PROVIDER_INVALID_RESPONSE
    assert captured.value.code is ApiErrorCode.PROVIDER_UNAVAILABLE
    assert captured.value.retryable is True
    assert "x" * 100 not in captured.value.public_message


def test_content_filter_returns_deterministic_degraded_fallback() -> None:
    service = make_service(FakeProvider([completion(None, finish_reason="content_filter")]))

    response = run(service.execute(make_request(), trace_id=TRACE_ID))

    assert response.status is DialogueStatus.DEGRADED
    assert response.provider == "local-fallback"
    assert response.reply == "Nia pauses, keeping the conversation within safe boundaries."


@pytest.mark.parametrize(
    ("provider_error", "kind", "code"),
    [
        (
            ProviderTimeoutError("synthetic raw timeout detail"),
            DialogueFailureKind.PROVIDER_TIMEOUT,
            ApiErrorCode.PROVIDER_TIMEOUT,
        ),
        (
            ProviderUnavailableError("synthetic raw unavailable detail"),
            DialogueFailureKind.PROVIDER_UNAVAILABLE,
            ApiErrorCode.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_provider_failures_map_to_safe_application_errors(
    provider_error: Exception,
    kind: DialogueFailureKind,
    code: ApiErrorCode,
) -> None:
    service = make_service(FakeProvider([provider_error]))

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(make_request(), trace_id=TRACE_ID))

    assert captured.value.kind is kind
    assert captured.value.code is code
    assert captured.value.retryable is True
    assert "synthetic raw" not in captured.value.public_message
    formatted_traceback = "".join(traceback.format_exception(captured.value))
    assert "synthetic raw" not in formatted_traceback


def test_unexpected_provider_error_maps_to_safe_internal_error() -> None:
    raw_error = "synthetic unexpected provider detail 564738"
    service = make_service(FakeProvider([RuntimeError(raw_error)]))

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(make_request(), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.INTERNAL_ERROR
    assert captured.value.code is ApiErrorCode.INTERNAL_ERROR
    assert captured.value.retryable is False
    assert raw_error not in "".join(traceback.format_exception(captured.value))


class SlowProvider:
    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        del request
        await asyncio.sleep(1.0)
        return completion()


def test_application_deadline_maps_slow_provider_to_timeout() -> None:
    service = make_service(SlowProvider(), timeout_seconds=0.1)

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(make_request(), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.PROVIDER_TIMEOUT
    assert captured.value.code is ApiErrorCode.PROVIDER_TIMEOUT
    assert captured.value.retryable is True


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.call_count = 0

    async def complete(self, request: ProviderRequest) -> ProviderCompletion:
        del request
        self.call_count += 1
        self.started.set()
        await self.release.wait()
        return completion()


async def concurrent_requests_share_one_inflight_provider_call() -> None:
    provider = BlockingProvider()
    service = make_service(provider)
    request = make_request()

    first = asyncio.create_task(service.execute(request, trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(service.execute(request, trace_id=SECOND_TRACE_ID))
    await asyncio.sleep(0)
    assert provider.call_count == 1

    provider.release.set()
    first_response, second_response = await asyncio.gather(first, second)

    assert provider.call_count == 1
    assert first_response.reply == second_response.reply
    assert first_response.trace_id == TRACE_ID
    assert second_response.trace_id == SECOND_TRACE_ID


def test_concurrent_duplicates_share_one_provider_call() -> None:
    run(concurrent_requests_share_one_inflight_provider_call())


async def cancelled_waiter_does_not_cancel_shared_provider_call() -> None:
    provider = BlockingProvider()
    service = make_service(provider)
    request = make_request()

    cancelled = asyncio.create_task(service.execute(request, trace_id=TRACE_ID))
    await provider.started.wait()
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled

    replacement = asyncio.create_task(service.execute(request, trace_id=SECOND_TRACE_ID))
    await asyncio.sleep(0)
    assert provider.call_count == 1
    provider.release.set()
    response = await replacement

    assert response.trace_id == SECOND_TRACE_ID
    assert provider.call_count == 1


def test_cancelling_one_waiter_keeps_shared_request_alive() -> None:
    run(cancelled_waiter_does_not_cancel_shared_provider_call())


async def cancelled_only_waiter_cannot_permanently_exhaust_idempotency_capacity() -> None:
    provider = BlockingProvider()
    service = make_service(provider, max_entries=1)
    original = asyncio.create_task(service.execute(make_request(), trace_id=TRACE_ID))
    await provider.started.wait()
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original

    provider.release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    replacement = make_request(request_id=UUID("55555555-5555-4555-8555-555555555555"))

    response = await service.execute(replacement, trace_id=SECOND_TRACE_ID)

    assert response.request_id == replacement.request_id
    assert provider.call_count == 2


def test_cancelled_only_waiter_releases_capacity_after_provider_completion() -> None:
    run(cancelled_only_waiter_cannot_permanently_exhaust_idempotency_capacity())


def test_completed_replay_uses_cache_with_new_trace_id() -> None:
    provider = FakeProvider([completion()])
    service = make_service(provider)

    first = run(service.execute(make_request(), trace_id=TRACE_ID))
    replay = run(service.execute(make_request(), trace_id=SECOND_TRACE_ID))

    assert provider.call_count == 1
    assert first.reply == replay.reply
    assert replay.trace_id == SECOND_TRACE_ID


def test_same_request_id_with_different_payload_is_a_conflict() -> None:
    provider = FakeProvider([completion()])
    service = make_service(provider)
    run(service.execute(make_request(), trace_id=TRACE_ID))

    with pytest.raises(DialogueUseCaseError) as captured:
        run(
            service.execute(
                make_request(message="Use the same id for different content."),
                trace_id=SECOND_TRACE_ID,
            )
        )

    assert captured.value.kind is DialogueFailureKind.CONFLICT
    assert captured.value.code is ApiErrorCode.CONFLICT
    assert captured.value.retryable is False
    assert provider.call_count == 1


def test_failed_request_is_not_cached_and_manual_retry_can_recover() -> None:
    provider = FakeProvider(
        [ProviderUnavailableError("synthetic provider outage"), completion("Recovered reply")]
    )
    service = make_service(provider)

    with pytest.raises(DialogueUseCaseError):
        run(service.execute(make_request(), trace_id=TRACE_ID))
    response = run(service.execute(make_request(), trace_id=SECOND_TRACE_ID))

    assert provider.call_count == 2
    assert response.reply == "Recovered reply"


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def test_success_cache_expires_after_ttl() -> None:
    clock = FakeClock()
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    service = make_service(provider, clock=clock)

    first = run(service.execute(make_request(), trace_id=TRACE_ID))
    clock.value += 601.0
    second = run(service.execute(make_request(), trace_id=SECOND_TRACE_ID))

    assert provider.call_count == 2
    assert first.reply == "First reply"
    assert second.reply == "Second reply"


def test_capacity_evicts_completed_entry_without_reusing_wrong_result() -> None:
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    service = make_service(provider, max_entries=1)

    first_request = make_request()
    second_request = make_request(request_id=UUID("55555555-5555-4555-8555-555555555555"))
    run(service.execute(first_request, trace_id=TRACE_ID))
    second = run(service.execute(second_request, trace_id=SECOND_TRACE_ID))

    assert provider.call_count == 2
    assert second.reply == "Second reply"


async def capacity_rejects_new_request_while_all_entries_are_inflight() -> None:
    provider = BlockingProvider()
    service = make_service(provider, max_entries=1)
    first = asyncio.create_task(service.execute(make_request(), trace_id=TRACE_ID))
    await provider.started.wait()

    with pytest.raises(DialogueUseCaseError) as captured:
        await service.execute(
            make_request(request_id=UUID("66666666-6666-4666-8666-666666666666")),
            trace_id=SECOND_TRACE_ID,
        )

    assert captured.value.kind is DialogueFailureKind.PROVIDER_UNAVAILABLE
    assert captured.value.retryable is True
    assert provider.call_count == 1
    provider.release.set()
    await first


def test_capacity_does_not_evict_or_duplicate_inflight_requests() -> None:
    run(capacity_rejects_new_request_while_all_entries_are_inflight())


def test_logs_contain_only_allowlisted_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_message = "private player message 938475"
    raw_reply = "private model reply 837465"
    provider = FakeProvider([completion(raw_reply)])
    service = make_service(provider)

    with caplog.at_level(logging.INFO, logger="cyber_town.dialogue"):
        run(service.execute(make_request(message=raw_message), trace_id=TRACE_ID))

    combined = caplog.text + "\n".join(repr(record.__dict__) for record in caplog.records)
    assert raw_message not in combined
    assert raw_reply not in combined
    assert "You are Nia" not in combined
    assert "API key" not in combined
    assert str(TRACE_ID) in combined
    assert str(REQUEST_ID) in combined
    assert "dialogue_completed" in combined


def test_provider_error_details_and_raw_input_are_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_message = "private failed player message 192837"
    raw_error = "private provider exception detail 918273"
    service = make_service(FakeProvider([ProviderUnavailableError(raw_error)]))

    with (
        caplog.at_level(logging.INFO, logger="cyber_town.dialogue"),
        pytest.raises(DialogueUseCaseError),
    ):
        run(service.execute(make_request(message=raw_message), trace_id=TRACE_ID))

    combined = caplog.text + "\n".join(repr(record.__dict__) for record in caplog.records)
    assert raw_message not in combined
    assert raw_error not in combined
    assert "dialogue_failed" in combined


def test_core_protocol_and_use_case_do_not_import_provider_sdk() -> None:
    from cyber_town.application import dialogue, provider
    from cyber_town.domain import persona

    core_source = "\n".join(
        inspect.getsource(module) for module in (dialogue, provider, persona)
    ).lower()
    assert "import openai" not in core_source
    assert "from openai" not in core_source

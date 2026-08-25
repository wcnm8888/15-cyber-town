from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest

from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.memory import ConversationScope, ConversationTurn, ShortTermSessionStore
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderProtocol,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.contracts.v1 import ApiErrorCode, DialogueRequestV1, DialogueStatus
from cyber_town.domain.persona import PersonaDefinition, load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider

CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_CONVERSATION_ID = UUID("77777777-7777-4777-8777-777777777777")
TRACE_ID = UUID("33333333-3333-4333-8333-333333333333")


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def request(
    number: int,
    *,
    message: str = "Synthetic question",
    player_id: str = "local_player",
    npc_id: str = "neon_guide",
    conversation_id: UUID = CONVERSATION_ID,
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=UUID(int=number + 1),
        player_id=player_id,
        npc_id=npc_id,
        conversation_id=conversation_id,
        message=message,
    )


def completion(
    content: object = "Synthetic Nia response",
    *,
    finish_reason: object = "stop",
) -> ProviderCompletion:
    return ProviderCompletion(
        content=content,
        finish_reason=finish_reason,
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=3, completion_tokens=2),
    )


def make_service(
    provider: ProviderProtocol,
    *,
    store: ShortTermSessionStore | None = None,
    persona: PersonaDefinition | None = None,
    clock: Any | None = None,
) -> DialogueService:
    active_persona = persona or load_bundled_persona("nia_v1.json")
    return DialogueService(
        personas={active_persona.npc_id: active_persona},
        provider=provider,
        config=DialogueExecutionConfig(
            model="deepseek-v4-flash",
            temperature=0.6,
            max_tokens=256,
            timeout_seconds=12.0,
            max_concurrency=2,
            idempotency_ttl_seconds=600.0,
            idempotency_max_entries=256,
        ),
        session_store=store,
        clock=clock,
    )


def scope(value: DialogueRequestV1) -> ConversationScope:
    return ConversationScope(value.player_id, value.npc_id, value.conversation_id)


def test_successive_requests_receive_only_completed_history() -> None:
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)

    first = request(1, message="First question")
    second = request(2, message="Second question")
    run(service.execute(first, trace_id=TRACE_ID))
    run(service.execute(second, trace_id=TRACE_ID))

    assert provider.requests[0].history_messages == ()
    assert [(item.role, item.content) for item in provider.requests[1].history_messages] == [
        ("user", "First question"),
        ("assistant", "First reply"),
    ]
    assert store.history(scope(first)) == (
        ConversationTurn("First question", "First reply"),
        ConversationTurn("Second question", "Second reply"),
    )


@pytest.mark.parametrize(
    "message",
    [
        "我刚才告诉你的临时代号是什么\uff1f",
        "还记得我之前说过的名字吗\uff1f",
        "我先前提到的代号是什么",
        "What codename did I tell you earlier?",
        "Do you remember what I told you?",
        "What was my name before?",
    ],
)
def test_empty_scope_recall_returns_truthful_local_reply_without_provider(
    message: str,
) -> None:
    provider = FakeProvider([completion("Synthetic fabricated codename NIGHT-OWL")])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1, message=message)

    response = run(service.execute(command, trace_id=TRACE_ID))

    assert response.status is DialogueStatus.DEGRADED
    assert response.provider == "local-fallback"
    assert "NIGHT-OWL" not in response.reply
    assert provider.call_count == 0
    assert store.history(scope(command)) == ()
    assert store.session_count == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"player_id": "another_player"},
        {"conversation_id": OTHER_CONVERSATION_ID},
    ],
)
def test_empty_scope_recall_never_fabricates_or_reads_another_scope(
    changes: dict[str, Any],
) -> None:
    provider = FakeProvider(
        [completion("Synthetic existing answer"), completion("Synthetic fabricated answer")]
    )
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    original = request(1, message="My temporary codename is BLUE-47.")
    isolated = request(
        2,
        message="What codename did I tell you earlier?",
        **changes,
    )

    run(service.execute(original, trace_id=TRACE_ID))
    response = run(service.execute(isolated, trace_id=TRACE_ID))

    assert response.status is DialogueStatus.DEGRADED
    assert response.provider == "local-fallback"
    assert "BLUE-47" not in response.reply
    assert provider.call_count == 1
    assert len(store.history(scope(original))) == 1
    assert store.history(scope(isolated)) == ()


def test_existing_scope_recall_uses_real_completed_history() -> None:
    provider = FakeProvider([completion("I will remember."), completion("BLUE-47")])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)

    run(
        service.execute(
            request(1, message="My temporary codename is BLUE-47."),
            trace_id=TRACE_ID,
        )
    )
    response = run(
        service.execute(
            request(2, message="What codename did I tell you earlier?"),
            trace_id=TRACE_ID,
        )
    )

    assert response.status is DialogueStatus.COMPLETED
    assert response.reply == "BLUE-47"
    assert provider.call_count == 2
    assert len(provider.requests[1].history_messages) == 2
    assert len(store.history(scope(request(1)))) == 2


@pytest.mark.parametrize(
    "message",
    [
        "我的临时代号是 BLUE-47\uff0c请记住。",
        "你好\uff0c请介绍一下这座城市。",
        "Please remember my temporary codename BLUE-47.",
        "What is your name?",
    ],
)
def test_empty_scope_new_information_still_calls_provider(message: str) -> None:
    provider = FakeProvider([completion("Synthetic grounded first reply")])
    service = make_service(provider)

    response = run(service.execute(request(1, message=message), trace_id=TRACE_ID))

    assert response.status is DialogueStatus.COMPLETED
    assert provider.call_count == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"player_id": "another_player"},
        {"conversation_id": OTHER_CONVERSATION_ID},
    ],
)
def test_different_scope_members_never_share_history(changes: dict[str, Any]) -> None:
    provider = FakeProvider([completion("Private reply"), completion("Separate reply")])
    service = make_service(provider)

    run(service.execute(request(1, message="Private question"), trace_id=TRACE_ID))
    run(service.execute(request(2, **changes), trace_id=TRACE_ID))

    assert provider.requests[1].history_messages == ()


def test_different_npc_scope_cannot_read_existing_nia_history() -> None:
    provider = FakeProvider([completion()])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)

    run(service.execute(request(1), trace_id=TRACE_ID))
    with pytest.raises(DialogueUseCaseError):
        run(service.execute(request(2, npc_id="another_npc"), trace_id=TRACE_ID))

    assert provider.call_count == 1
    assert store.history(ConversationScope("local_player", "another_npc", CONVERSATION_ID)) == ()


def test_seventh_success_retains_six_complete_turns() -> None:
    provider = FakeProvider([completion(f"Reply {index}") for index in range(7)])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)

    for index in range(7):
        run(service.execute(request(index, message=f"Question {index}"), trace_id=TRACE_ID))

    assert [turn.user_message for turn in store.history(scope(request(1)))] == [
        f"Question {index}" for index in range(1, 7)
    ]
    assert len(provider.requests[-1].history_messages) == 12


def test_expired_scope_starts_again_without_prior_history() -> None:
    current_time = [100.0]

    def clock() -> float:
        return current_time[0]

    store = ShortTermSessionStore(clock=clock)
    provider = FakeProvider([completion("First reply"), completion("After expiry")])
    service = make_service(provider, store=store, clock=clock)

    run(service.execute(request(1), trace_id=TRACE_ID))
    current_time[0] += 1_800.0
    run(service.execute(request(2), trace_id=TRACE_ID))

    assert provider.requests[1].history_messages == ()


@pytest.mark.parametrize(
    "outcome",
    [
        ProviderTimeoutError("synthetic timeout"),
        ProviderUnavailableError("synthetic unavailable"),
        completion(None),
    ],
)
def test_failed_requests_never_create_memory(outcome: ProviderCompletion | Exception) -> None:
    store = ShortTermSessionStore()
    service = make_service(FakeProvider([outcome]), store=store)

    with pytest.raises(DialogueUseCaseError):
        run(service.execute(request(1), trace_id=TRACE_ID))

    assert store.history(scope(request(1))) == ()
    assert store.session_count == 0


def test_degraded_fallback_never_creates_memory() -> None:
    store = ShortTermSessionStore()
    service = make_service(
        FakeProvider([completion(None, finish_reason="content_filter")]), store=store
    )

    response = run(service.execute(request(1), trace_id=TRACE_ID))

    assert response.status is DialogueStatus.DEGRADED
    assert store.history(scope(request(1))) == ()
    assert store.session_count == 0


def test_successful_replay_never_appends_duplicate_history() -> None:
    provider = FakeProvider([completion()])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)

    run(service.execute(command, trace_id=TRACE_ID))
    run(service.execute(command, trace_id=TRACE_ID))

    assert provider.call_count == 1
    assert len(store.history(scope(command))) == 1


def test_conflicting_replay_never_appends_history() -> None:
    provider = FakeProvider([completion()])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    run(service.execute(request(1, message="Original"), trace_id=TRACE_ID))

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(request(1, message="Conflict"), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.CONFLICT
    assert len(store.history(scope(request(1)))) == 1


def test_failed_retry_commits_only_the_recovered_turn() -> None:
    provider = FakeProvider([ProviderUnavailableError("synthetic outage"), completion("Recovered")])
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)

    with pytest.raises(DialogueUseCaseError):
        run(service.execute(command, trace_id=TRACE_ID))
    run(service.execute(command, trace_id=TRACE_ID))

    assert store.history(scope(command)) == (ConversationTurn(command.message, "Recovered"),)


def test_oversized_utf8_current_message_fails_without_provider_or_memory() -> None:
    persona = load_bundled_persona("nia_v1.json").model_copy(update={"system_prompt": "p" * 4_000})
    provider = FakeProvider([completion()])
    store = ShortTermSessionStore()
    service = make_service(provider, persona=persona, store=store)
    command = request(1, message="🌃" * 1_000)

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(command, trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.VALIDATION_ERROR
    assert captured.value.code is ApiErrorCode.VALIDATION_ERROR
    assert captured.value.retryable is False
    assert provider.call_count == 0
    assert store.session_count == 0


def test_unusable_persona_minimum_fails_without_provider_or_memory() -> None:
    persona = load_bundled_persona("nia_v1.json").model_copy(update={"system_prompt": "🌃" * 2_000})
    provider = FakeProvider([completion()])
    store = ShortTermSessionStore()
    service = make_service(provider, persona=persona, store=store)

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(request(1), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.PROVIDER_UNAVAILABLE
    assert captured.value.retryable is True
    assert provider.call_count == 0
    assert store.session_count == 0


def test_all_active_sessions_fail_closed_without_provider_or_ghost_history() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        store.begin(ConversationScope(f"player-{index}", "neon_guide", CONVERSATION_ID))
    provider = FakeProvider([completion()])
    service = make_service(provider, store=store)

    with pytest.raises(DialogueUseCaseError) as captured:
        run(service.execute(request(1), trace_id=TRACE_ID))

    assert captured.value.kind is DialogueFailureKind.PROVIDER_UNAVAILABLE
    assert captured.value.code is ApiErrorCode.PROVIDER_UNAVAILABLE
    assert captured.value.retryable is True
    assert provider.call_count == 0
    assert store.session_count == 128


@dataclass
class BlockingProvider:
    outcomes: deque[ProviderCompletion]

    def __post_init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.requests: list[ProviderRequest] = []
        self.active = 0
        self.maximum_active = 0

    async def complete(self, value: ProviderRequest) -> ProviderCompletion:
        self.requests.append(value)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.started.set()
        try:
            await self.release.wait()
            return self.outcomes.popleft()
        finally:
            self.active -= 1


async def assert_same_scope_requests_are_serialized() -> None:
    provider = BlockingProvider(deque([completion("First"), completion("Second")]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    first = asyncio.create_task(service.execute(request(1, message="One"), trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(service.execute(request(2, message="Two"), trace_id=TRACE_ID))
    await asyncio.sleep(0)

    assert len(provider.requests) == 1
    provider.release.set()
    await asyncio.gather(first, second)

    assert len(provider.requests) == 2
    assert provider.requests[1].history_messages[0].content == "One"
    assert provider.maximum_active == 1


def test_same_scope_serializes_history_read_provider_and_commit() -> None:
    run(assert_same_scope_requests_are_serialized())


async def assert_distinct_scopes_are_concurrent() -> None:
    provider = BlockingProvider(deque([completion("First"), completion("Second")]))
    service = make_service(provider)
    first = asyncio.create_task(service.execute(request(1), trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(
        service.execute(request(2, conversation_id=OTHER_CONVERSATION_ID), trace_id=TRACE_ID)
    )
    for _ in range(5):
        await asyncio.sleep(0)

    assert len(provider.requests) == 2
    assert provider.maximum_active == 2
    provider.release.set()
    await asyncio.gather(first, second)


def test_distinct_scopes_run_concurrently_within_global_provider_limit() -> None:
    run(assert_distinct_scopes_are_concurrent())


async def assert_three_scopes_respect_global_concurrency_limit() -> None:
    provider = BlockingProvider(
        deque([completion("First"), completion("Second"), completion("Third")])
    )
    service = make_service(provider)
    commands = [request(index, player_id=f"player-{index}") for index in range(3)]
    pending = [
        asyncio.create_task(service.execute(command, trace_id=TRACE_ID)) for command in commands
    ]
    for _ in range(8):
        await asyncio.sleep(0)

    assert len(provider.requests) == 2
    assert provider.maximum_active == 2
    provider.release.set()
    await asyncio.gather(*pending)

    assert len(provider.requests) == 3
    assert provider.maximum_active == 2


def test_three_distinct_scopes_never_exceed_two_global_provider_slots() -> None:
    run(assert_three_scopes_respect_global_concurrency_limit())


async def assert_duplicate_waiters_commit_once() -> None:
    provider = BlockingProvider(deque([completion()]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    first = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await asyncio.sleep(0)
    provider.release.set()
    await asyncio.gather(first, second)

    assert len(provider.requests) == 1
    assert len(store.history(scope(command))) == 1


def test_concurrent_duplicate_waiters_commit_one_complete_turn() -> None:
    run(assert_duplicate_waiters_commit_once())


async def assert_partial_waiter_cancellation_preserves_valid_request() -> None:
    provider = BlockingProvider(deque([completion()]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    first = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    provider.release.set()
    await second

    assert len(provider.requests) == 1
    assert len(store.history(scope(command))) == 1


def test_cancelling_one_of_multiple_waiters_still_commits_once() -> None:
    run(assert_partial_waiter_cancellation_preserves_valid_request())


async def assert_last_waiter_cancellation_aborts_history() -> None:
    provider = BlockingProvider(deque([completion("Must not persist")]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    pending = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    provider.release.set()
    for _ in range(5):
        await asyncio.sleep(0)

    assert store.history(scope(command)) == ()
    assert store.session_count == 0
    assert provider.active == 0


def test_cancelling_last_waiter_never_commits_a_late_provider_result() -> None:
    run(assert_last_waiter_cancellation_aborts_history())


async def assert_all_duplicate_waiters_cancel_without_history() -> None:
    provider = BlockingProvider(deque([completion("Must not persist")]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    first = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    second = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await asyncio.sleep(0)
    first.cancel()
    second.cancel()
    for pending in (first, second):
        with pytest.raises(asyncio.CancelledError):
            await pending
    provider.release.set()
    for _ in range(6):
        await asyncio.sleep(0)

    assert store.history(scope(command)) == ()
    assert store.session_count == 0
    assert provider.active == 0


def test_cancelling_all_duplicate_waiters_releases_scope_without_history() -> None:
    run(assert_all_duplicate_waiters_cancel_without_history())


class LateCompletionProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, value: ProviderRequest) -> ProviderCompletion:
        del value
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            await self.release.wait()
        return completion("Synthetic orphan result")


class RetriedLateCompletionProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.requests: list[ProviderRequest] = []

    async def complete(self, value: ProviderRequest) -> ProviderCompletion:
        self.requests.append(value)
        if len(self.requests) == 1:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                await self.release.wait()
            return completion("Synthetic adopted result")
        return completion("Synthetic duplicate result")


async def assert_cancellation_resistant_late_result_cannot_commit() -> None:
    provider = LateCompletionProvider()
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    pending = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.wait_for(provider.cancelled.wait(), timeout=1.0)
    provider.release.set()
    for _ in range(5):
        await asyncio.sleep(0)

    assert store.history(scope(command)) == ()
    assert store.session_count == 0


def test_provider_that_returns_after_cancellation_cannot_create_ghost_memory() -> None:
    run(assert_cancellation_resistant_late_result_cannot_commit())


async def assert_cancelled_orphan_retry_is_adopted_once(waiter_count: int) -> None:
    provider = RetriedLateCompletionProvider()
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    command = request(1)
    original = asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
    await provider.started.wait()
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original
    await asyncio.wait_for(provider.cancelled.wait(), timeout=1.0)

    retries = [
        asyncio.create_task(service.execute(command, trace_id=TRACE_ID))
        for _ in range(waiter_count)
    ]
    for _ in range(3):
        await asyncio.sleep(0)
    provider.release.set()
    responses = await asyncio.wait_for(asyncio.gather(*retries), timeout=1.0)

    assert len(provider.requests) == 1
    assert all(response.reply == "Synthetic adopted result" for response in responses)
    history = store.history(scope(command))
    assert len(history) == 1
    assert history[0].assistant_message == "Synthetic adopted result"


@pytest.mark.parametrize("waiter_count", (1, 2))
def test_cancelled_orphan_same_request_retry_never_duplicates_provider_or_memory(
    waiter_count: int,
) -> None:
    run(assert_cancelled_orphan_retry_is_adopted_once(waiter_count))


async def assert_scope_wait_fails_without_provider_or_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = BlockingProvider(deque([completion()]))
    store = ShortTermSessionStore()
    service = make_service(provider, store=store)
    first = asyncio.create_task(service.execute(request(1), trace_id=TRACE_ID))
    await provider.started.wait()

    original_wait_for = asyncio.wait_for

    async def synthetic_timeout(awaitable: Any, timeout: float | None) -> Any:
        if inspect_timeout(timeout):
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise TimeoutError
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr("cyber_town.application.dialogue.asyncio.wait_for", synthetic_timeout)
    with pytest.raises(DialogueUseCaseError) as captured:
        await service.execute(request(2), trace_id=TRACE_ID)

    assert captured.value.kind is DialogueFailureKind.PROVIDER_UNAVAILABLE
    assert captured.value.retryable is True
    assert len(provider.requests) == 1
    provider.release.set()
    await first
    assert len(store.history(scope(request(1)))) == 1


def inspect_timeout(value: float | None) -> bool:
    return value == 2.0


def test_same_scope_wait_timeout_is_safe_without_real_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run(assert_scope_wait_fails_without_provider_or_memory(monkeypatch))


def test_history_content_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    provider = FakeProvider([completion("private assistant 8234"), completion("second")])
    service = make_service(provider)

    with caplog.at_level(logging.INFO, logger="cyber_town.dialogue"):
        run(service.execute(request(1, message="private user 7194"), trace_id=TRACE_ID))
        run(service.execute(request(2), trace_id=TRACE_ID))

    combined = caplog.text + "\n".join(repr(item.__dict__) for item in caplog.records)
    assert "private user 7194" not in combined
    assert "private assistant 8234" not in combined

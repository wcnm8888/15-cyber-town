from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from cyber_town.api.app import create_app
from cyber_town.application.dialogue import DialogueExecutionConfig, DialogueService
from cyber_town.application.memory import ConversationScope, ShortTermSessionStore
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.domain.persona import PersonaDefinition, load_bundled_persona
from cyber_town.infrastructure.llm.fake import FakeProvider

DIALOGUE_PATH = "/api/v1/dialogue"
CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_CONVERSATION_ID = UUID("77777777-7777-4777-8777-777777777777")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def completion(
    content: object = "Synthetic offline response",
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
        usage=ProviderUsage(prompt_tokens=5, completion_tokens=3),
    )


def payload(
    number: int,
    *,
    player_id: str = "local_player",
    conversation_id: UUID = CONVERSATION_ID,
    message: str = "Synthetic question",
) -> dict[str, Any]:
    return {
        "request_id": str(UUID(int=number + 1)),
        "player_id": player_id,
        "npc_id": "neon_guide",
        "conversation_id": str(conversation_id),
        "message": message,
    }


def make_service(
    provider: FakeProvider,
    *,
    store: ShortTermSessionStore | None = None,
    persona: PersonaDefinition | None = None,
) -> DialogueService:
    approved_persona = persona or load_bundled_persona("nia_v1.json")
    return DialogueService(
        personas={approved_persona.npc_id: approved_persona},
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
    )


@pytest.mark.anyio
async def test_http_multi_turn_preserves_exact_public_contract_and_private_history() -> None:
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1, message="First question"))
        second = await client.post(DIALOGUE_PATH, json=payload(2, message="Second question"))

    assert first.status_code == second.status_code == 200
    assert set(second.json()) == {
        "request_id",
        "trace_id",
        "npc_id",
        "conversation_id",
        "reply",
        "status",
        "provider",
    }
    assert [(item.role, item.content) for item in provider.requests[1].history_messages] == [
        ("user", "First question"),
        ("assistant", "First reply"),
    ]
    assert "history_messages" not in second.text


@pytest.mark.parametrize(
    "message",
    [
        "我刚才告诉你的临时代号是什么\uff1f",
        "What codename did I tell you earlier?",
    ],
)
@pytest.mark.anyio
async def test_http_empty_scope_recall_returns_truthful_existing_fallback_contract(
    message: str,
) -> None:
    provider = FakeProvider([completion("Synthetic invented codename NIGHT-OWL")])
    store = ShortTermSessionStore()
    transport = ASGITransport(app=create_app(make_service(provider, store=store)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(DIALOGUE_PATH, json=payload(1, message=message))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "request_id",
        "trace_id",
        "npc_id",
        "conversation_id",
        "reply",
        "status",
        "provider",
    }
    assert body["status"] == "degraded"
    assert body["provider"] == "local-fallback"
    assert "NIGHT-OWL" not in body["reply"]
    assert provider.call_count == 0
    assert store.session_count == 0


@pytest.mark.parametrize(
    "changes",
    [{"player_id": "another_player"}, {"conversation_id": OTHER_CONVERSATION_ID}],
)
@pytest.mark.anyio
async def test_http_scope_member_changes_never_leak_history(changes: dict[str, Any]) -> None:
    provider = FakeProvider([completion("Private reply"), completion("Separate reply")])
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1, message="Private question"))
        second = await client.post(DIALOGUE_PATH, json=payload(2, **changes))

    assert first.status_code == second.status_code == 200
    assert provider.requests[1].history_messages == ()


@pytest.mark.anyio
async def test_http_unknown_npc_never_reads_other_npc_history() -> None:
    provider = FakeProvider([completion()])
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1))
        second = await client.post(
            DIALOGUE_PATH,
            json={**payload(2), "npc_id": "another_npc"},
        )

    assert first.status_code == 200
    assert second.status_code == 404
    assert provider.call_count == 1


@pytest.mark.anyio
async def test_http_seven_turns_retain_only_six_complete_history_pairs() -> None:
    provider = FakeProvider([completion(f"Reply {index}") for index in range(8)])
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for index in range(8):
            response = await client.post(
                DIALOGUE_PATH,
                json=payload(index, message=f"Question {index}"),
            )
            assert response.status_code == 200

    history = provider.requests[-1].history_messages
    assert len(history) == 12
    assert history[0].content == "Question 1"
    assert history[-1].content == "Reply 6"


@pytest.mark.parametrize(
    ("failure", "status_code"),
    [
        (ProviderUnavailableError("private unavailable"), 503),
        (ProviderTimeoutError("private timeout"), 504),
        (completion(None), 502),
    ],
)
@pytest.mark.anyio
async def test_http_failure_retry_preserves_prior_history_without_ghost_turn(
    failure: ProviderCompletion | Exception,
    status_code: int,
) -> None:
    provider = FakeProvider([completion("First reply"), failure, completion("Recovered reply")])
    transport = ASGITransport(app=create_app(make_service(provider)))
    retried = payload(2, message="Second question")

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1, message="First question"))
        failed = await client.post(DIALOGUE_PATH, json=retried)
        recovered = await client.post(DIALOGUE_PATH, json=retried)

    assert first.status_code == 200
    assert failed.status_code == status_code
    assert failed.json()["retryable"] is True
    assert recovered.status_code == 200
    assert provider.requests[1].history_messages == provider.requests[2].history_messages
    assert len(provider.requests[2].history_messages) == 2
    assert provider.call_count == 3


@pytest.mark.anyio
async def test_http_degraded_response_does_not_enter_later_history() -> None:
    provider = FakeProvider(
        [completion("First reply"), completion(None, finish_reason="content_filter"), completion()]
    )
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1))
        degraded = await client.post(DIALOGUE_PATH, json=payload(2, message="Filtered"))
        third = await client.post(DIALOGUE_PATH, json=payload(3))

    assert first.status_code == degraded.status_code == third.status_code == 200
    assert degraded.json()["status"] == "degraded"
    assert [item.content for item in provider.requests[2].history_messages] == [
        "Synthetic question",
        "First reply",
    ]


@pytest.mark.anyio
async def test_http_success_replay_does_not_append_duplicate_memory() -> None:
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    transport = ASGITransport(app=create_app(make_service(provider)))
    first_payload = payload(1, message="First question")

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=first_payload)
        replay = await client.post(DIALOGUE_PATH, json=first_payload)
        second = await client.post(DIALOGUE_PATH, json=payload(2))

    assert first.status_code == replay.status_code == second.status_code == 200
    assert first.json()["trace_id"] != replay.json()["trace_id"]
    assert provider.call_count == 2
    assert len(provider.requests[1].history_messages) == 2


@pytest.mark.anyio
async def test_http_conflict_does_not_mutate_original_history() -> None:
    provider = FakeProvider([completion("First reply"), completion("Second reply")])
    transport = ASGITransport(app=create_app(make_service(provider)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(DIALOGUE_PATH, json=payload(1, message="Original"))
        conflict = await client.post(DIALOGUE_PATH, json=payload(1, message="Different"))
        second = await client.post(DIALOGUE_PATH, json=payload(2))

    assert first.status_code == second.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["retryable"] is False
    assert [item.content for item in provider.requests[1].history_messages] == [
        "Original",
        "First reply",
    ]


@pytest.mark.anyio
async def test_http_utf8_context_overflow_maps_to_public_422_without_provider_call() -> None:
    persona = load_bundled_persona("nia_v1.json").model_copy(update={"system_prompt": "p" * 4_000})
    provider = FakeProvider([completion()])
    transport = ASGITransport(app=create_app(make_service(provider, persona=persona)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(DIALOGUE_PATH, json=payload(1, message="🌃" * 1_000))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["retryable"] is False
    assert provider.call_count == 0


@pytest.mark.anyio
async def test_http_inflight_capacity_maps_to_safe_503_without_provider_call() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        store.begin(ConversationScope(f"occupied-{index}", "neon_guide", CONVERSATION_ID))
    provider = FakeProvider([completion()])
    transport = ASGITransport(app=create_app(make_service(provider, store=store)))

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(DIALOGUE_PATH, json=payload(1))

    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"
    assert response.json()["retryable"] is True
    assert provider.call_count == 0

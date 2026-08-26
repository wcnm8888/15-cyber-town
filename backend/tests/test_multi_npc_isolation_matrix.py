from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import SecretStr

from cyber_town.api.composition import build_dialogue_service
from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.memory import (
    ConversationScope,
    ConversationTurn,
    ShortTermSessionStore,
)
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderProtocol,
    ProviderRequest,
    ProviderUsage,
)
from cyber_town.application.relationship import RelationshipService
from cyber_town.config import LlmProvider, Settings
from cyber_town.contracts.v1 import DialogueRequestV1
from cyber_town.domain.long_term_memory import LongTermMemoryScope
from cyber_town.domain.persona import load_bundled_personas
from cyber_town.domain.relationship import RelationshipReasonCode, RelationshipScope
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import (
    SqliteLongTermMemoryRepository,
)
from cyber_town.infrastructure.persistence.sqlite_relationship import (
    SqliteRelationshipRepository,
)

NPC_IDS = ("neon_guide", "signal_archivist", "night_courier")
PLAYER_IDS = ("player_alpha", "player_beta")
CONVERSATION_IDS = (UUID(int=101), UUID(int=202))
TRACE_ID = UUID(int=9000)


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CYBER_TOWN_DISABLE_DOTENV", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def completion(
    reply: str,
    *,
    relationship_suggestion: object = None,
) -> ProviderCompletion:
    return ProviderCompletion(
        content=reply,
        finish_reason="stop",
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=3, completion_tokens=2),
        relationship_suggestion=relationship_suggestion,
    )


def request(
    index: int,
    *,
    player_id: str,
    npc_id: str,
    conversation_id: UUID,
    message: str,
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=UUID(int=index),
        player_id=player_id,
        npc_id=npc_id,
        conversation_id=conversation_id,
        message=message,
    )


def config() -> DialogueExecutionConfig:
    return DialogueExecutionConfig(
        model="deepseek-v4-flash",
        temperature=0.6,
        max_tokens=256,
        timeout_seconds=12.0,
        max_concurrency=2,
        idempotency_ttl_seconds=600.0,
        idempotency_max_entries=256,
    )


def direct_service(
    provider: ProviderProtocol,
    *,
    store: ShortTermSessionStore | None = None,
    relationship_repository: SqliteRelationshipRepository | None = None,
) -> DialogueService:
    return DialogueService(
        personas=load_bundled_personas(),
        provider=provider,
        config=config(),
        session_store=store,
        relationship_service=(
            None
            if relationship_repository is None
            else RelationshipService(repository=relationship_repository)
        ),
    )


def repositories(
    tmp_path: Path,
) -> tuple[SqliteLongTermMemoryRepository, SqliteRelationshipRepository]:
    database_path = tmp_path / "f007-step3.sqlite3"
    memory = SqliteLongTermMemoryRepository(database_path=database_path, allowed_root=tmp_path)
    memory.initialize()
    relationship = SqliteRelationshipRepository(database_path=database_path, allowed_root=tmp_path)
    relationship.initialize()
    return memory, relationship


def composed_service(
    tmp_path: Path,
    provider: ProviderProtocol,
) -> tuple[DialogueService, SqliteLongTermMemoryRepository, SqliteRelationshipRepository]:
    memory, relationship = repositories(tmp_path)
    settings = Settings.model_validate(
        {
            "llm_provider": LlmProvider.DEEPSEEK,
            "llm_api_key": SecretStr("synthetic-provider-value"),
        }
    )
    service = build_dialogue_service(
        settings,
        provider=provider,
        long_term_repository=memory,
        relationship_repository=relationship,
    )
    assert service is not None
    return service, memory, relationship


def conversation_scope(value: DialogueRequestV1) -> ConversationScope:
    return ConversationScope(value.player_id, value.npc_id, value.conversation_id)


def test_short_term_history_isolated_across_full_player_npc_conversation_matrix() -> None:
    matrix = [
        (player_id, npc_id, conversation_id)
        for player_id in PLAYER_IDS
        for npc_id in NPC_IDS
        for conversation_id in CONVERSATION_IDS
    ]
    outcomes = [completion(f"private-reply-{index}") for index in range(len(matrix))]
    outcomes.extend(completion(f"follow-up-reply-{index}") for index in range(len(matrix)))
    provider = FakeProvider(outcomes)
    store = ShortTermSessionStore()
    service = direct_service(provider, store=store)
    first_requests: list[DialogueRequestV1] = []

    for index, (player_id, npc_id, conversation_id) in enumerate(matrix, start=1):
        command = request(
            index,
            player_id=player_id,
            npc_id=npc_id,
            conversation_id=conversation_id,
            message=f"private-message-{index}",
        )
        first_requests.append(command)
        run(service.execute(command, trace_id=TRACE_ID))

    for index, (player_id, npc_id, conversation_id) in enumerate(matrix, start=len(matrix) + 1):
        run(
            service.execute(
                request(
                    index,
                    player_id=player_id,
                    npc_id=npc_id,
                    conversation_id=conversation_id,
                    message=f"follow-up-message-{index}",
                ),
                trace_id=TRACE_ID,
            )
        )

    assert store.session_count == len(matrix)
    personas = load_bundled_personas()
    for offset, first in enumerate(first_requests):
        follow_up = provider.requests[len(matrix) + offset]
        assert [(item.role, item.content) for item in follow_up.history_messages] == [
            ("user", first.message),
            ("assistant", f"private-reply-{offset}"),
        ]
        assert follow_up.system_prompt == personas[first.npc_id].system_prompt


def test_long_term_facts_cross_conversations_but_not_player_or_npc(tmp_path: Path) -> None:
    matrix = [(player_id, npc_id) for player_id in PLAYER_IDS for npc_id in NPC_IDS]
    provider = FakeProvider(
        [completion(f"isolated-recall-{index}") for index in range(len(matrix))]
    )
    service, memory, _ = composed_service(tmp_path, provider)
    aliases: dict[tuple[str, str], str] = {}

    for index, (player_id, npc_id) in enumerate(matrix, start=1):
        alias = f"P{index}-{npc_id[:4].upper()}"
        aliases[(player_id, npc_id)] = alias
        remembered = request(
            100 + index,
            player_id=player_id,
            npc_id=npc_id,
            conversation_id=CONVERSATION_IDS[0],
            message=f"Remember: game_alias={alias}",
        )
        response = run(service.execute(remembered, trace_id=TRACE_ID))
        assert response.provider == "local-memory"

    for index, (player_id, npc_id) in enumerate(matrix, start=1):
        recalled = request(
            200 + index,
            player_id=player_id,
            npc_id=npc_id,
            conversation_id=CONVERSATION_IDS[1],
            message="What is my game_alias?",
        )
        run(service.execute(recalled, trace_id=TRACE_ID))

    personas = load_bundled_personas()
    for provider_request, (player_id, npc_id) in zip(provider.requests, matrix, strict=True):
        expected_alias = aliases[(player_id, npc_id)]
        assert [(fact.fact_key, fact.fact_value) for fact in provider_request.long_term_facts] == [
            ("game_alias", expected_alias)
        ]
        assert provider_request.history_messages == ()
        assert provider_request.system_prompt == personas[npc_id].system_prompt
        records = memory.list_scope(LongTermMemoryScope(player_id, npc_id))
        assert [record.fact_value for record in records] == [expected_alias]


def test_relationship_and_replay_are_isolated_by_player_and_npc_across_conversations(
    tmp_path: Path,
) -> None:
    matrix = [(player_id, npc_id) for player_id in PLAYER_IDS for npc_id in NPC_IDS]
    suggestion = {"category": "friendly", "confidence": 80}
    provider = FakeProvider(
        [
            completion(f"relationship-reply-{index}", relationship_suggestion=suggestion)
            for index in range(len(matrix) * 2)
        ]
    )
    service, _, relationship = composed_service(tmp_path, provider)
    first_requests: dict[tuple[str, str], DialogueRequestV1] = {}
    second_requests: dict[tuple[str, str], DialogueRequestV1] = {}

    for offset, (player_id, npc_id) in enumerate(matrix, start=1):
        first = request(
            300 + offset,
            player_id=player_id,
            npc_id=npc_id,
            conversation_id=CONVERSATION_IDS[0],
            message=f"first relationship turn {offset}",
        )
        second = request(
            400 + offset,
            player_id=player_id,
            npc_id=npc_id,
            conversation_id=CONVERSATION_IDS[1],
            message=f"second relationship turn {offset}",
        )
        first_requests[(player_id, npc_id)] = first
        second_requests[(player_id, npc_id)] = second
        run(service.execute(first, trace_id=TRACE_ID))
        run(service.execute(second, trace_id=TRACE_ID))

    for player_id, npc_id in matrix:
        scope = RelationshipScope(player_id, npc_id)
        first = first_requests[(player_id, npc_id)]
        second = second_requests[(player_id, npc_id)]
        state = relationship.get_state(scope)
        first_event = relationship.event_for_request(scope, first.request_id)
        second_event = relationship.event_for_request(scope, second.request_id)

        assert state.score == 21
        assert first_event is not None
        assert first_event.conversation_id == CONVERSATION_IDS[0]
        assert first_event.applied_delta == 1
        assert second_event is not None
        assert second_event.conversation_id == CONVERSATION_IDS[1]
        assert second_event.applied_delta == 0
        assert second_event.reason_code is RelationshipReasonCode.COOLDOWN

        replay = run(service.execute(first, trace_id=UUID(int=9999)))
        assert replay.reply.startswith("relationship-reply-")
        assert relationship.get_state(scope) == state

        foreign_npc = NPC_IDS[(NPC_IDS.index(npc_id) + 1) % len(NPC_IDS)]
        assert (
            relationship.event_for_request(
                RelationshipScope(player_id, foreign_npc), first.request_id
            )
            is None
        )

    assert provider.call_count == len(matrix) * 2
    assert relationship.get_state(RelationshipScope("untouched_player", NPC_IDS[0])).score == 20


def test_request_id_reuse_in_another_npc_fails_closed_without_sharing_results(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [
            completion(
                "Nia-owned reply",
                relationship_suggestion={"category": "friendly", "confidence": 80},
            )
        ]
    )
    _, relationship = repositories(tmp_path)
    store = ShortTermSessionStore()
    service = direct_service(provider, store=store, relationship_repository=relationship)
    nia = request(
        500,
        player_id=PLAYER_IDS[0],
        npc_id="neon_guide",
        conversation_id=CONVERSATION_IDS[0],
        message="Nia-owned request",
    )
    ivo = request(
        500,
        player_id=PLAYER_IDS[0],
        npc_id="signal_archivist",
        conversation_id=CONVERSATION_IDS[0],
        message="Ivo must not inherit this request",
    )

    run(service.execute(nia, trace_id=TRACE_ID))
    with pytest.raises(DialogueUseCaseError) as raised:
        run(service.execute(ivo, trace_id=TRACE_ID))

    assert raised.value.kind is DialogueFailureKind.CONFLICT
    assert provider.call_count == 1
    assert store.history(conversation_scope(nia)) == (
        ConversationTurn("Nia-owned request", "Nia-owned reply"),
    )
    assert store.history(conversation_scope(ivo)) == ()
    assert relationship.get_state(RelationshipScope(PLAYER_IDS[0], "neon_guide")).score == 21
    assert relationship.get_state(RelationshipScope(PLAYER_IDS[0], "signal_archivist")).score == 20


class GateProvider:
    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []
        self.two_active = asyncio.Event()
        self.release = asyncio.Event()
        self.active = 0
        self.maximum_active = 0

    async def complete(self, value: ProviderRequest) -> ProviderCompletion:
        self.requests.append(value)
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        if self.active == 2:
            self.two_active.set()
        try:
            await self.release.wait()
            return completion(
                f"reply:{value.user_message}",
                relationship_suggestion={"category": "friendly", "confidence": 80},
            )
        finally:
            self.active -= 1


async def assert_scope_lock_and_adjacent_npc_concurrency(tmp_path: Path) -> None:
    provider = GateProvider()
    _, relationship = repositories(tmp_path)
    store = ShortTermSessionStore()
    service = direct_service(provider, store=store, relationship_repository=relationship)
    first = request(
        600,
        player_id=PLAYER_IDS[0],
        npc_id="signal_archivist",
        conversation_id=CONVERSATION_IDS[0],
        message="Ivo first",
    )
    queued_same_scope = request(
        601,
        player_id=PLAYER_IDS[0],
        npc_id="signal_archivist",
        conversation_id=CONVERSATION_IDS[0],
        message="Ivo second",
    )
    adjacent_npc = request(
        602,
        player_id=PLAYER_IDS[0],
        npc_id="night_courier",
        conversation_id=CONVERSATION_IDS[0],
        message="Rhea adjacent",
    )

    first_task = asyncio.create_task(service.execute(first, trace_id=TRACE_ID))
    while not provider.requests:
        await asyncio.sleep(0)
    queued_task = asyncio.create_task(service.execute(queued_same_scope, trace_id=TRACE_ID))
    adjacent_task = asyncio.create_task(service.execute(adjacent_npc, trace_id=TRACE_ID))
    await asyncio.wait_for(provider.two_active.wait(), timeout=1.0)

    assert {item.user_message for item in provider.requests} == {"Ivo first", "Rhea adjacent"}
    assert provider.maximum_active == 2

    provider.release.set()
    await asyncio.wait_for(
        asyncio.gather(first_task, queued_task, adjacent_task),
        timeout=1.0,
    )

    assert [item.user_message for item in provider.requests].count("Ivo second") == 1
    ivo_second_provider_request = next(
        item for item in provider.requests if item.user_message == "Ivo second"
    )
    assert [(item.role, item.content) for item in ivo_second_provider_request.history_messages] == [
        ("user", "Ivo first"),
        ("assistant", "reply:Ivo first"),
    ]
    rhea_provider_request = next(
        item for item in provider.requests if item.user_message == "Rhea adjacent"
    )
    assert rhea_provider_request.history_messages == ()
    assert relationship.get_state(RelationshipScope(PLAYER_IDS[0], "signal_archivist")).score == 21
    assert relationship.get_state(RelationshipScope(PLAYER_IDS[0], "night_courier")).score == 21


def test_same_scope_serializes_without_blocking_an_adjacent_npc(tmp_path: Path) -> None:
    run(assert_scope_lock_and_adjacent_npc_concurrency(tmp_path))


class LateAndAdjacentProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()

    async def complete(self, value: ProviderRequest) -> ProviderCompletion:
        if value.user_message != "cancelled Ivo request":
            return completion(
                "Rhea survives adjacent cancellation",
                relationship_suggestion={"category": "friendly", "confidence": 80},
            )

        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            await self.release.wait()
        return completion(
            "late Ivo reply must be inert",
            relationship_suggestion={"category": "supportive", "confidence": 100},
        )


async def assert_late_cancelled_result_cannot_pollute_adjacent_npc(tmp_path: Path) -> None:
    provider = LateAndAdjacentProvider()
    _, relationship = repositories(tmp_path)
    store = ShortTermSessionStore()
    service = direct_service(provider, store=store, relationship_repository=relationship)
    cancelled = request(
        700,
        player_id=PLAYER_IDS[0],
        npc_id="signal_archivist",
        conversation_id=CONVERSATION_IDS[0],
        message="cancelled Ivo request",
    )
    adjacent = request(
        701,
        player_id=PLAYER_IDS[0],
        npc_id="night_courier",
        conversation_id=CONVERSATION_IDS[0],
        message="valid Rhea request",
    )

    pending = asyncio.create_task(service.execute(cancelled, trace_id=TRACE_ID))
    await asyncio.wait_for(provider.started.wait(), timeout=1.0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await asyncio.wait_for(provider.cancelled.wait(), timeout=1.0)

    adjacent_response = await asyncio.wait_for(
        service.execute(adjacent, trace_id=TRACE_ID), timeout=1.0
    )
    provider.release.set()
    for _ in range(8):
        await asyncio.sleep(0)

    assert adjacent_response.reply == "Rhea survives adjacent cancellation"
    assert store.history(conversation_scope(cancelled)) == ()
    assert store.history(conversation_scope(adjacent)) == (
        ConversationTurn("valid Rhea request", "Rhea survives adjacent cancellation"),
    )
    cancelled_scope = RelationshipScope(PLAYER_IDS[0], "signal_archivist")
    adjacent_scope = RelationshipScope(PLAYER_IDS[0], "night_courier")
    assert relationship.get_state(cancelled_scope).score == 20
    assert relationship.event_for_request(cancelled_scope, cancelled.request_id) is None
    assert relationship.get_state(adjacent_scope).score == 21
    assert relationship.event_for_request(adjacent_scope, adjacent.request_id) is not None


def test_cancellation_resistant_late_result_cannot_pollute_adjacent_npc(tmp_path: Path) -> None:
    run(assert_late_cancelled_result_cannot_pollute_adjacent_npc(tmp_path))

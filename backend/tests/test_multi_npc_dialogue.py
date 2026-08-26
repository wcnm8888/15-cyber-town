from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cyber_town.api.app import create_app
from cyber_town.api.composition import build_dialogue_service
from cyber_town.application.dialogue import (
    DialogueExecutionConfig,
    DialogueFailureKind,
    DialogueService,
    DialogueUseCaseError,
)
from cyber_town.application.memory import ShortTermSessionStore
from cyber_town.application.provider import ProviderCompletion, ProviderUsage
from cyber_town.config import LlmProvider, Settings
from cyber_town.contracts.v1 import DialogueRequestV1
from cyber_town.domain.long_term_memory import LongTermMemoryScope
from cyber_town.domain.persona import load_bundled_personas
from cyber_town.domain.relationship import RelationshipScope
from cyber_town.infrastructure.llm.fake import FakeProvider
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import (
    SqliteLongTermMemoryRepository,
)
from cyber_town.infrastructure.persistence.sqlite_relationship import SqliteRelationshipRepository

PERSONAS = (
    ("neon_guide", "Nia", "nia-v1"),
    ("signal_archivist", "Ivo", "ivo-v1"),
    ("night_courier", "Rhea", "rhea-v1"),
)
DEFAULT_CONVERSATION_ID = UUID("22222222-2222-4222-8222-222222222222")


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
    finish_reason: str = "stop",
    relationship_suggestion: object = None,
) -> ProviderCompletion:
    return ProviderCompletion(
        content=reply if finish_reason == "stop" else None,
        finish_reason=finish_reason,
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
    npc_id: str,
    player_id: str = "local_player",
    conversation_id: UUID = DEFAULT_CONVERSATION_ID,
    message: str = "Synthetic question",
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=UUID(int=index),
        player_id=player_id,
        npc_id=npc_id,
        conversation_id=conversation_id,
        message=message,
    )


def settings() -> Settings:
    return Settings.model_validate(
        {
            "llm_provider": LlmProvider.DEEPSEEK,
            "llm_api_key": SecretStr("synthetic-provider-value"),
        }
    )


def repositories(
    tmp_path: Path,
) -> tuple[SqliteLongTermMemoryRepository, SqliteRelationshipRepository]:
    database_path = tmp_path / "f007-step2.sqlite3"
    memory = SqliteLongTermMemoryRepository(database_path=database_path, allowed_root=tmp_path)
    memory.initialize()
    relationship = SqliteRelationshipRepository(database_path=database_path, allowed_root=tmp_path)
    relationship.initialize()
    return memory, relationship


def composed_service(
    tmp_path: Path,
    provider: FakeProvider,
) -> tuple[DialogueService, SqliteLongTermMemoryRepository, SqliteRelationshipRepository]:
    memory, relationship = repositories(tmp_path)
    service = build_dialogue_service(
        settings(),
        provider=provider,
        long_term_repository=memory,
        relationship_repository=relationship,
    )
    assert service is not None
    return service, memory, relationship


def direct_service(provider: FakeProvider) -> DialogueService:
    return DialogueService(
        personas=load_bundled_personas(),
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
        session_store=ShortTermSessionStore(),
    )


@pytest.mark.parametrize(("npc_id", "display_name", "version"), PERSONAS)
def test_composition_routes_each_approved_persona_through_dialogue_v1(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    npc_id: str,
    display_name: str,
    version: str,
) -> None:
    provider = FakeProvider([completion(f"Synthetic {display_name} reply")])
    service, _, _ = composed_service(tmp_path, provider)
    payload = request(100, npc_id=npc_id).model_dump(mode="json")

    with caplog.at_level(logging.INFO, logger="cyber_town.dialogue"):
        response = TestClient(create_app(service)).post("/api/v1/dialogue", json=payload)

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
    assert response.json()["npc_id"] == npc_id
    expected = load_bundled_personas()[npc_id]
    assert provider.requests[0].system_prompt == expected.system_prompt
    assert provider.requests[0].system_prompt.count(f"You are {display_name}") == 1
    audits = [getattr(record, "dialogue_audit", {}) for record in caplog.records]
    assert any(audit.get("persona_version") == version for audit in audits)
    assert all("npc_id" not in audit for audit in audits)


@pytest.mark.parametrize(("npc_id", "display_name", "_version"), PERSONAS)
def test_content_filter_fallback_uses_only_the_active_persona_name(
    npc_id: str,
    display_name: str,
    _version: str,
) -> None:
    provider = FakeProvider([completion("unused", finish_reason="content_filter")])

    response = run(
        direct_service(provider).execute(request(200, npc_id=npc_id), trace_id=UUID(int=300))
    )

    assert (
        response.reply == f"{display_name} pauses, keeping the conversation within safe boundaries."
    )


@pytest.mark.parametrize(
    ("player_id", "npc_id", "conversation_id"),
    [
        ("other_player", "neon_guide", UUID("22222222-2222-4222-8222-222222222222")),
        ("local_player", "night_courier", UUID("22222222-2222-4222-8222-222222222222")),
        ("local_player", "neon_guide", UUID("44444444-4444-4444-8444-444444444444")),
    ],
)
def test_changing_any_short_term_scope_dimension_starts_with_empty_history(
    player_id: str,
    npc_id: str,
    conversation_id: UUID,
) -> None:
    provider = FakeProvider([completion("First private reply"), completion("Second reply")])
    service = direct_service(provider)
    run(
        service.execute(
            request(400, npc_id="neon_guide", message="First private message"),
            trace_id=UUID(int=500),
        )
    )

    run(
        service.execute(
            request(
                401,
                player_id=player_id,
                npc_id=npc_id,
                conversation_id=conversation_id,
                message="Second message",
            ),
            trace_id=UUID(int=501),
        )
    )

    assert provider.requests[1].history_messages == ()
    assert provider.requests[1].system_prompt == load_bundled_personas()[npc_id].system_prompt


def test_unknown_npc_fails_before_provider_or_persistent_scope_writes(tmp_path: Path) -> None:
    provider = FakeProvider([])
    service, memory, relationship = composed_service(tmp_path, provider)
    unknown = request(600, npc_id="unapproved_npc")

    with pytest.raises(DialogueUseCaseError) as raised:
        run(service.execute(unknown, trace_id=UUID(int=601)))

    assert raised.value.kind is DialogueFailureKind.NPC_NOT_FOUND
    assert provider.requests == []
    assert memory.list_scope(LongTermMemoryScope("local_player", "unapproved_npc")) == ()
    snapshot = relationship.get_state(RelationshipScope("local_player", "unapproved_npc"))
    assert snapshot.score == 20


def test_long_term_and_relationship_state_remain_owned_by_player_and_npc(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            completion(
                "Synthetic Ivo reply",
                relationship_suggestion={"category": "friendly", "confidence": 80},
            ),
            completion(
                "Synthetic Rhea reply",
                relationship_suggestion={"category": "friendly", "confidence": 80},
            ),
        ]
    )
    service, memory, relationship = composed_service(tmp_path, provider)

    run(
        service.execute(
            request(700, npc_id="signal_archivist", message="Remember: game_alias=IVO-ONLY"),
            trace_id=UUID(int=800),
        )
    )
    run(
        service.execute(
            request(701, npc_id="signal_archivist", message="A normal Ivo conversation"),
            trace_id=UUID(int=801),
        )
    )
    run(
        service.execute(
            request(702, npc_id="night_courier", message="A normal Rhea conversation"),
            trace_id=UUID(int=802),
        )
    )

    ivo_memories = memory.list_scope(LongTermMemoryScope("local_player", "signal_archivist"))
    assert [item.fact_value for item in ivo_memories] == ["IVO-ONLY"]
    assert memory.list_scope(LongTermMemoryScope("local_player", "night_courier")) == ()
    assert relationship.get_state(RelationshipScope("local_player", "signal_archivist")).score == 21
    assert relationship.get_state(RelationshipScope("local_player", "night_courier")).score == 21
    assert relationship.get_state(RelationshipScope("other_player", "signal_archivist")).score == 20

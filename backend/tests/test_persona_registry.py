from __future__ import annotations

import asyncio
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
from cyber_town.application.memory import ShortTermSessionStore
from cyber_town.contracts.v1 import DialogueRequestV1
from cyber_town.domain.persona import BUNDLED_PERSONA_FILENAMES, load_bundled_personas
from cyber_town.infrastructure.llm.fake import FakeProvider


def run[T](awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def test_bundled_persona_registry_is_a_frozen_three_npc_allowlist() -> None:
    personas = load_bundled_personas()

    assert BUNDLED_PERSONA_FILENAMES == ("nia_v1.json", "ivo_v1.json", "rhea_v1.json")
    assert tuple(personas) == ("neon_guide", "signal_archivist", "night_courier")
    assert [(persona.display_name, persona.version) for persona in personas.values()] == [
        ("Nia", "nia-v1"),
        ("Ivo", "ivo-v1"),
        ("Rhea", "rhea-v1"),
    ]
    with pytest.raises(TypeError):
        personas["unapproved"] = personas["neon_guide"]  # type: ignore[index]


def test_bundled_persona_registry_keeps_persona_prompts_distinct() -> None:
    personas = load_bundled_personas()

    prompts = [persona.system_prompt for persona in personas.values()]
    assert len(set(prompts)) == 3
    assert "Ivo" in personas["signal_archivist"].system_prompt
    assert "Rhea" in personas["night_courier"].system_prompt


def test_unknown_npc_id_fails_closed_before_provider_or_memory_use() -> None:
    provider = FakeProvider([])
    service = DialogueService(
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
    request = DialogueRequestV1(
        request_id=UUID("11111111-1111-4111-8111-111111111111"),
        player_id="local_player",
        npc_id="unapproved",
        conversation_id=UUID("22222222-2222-4222-8222-222222222222"),
        message="Synthetic question",
    )

    with pytest.raises(DialogueUseCaseError) as raised:
        run(service.execute(request, trace_id=UUID("33333333-3333-4333-8333-333333333333")))

    assert raised.value.kind is DialogueFailureKind.NPC_NOT_FOUND
    assert provider.requests == []

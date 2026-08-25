"""Opt-in local application composition without SDK leakage into core layers."""

from __future__ import annotations

from cyber_town.application.dialogue import DialogueExecutionConfig, DialogueService
from cyber_town.application.provider import ProviderProtocol
from cyber_town.config import LlmProvider, Settings
from cyber_town.domain.persona import load_bundled_persona
from cyber_town.infrastructure.llm.deepseek import DeepSeekProvider


def build_dialogue_service(
    settings: Settings,
    *,
    provider: ProviderProtocol | None = None,
) -> DialogueService | None:
    """Build the dialogue use case only when the approved provider is enabled."""

    if settings.llm_provider is LlmProvider.DISABLED:
        return None

    if provider is None:
        if settings.llm_api_key is None:
            raise ValueError("The enabled dialogue provider requires a configured API key.")
        provider = DeepSeekProvider(
            credential=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    persona = load_bundled_persona("nia_v1.json")
    return DialogueService(
        personas={persona.npc_id: persona},
        provider=provider,
        config=DialogueExecutionConfig(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
            max_concurrency=settings.llm_max_concurrency,
            idempotency_ttl_seconds=settings.llm_idempotency_ttl_seconds,
            idempotency_max_entries=settings.llm_idempotency_max_entries,
        ),
    )

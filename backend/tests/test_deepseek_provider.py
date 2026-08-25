from __future__ import annotations

import asyncio
import importlib
import logging
import traceback
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from cyber_town.api.app import create_app
from cyber_town.api.composition import build_dialogue_service
from cyber_town.application.dialogue import DialogueFailureKind, DialogueUseCaseError
from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderInvalidResponseError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.config import LlmProvider, Settings
from cyber_town.contracts.v1 import DialogueRequestV1
from cyber_town.infrastructure.llm import deepseek
from cyber_town.infrastructure.llm.deepseek import DeepSeekProvider
from cyber_town.infrastructure.llm.fake import FakeProvider

REQUEST = ProviderRequest(
    system_prompt="Frozen synthetic persona prompt.",
    user_message="Where is the quiet street?",
    model="deepseek-v4-flash",
    temperature=0.6,
    max_tokens=256,
    timeout_seconds=12.0,
)


@pytest.fixture(autouse=True)
def isolate_provider_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


class StubCompletions:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class StubSdkClient:
    def __init__(self, outcome: Any) -> None:
        self.completions = StubCompletions(outcome)
        self.chat = SimpleNamespace(completions=self.completions)


def sdk_response(
    *,
    content: Any = "The east arcade stays quiet after midnight.",
    finish_reason: Any = "stop",
    choice_count: int = 1,
    tool_calls: Any = None,
    reasoning_content: Any = None,
    usage: Any = "default",
    model: Any = "deepseek-v4-flash",
) -> SimpleNamespace:
    message = SimpleNamespace(
        content=content,
        tool_calls=tool_calls,
        reasoning_content=reasoning_content,
    )
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    token_usage = (
        SimpleNamespace(prompt_tokens=23, completion_tokens=11) if usage == "default" else usage
    )
    return SimpleNamespace(choices=[choice] * choice_count, model=model, usage=token_usage)


def response_with_choices(choices: object) -> SimpleNamespace:
    response = sdk_response()
    response.choices = choices
    return response


def adapter(outcome: Any) -> tuple[DeepSeekProvider, StubSdkClient]:
    client = StubSdkClient(outcome)
    return (
        DeepSeekProvider(
            credential=SecretStr("synthetic-provider-value"),
            base_url="https://api.deepseek.com",
            timeout_seconds=12.0,
            client=client,
        ),
        client,
    )


def dialogue_request() -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=UUID("11111111-1111-4111-8111-111111111111"),
        player_id="local_player",
        npc_id="neon_guide",
        conversation_id=UUID("22222222-2222-4222-8222-222222222222"),
        message="Where is the quiet street?",
    )


def enabled_settings() -> Settings:
    return Settings.model_validate(
        {
            "llm_provider": LlmProvider.DEEPSEEK,
            "llm_api_key": SecretStr("synthetic-provider-value"),
        }
    )


def test_sdk_client_uses_approved_endpoint_timeout_and_zero_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def build_client(**kwargs: Any) -> StubSdkClient:
        captured.update(kwargs)
        return StubSdkClient(sdk_response())

    monkeypatch.setattr(deepseek, "AsyncOpenAI", build_client)

    provider = DeepSeekProvider(
        credential=SecretStr("synthetic-provider-value"),
        base_url="https://api.deepseek.com",
        timeout_seconds=12.0,
    )

    assert isinstance(provider, DeepSeekProvider)
    assert captured == {
        "api_key": "synthetic-provider-value",
        "base_url": "https://api.deepseek.com",
        "timeout": 12.0,
        "max_retries": 0,
    }


def test_adapter_sends_frozen_non_thinking_non_streaming_request() -> None:
    provider, client = adapter(sdk_response())

    result = asyncio.run(provider.complete(REQUEST))

    assert len(client.completions.calls) == 1
    assert client.completions.calls[0] == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "Frozen synthetic persona prompt."},
            {"role": "user", "content": "Where is the quiet street?"},
        ],
        "temperature": 0.6,
        "max_tokens": 256,
        "stream": False,
        "timeout": 12.0,
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    assert result == ProviderCompletion(
        content="The east arcade stays quiet after midnight.",
        finish_reason="stop",
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="deepseek",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=23, completion_tokens=11),
    )


@pytest.mark.parametrize(
    "provider_request",
    [
        replace(REQUEST, thinking_enabled=True),
        replace(REQUEST, stream=True),
        replace(REQUEST, model="unapproved-model"),
    ],
)
def test_adapter_rejects_unapproved_request_before_sdk_call(
    provider_request: ProviderRequest,
) -> None:
    provider, client = adapter(sdk_response())

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(provider.complete(provider_request))

    assert client.completions.calls == []


@pytest.mark.parametrize(
    ("response", "expected_choice_count", "expected_tool_calls", "expected_reasoning"),
    [
        (sdk_response(choice_count=0), 0, False, False),
        (sdk_response(choice_count=2), 2, False, False),
        (sdk_response(tool_calls=[object()]), 1, True, False),
        (sdk_response(reasoning_content="synthetic reasoning"), 1, False, True),
    ],
)
def test_adapter_preserves_untrusted_shape_for_application_validation(
    response: SimpleNamespace,
    expected_choice_count: int,
    expected_tool_calls: bool,
    expected_reasoning: bool,
) -> None:
    provider, _ = adapter(response)

    completion = asyncio.run(provider.complete(REQUEST))

    assert completion.choice_count == expected_choice_count
    assert completion.tool_calls_present is expected_tool_calls
    assert completion.reasoning_content_present is expected_reasoning


@pytest.mark.parametrize(
    "invalid_usage",
    [
        None,
        SimpleNamespace(prompt_tokens=-1, completion_tokens=1),
        SimpleNamespace(prompt_tokens="23", completion_tokens=1),
        SimpleNamespace(prompt_tokens=23, completion_tokens=True),
    ],
)
def test_missing_or_invalid_usage_fails_closed(invalid_usage: Any) -> None:
    provider, client = adapter(sdk_response(usage=invalid_usage))

    with pytest.raises(ProviderInvalidResponseError, match="invalid response"):
        asyncio.run(provider.complete(REQUEST))

    assert len(client.completions.calls) == 1


def test_sdk_timeout_is_classified_without_exposing_raw_details() -> None:
    request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
    sdk_error = openai.APITimeoutError(request=request)
    provider, client = adapter(sdk_error)

    with pytest.raises(ProviderTimeoutError, match="timed out") as captured:
        asyncio.run(provider.complete(REQUEST))

    assert captured.value.__cause__ is None
    assert len(client.completions.calls) == 1


@pytest.mark.parametrize("status_code", [401, 429, 500, 503])
def test_sdk_status_failures_are_classified_and_redacted(status_code: int) -> None:
    request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx2.Response(status_code, request=request)
    raw_error = "synthetic-private-provider-detail"
    sdk_error = openai.APIStatusError(raw_error, response=response, body={"detail": raw_error})
    provider, client = adapter(sdk_error)

    with pytest.raises(ProviderUnavailableError) as captured:
        asyncio.run(provider.complete(REQUEST))

    assert raw_error not in str(captured.value)
    assert raw_error not in "".join(traceback.format_exception(captured.value))
    assert captured.value.__cause__ is None
    assert len(client.completions.calls) == 1


def test_sdk_connection_failure_is_classified_without_automatic_retry() -> None:
    request = httpx2.Request("POST", "https://api.deepseek.com/chat/completions")
    sdk_error = openai.APIConnectionError(message="synthetic-network-detail", request=request)
    provider, client = adapter(sdk_error)

    with pytest.raises(ProviderUnavailableError) as captured:
        asyncio.run(provider.complete(REQUEST))

    assert "synthetic-network-detail" not in str(captured.value)
    assert len(client.completions.calls) == 1


def test_disabled_composition_never_constructs_a_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cyber_town.api.composition.DeepSeekProvider",
        lambda **_kwargs: pytest.fail("disabled provider attempted SDK construction"),
    )

    assert build_dialogue_service(Settings.model_validate({})) is None


def test_enabled_composition_accepts_only_an_injected_offline_test_provider() -> None:
    completion = ProviderCompletion(
        content="Nia points toward the quiet east arcade.",
        finish_reason="stop",
        choice_count=1,
        tool_calls_present=False,
        reasoning_content_present=False,
        provider="fake",
        model="deepseek-v4-flash",
        usage=ProviderUsage(prompt_tokens=23, completion_tokens=11),
    )
    provider = FakeProvider([completion])
    service = build_dialogue_service(enabled_settings(), provider=provider)

    assert service is not None
    result = asyncio.run(
        service.execute(
            dialogue_request(),
            trace_id=UUID("33333333-3333-4333-8333-333333333333"),
        )
    )
    assert result.reply == "Nia points toward the quiet east arcade."
    assert provider.call_count == 1


def test_invalid_sdk_completion_becomes_a_safe_application_failure() -> None:
    provider, _ = adapter(sdk_response(reasoning_content="synthetic hidden reasoning"))
    service = build_dialogue_service(enabled_settings(), provider=provider)

    assert service is not None
    with pytest.raises(DialogueUseCaseError) as captured:
        asyncio.run(
            service.execute(
                dialogue_request(),
                trace_id=UUID("33333333-3333-4333-8333-333333333333"),
            )
        )

    assert captured.value.kind is DialogueFailureKind.PROVIDER_INVALID_RESPONSE
    assert "synthetic hidden reasoning" not in captured.value.public_message


def test_composed_offline_provider_is_reachable_through_the_dialogue_route() -> None:
    provider, sdk_client = adapter(sdk_response())
    service = build_dialogue_service(enabled_settings(), provider=provider)

    assert service is not None
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/v1/dialogue",
            json=dialogue_request().model_dump(mode="json"),
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "deepseek"
    assert response.json()["reply"] == "The east arcade stays quiet after midnight."
    assert len(sdk_client.completions.calls) == 1


@pytest.mark.parametrize(
    "malformed_response",
    [
        sdk_response(model="unapproved-response-model"),
        sdk_response(usage=None),
        sdk_response(usage=SimpleNamespace(prompt_tokens=True, completion_tokens=1)),
        response_with_choices({"wrong": SimpleNamespace()}),
        response_with_choices({0: sdk_response().choices[0]}),
        response_with_choices(tuple(sdk_response().choices)),
    ],
)
def test_invalid_sdk_response_is_mapped_to_public_http_502(
    malformed_response: SimpleNamespace,
) -> None:
    provider, sdk_client = adapter(malformed_response)
    service = build_dialogue_service(enabled_settings(), provider=provider)

    assert service is not None
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/v1/dialogue",
            json=dialogue_request().model_dump(mode="json"),
        )

    assert response.status_code == 502
    assert response.json()["code"] == "provider_unavailable"
    assert len(sdk_client.completions.calls) == 1


def test_sdk_debug_logging_never_emits_prompt_or_player_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    synthetic_prompt = "synthetic-private-system-prompt-7194"
    synthetic_message = "synthetic-private-player-message-3821"

    def handle(request: httpx2.Request) -> httpx2.Response:
        del request
        return httpx2.Response(
            200,
            json={
                "id": "synthetic-completion",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Synthetic reply."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    sdk_options: dict[str, Any] = {"api_key": "synthetic-provider-value"}
    sdk_client = openai.AsyncOpenAI(
        **sdk_options,
        base_url="https://api.deepseek.com",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    provider = DeepSeekProvider(
        credential=SecretStr("synthetic-provider-value"),
        base_url="https://api.deepseek.com",
        timeout_seconds=12.0,
        client=sdk_client,
    )

    with caplog.at_level(logging.DEBUG, logger="openai._base_client"):
        asyncio.run(
            provider.complete(
                replace(REQUEST, system_prompt=synthetic_prompt, user_message=synthetic_message)
            )
        )

    assert synthetic_prompt not in caplog.text
    assert synthetic_message not in caplog.text


def test_entrypoint_installs_enabled_dialogue_service_before_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    api_main = importlib.import_module("cyber_town.api.__main__")
    provider = FakeProvider([])
    service = build_dialogue_service(enabled_settings(), provider=provider)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    assert service is not None
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-provider-value")
    monkeypatch.setattr(api_main.app.state, "dialogue_service", None)
    monkeypatch.setattr(api_main, "build_dialogue_service", lambda _settings: service)
    monkeypatch.setattr(
        api_main.uvicorn,
        "run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    api_main.main()

    assert api_main.app.state.dialogue_service is service
    assert calls == [((api_main.app,), {"host": "127.0.0.1", "port": 8000})]
    assert provider.call_count == 0

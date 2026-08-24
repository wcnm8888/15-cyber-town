from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from cyber_town.config import AppEnvironment, LlmProvider, Settings

CONFIG_ENV_NAMES = (
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
)


@pytest.fixture(autouse=True)
def isolate_settings_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep configuration tests independent from developer env and local .env files."""

    for name in CONFIG_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.chdir(tmp_path)


def test_default_settings_do_not_require_a_real_provider_key() -> None:
    settings = Settings.model_validate({})

    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.llm_provider is LlmProvider.DISABLED
    assert settings.llm_api_key is None


@pytest.mark.parametrize("key", [None, "", "   "])
def test_enabled_provider_requires_a_nonempty_api_key(key: str | None) -> None:
    payload: dict[str, object] = {"llm_provider": LlmProvider.DEEPSEEK}
    if key is not None:
        payload["llm_api_key"] = key

    with pytest.raises(ValidationError, match="LLM_API_KEY is required"):
        Settings.model_validate(payload)


def test_lowercase_environment_names_follow_settings_case_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("llm_provider", "deepseek")
    monkeypatch.setenv("llm_api_key", "synthetic-lowercase-config-value")

    settings = Settings.model_validate({})

    assert settings.llm_provider is LlmProvider.DEEPSEEK


def test_provider_key_is_redacted_from_settings_representation() -> None:
    synthetic_value = "synthetic-secret-value"

    settings = Settings.model_validate(
        {
            "llm_provider": LlmProvider.DEEPSEEK,
            "llm_api_key": SecretStr(synthetic_value),
        }
    )

    assert synthetic_value not in repr(settings)


def test_provider_key_is_redacted_from_validation_errors() -> None:
    synthetic_value = "synthetic-validation-secret-value"

    with pytest.raises(ValidationError) as captured:
        Settings.model_validate({"app_port": 0, "llm_api_key": SecretStr(synthetic_value)})

    assert synthetic_value not in str(captured.value)


@pytest.mark.parametrize("port", [0, 65_536])
def test_port_must_be_in_tcp_range(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"app_port": port})

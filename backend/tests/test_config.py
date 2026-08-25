from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings.sources import DotEnvSettingsSource

from cyber_town.config import AppEnvironment, LlmProvider, Settings

CONFIG_ENV_NAMES = (
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_TEMPERATURE",
    "LLM_MAX_TOKENS",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_MAX_CONCURRENCY",
    "LLM_IDEMPOTENCY_TTL_SECONDS",
    "LLM_IDEMPOTENCY_MAX_ENTRIES",
    "LLM_THINKING_ENABLED",
    "LLM_STREAM",
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
    assert settings.llm_model == "deepseek-v4-flash"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_temperature == 0.6
    assert settings.llm_max_tokens == 256
    assert settings.llm_timeout_seconds == 12.0
    assert settings.llm_max_retries == 0
    assert settings.llm_max_concurrency == 2
    assert settings.llm_idempotency_ttl_seconds == 600
    assert settings.llm_idempotency_max_entries == 256
    assert settings.llm_thinking_enabled is False
    assert settings.llm_stream is False


def test_automation_can_disable_dotenv_before_any_file_is_opened(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text("LLM_API_KEY=synthetic-dotenv-value\n", encoding="utf-8")
    monkeypatch.setenv("CYBER_TOWN_DISABLE_DOTENV", "1")

    def reject_dotenv_read(*_args: object, **_kwargs: object) -> dict[str, str]:
        raise AssertionError("automated execution attempted to open a dotenv file")

    monkeypatch.setattr(DotEnvSettingsSource, "_read_env_file", reject_dotenv_read)

    settings = Settings.model_validate({})

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


def test_approved_llm_settings_parse_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved_values = {
        "LLM_TEMPERATURE": "0.6",
        "LLM_MAX_TOKENS": "256",
        "LLM_TIMEOUT_SECONDS": "12",
        "LLM_MAX_RETRIES": "0",
        "LLM_MAX_CONCURRENCY": "2",
        "LLM_IDEMPOTENCY_TTL_SECONDS": "600",
        "LLM_IDEMPOTENCY_MAX_ENTRIES": "256",
        "LLM_THINKING_ENABLED": "false",
        "LLM_STREAM": "false",
    }
    for name, value in approved_values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.model_validate({})

    assert settings.llm_temperature == 0.6
    assert settings.llm_max_tokens == 256
    assert settings.llm_timeout_seconds == 12.0
    assert settings.llm_max_retries == 0
    assert settings.llm_max_concurrency == 2
    assert settings.llm_idempotency_ttl_seconds == 600
    assert settings.llm_idempotency_max_entries == 256
    assert settings.llm_thinking_enabled is False
    assert settings.llm_stream is False


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_temperature", -0.1),
        ("llm_temperature", 2.1),
        ("llm_max_tokens", 0),
        ("llm_max_tokens", 1_025),
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", 60.1),
        ("llm_max_concurrency", 0),
        ("llm_max_concurrency", 9),
        ("llm_idempotency_ttl_seconds", 0),
        ("llm_idempotency_ttl_seconds", 3_601),
        ("llm_idempotency_max_entries", 0),
        ("llm_idempotency_max_entries", 4_097),
    ],
)
def test_llm_resource_settings_reject_out_of_bounds_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_temperature", 0.7),
        ("llm_max_tokens", 257),
        ("llm_timeout_seconds", 13.0),
        ("llm_max_concurrency", 3),
        ("llm_idempotency_ttl_seconds", 601),
        ("llm_idempotency_max_entries", 257),
    ],
)
def test_f003_rejects_in_range_drift_from_approved_execution_policy(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError, match="must remain"):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_max_retries", 1),
        ("llm_thinking_enabled", True),
        ("llm_stream", True),
    ],
)
def test_f003_forbids_automatic_retry_thinking_and_streaming(
    field: str,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.deepseek.com",
        "https://example.com",
        "https://api.deepseek.com/v1",
        "https://user:password@api.deepseek.com",
    ],
)
def test_deepseek_provider_rejects_unapproved_base_urls(base_url: str) -> None:
    with pytest.raises(ValidationError, match="LLM_BASE_URL must be"):
        Settings.model_validate(
            {
                "llm_provider": LlmProvider.DEEPSEEK,
                "llm_api_key": "synthetic-provider-key",
                "llm_base_url": base_url,
            }
        )


def test_deepseek_provider_rejects_unapproved_model() -> None:
    with pytest.raises(ValidationError, match="LLM_MODEL must be"):
        Settings.model_validate(
            {
                "llm_provider": LlmProvider.DEEPSEEK,
                "llm_api_key": "synthetic-provider-key",
                "llm_model": "different-model",
            }
        )


def test_provider_key_is_redacted_when_provider_configuration_is_invalid() -> None:
    synthetic_value = "synthetic-invalid-provider-secret-value"

    with pytest.raises(ValidationError) as captured:
        Settings.model_validate(
            {
                "llm_provider": LlmProvider.DEEPSEEK,
                "llm_api_key": SecretStr(synthetic_value),
                "llm_base_url": "https://example.com",
            }
        )

    assert synthetic_value not in str(captured.value)


@pytest.mark.parametrize("port", [0, 65_536])
def test_port_must_be_in_tcp_range(port: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"app_port": port})

"""Validated application settings with secret-safe representations."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported local application environments."""

    DEVELOPMENT = "development"
    TEST = "test"


class LlmProvider(StrEnum):
    """Providers allowed by the engineering baseline."""

    DISABLED = "disabled"
    DEEPSEEK = "deepseek"


DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class Settings(BaseSettings):
    """Load and validate configuration without exposing secret values."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    app_host: str = Field(default="127.0.0.1", min_length=1)
    app_port: int = Field(default=8000, ge=1, le=65_535)

    llm_provider: LlmProvider = LlmProvider.DISABLED
    llm_model: str = Field(default=DEEPSEEK_MODEL, min_length=1)
    llm_api_key: SecretStr | None = None
    llm_base_url: str = Field(default=DEEPSEEK_BASE_URL, min_length=1)
    llm_temperature: float = Field(default=0.6, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=256, ge=1, le=1_024)
    llm_timeout_seconds: float = Field(default=12.0, ge=0.1, le=60.0)
    llm_max_retries: int = Field(default=0, ge=0, le=0)
    llm_max_concurrency: int = Field(default=2, ge=1, le=8)
    llm_idempotency_ttl_seconds: int = Field(default=600, ge=1, le=3_600)
    llm_idempotency_max_entries: int = Field(default=256, ge=1, le=4_096)
    llm_thinking_enabled: bool = False
    llm_stream: bool = False

    def __init__(self, **values: Any) -> None:
        if os.environ.get("CYBER_TOWN_DISABLE_DOTENV") == "1":
            values["_env_file"] = None
        super().__init__(**values)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        del settings_cls
        if os.environ.get("CYBER_TOWN_DISABLE_DOTENV") == "1":
            return init_settings, env_settings, file_secret_settings
        return init_settings, env_settings, dotenv_settings, file_secret_settings

    @model_validator(mode="after")
    def require_key_for_enabled_provider(self) -> Self:
        """Reject an enabled provider unless a non-empty secret is supplied."""

        frozen_values: tuple[tuple[str, object, object], ...] = (
            ("LLM_TEMPERATURE", self.llm_temperature, 0.6),
            ("LLM_MAX_TOKENS", self.llm_max_tokens, 256),
            ("LLM_TIMEOUT_SECONDS", self.llm_timeout_seconds, 12.0),
            ("LLM_MAX_CONCURRENCY", self.llm_max_concurrency, 2),
            ("LLM_IDEMPOTENCY_TTL_SECONDS", self.llm_idempotency_ttl_seconds, 600),
            ("LLM_IDEMPOTENCY_MAX_ENTRIES", self.llm_idempotency_max_entries, 256),
        )
        for name, actual, expected in frozen_values:
            if actual != expected:
                raise ValueError(f"{name} must remain {expected} for F-003")

        if self.llm_thinking_enabled:
            raise ValueError("LLM_THINKING_ENABLED must remain false for F-003")

        if self.llm_stream:
            raise ValueError("LLM_STREAM must remain false for F-003")

        if self.llm_provider is LlmProvider.DISABLED:
            return self

        if self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip():
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER is enabled")

        if self.llm_model != DEEPSEEK_MODEL:
            raise ValueError(f"LLM_MODEL must be {DEEPSEEK_MODEL!r} for the DeepSeek provider")

        if self.llm_base_url != DEEPSEEK_BASE_URL:
            raise ValueError(
                f"LLM_BASE_URL must be {DEEPSEEK_BASE_URL!r} for the DeepSeek provider"
            )

        return self

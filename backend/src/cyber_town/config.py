"""Validated application settings with secret-safe representations."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Supported local application environments."""

    DEVELOPMENT = "development"
    TEST = "test"


class LlmProvider(StrEnum):
    """Providers allowed by the engineering baseline."""

    DISABLED = "disabled"
    DEEPSEEK = "deepseek"


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
    llm_model: str = Field(default="deepseek-v4-flash", min_length=1)
    llm_api_key: SecretStr | None = None
    llm_base_url: str = Field(default="https://api.deepseek.com", min_length=1)

    @model_validator(mode="after")
    def require_key_for_enabled_provider(self) -> Self:
        """Reject an enabled provider unless a non-empty secret is supplied."""

        if self.llm_provider is LlmProvider.DISABLED:
            return self

        if self.llm_api_key is None or not self.llm_api_key.get_secret_value().strip():
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER is enabled")

        return self

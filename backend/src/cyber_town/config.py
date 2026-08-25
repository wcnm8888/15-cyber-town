"""Validated application settings with secret-safe representations."""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import Field, SecretStr, field_validator, model_validator
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
MEMORY_SCOPE_FIELDS: tuple[str, str, str] = ("player_id", "npc_id", "conversation_id")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LONG_TERM_MEMORY_SCOPE_FIELDS: tuple[str, str] = ("player_id", "npc_id")
LONG_TERM_MEMORY_ALLOWED_FACT_KEYS: tuple[str, str, str, str] = (
    "game_alias",
    "preferred_language",
    "reply_style",
    "favorite_cyber_town_topic",
)
LONG_TERM_MEMORY_DATABASE_PATH = Path("data/cyber-town.sqlite3")
LONG_TERM_MEMORY_UAT_DATABASE_ROOT = Path("data/uat/f-005")
LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH = Path("data/acceptance-ledgers/f-005.sqlite3")


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

    memory_scope_fields: tuple[str, str, str] = MEMORY_SCOPE_FIELDS
    memory_max_turns: int = Field(default=6, gt=0)
    memory_max_sessions: int = Field(default=128, gt=0)
    memory_idle_ttl_seconds: int = Field(default=1_800, gt=0)
    memory_context_budget_units: int = Field(default=8_192, gt=0)
    memory_request_overhead_units: int = Field(default=64, gt=0)
    memory_message_overhead_units: int = Field(default=16, gt=0)
    memory_response_reserve_units: int = Field(default=256, gt=0)
    memory_scope_wait_seconds: float = Field(default=2.0, gt=0, allow_inf_nan=False)

    long_term_memory_scope_fields: tuple[str, str] = LONG_TERM_MEMORY_SCOPE_FIELDS
    long_term_memory_allowed_fact_keys: tuple[str, str, str, str] = (
        LONG_TERM_MEMORY_ALLOWED_FACT_KEYS
    )
    long_term_memory_max_per_scope: int = Field(default=64, gt=0)
    long_term_memory_max_total: int = Field(default=4_096, gt=0)
    long_term_memory_max_recall: int = Field(default=4, gt=0)
    long_term_memory_default_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    long_term_memory_context_budget_units: int = Field(default=2_048, gt=0)
    long_term_memory_sqlite_busy_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        allow_inf_nan=False,
    )
    long_term_memory_database_path: Path = LONG_TERM_MEMORY_DATABASE_PATH
    long_term_memory_uat_database_root: Path = LONG_TERM_MEMORY_UAT_DATABASE_ROOT
    long_term_memory_acceptance_ledger_path: Path = LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH

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

    @field_validator(
        "memory_max_turns",
        "memory_max_sessions",
        "memory_idle_ttl_seconds",
        "memory_context_budget_units",
        "memory_request_overhead_units",
        "memory_message_overhead_units",
        "memory_response_reserve_units",
        mode="before",
    )
    @classmethod
    def reject_noninteger_memory_policy_values(cls, value: object) -> object:
        """Reject bool/float coercion while retaining normal environment parsing."""

        if isinstance(value, (bool, float)):
            raise ValueError("Short-term memory policy values must be integers")
        return value

    @field_validator(
        "long_term_memory_max_per_scope",
        "long_term_memory_max_total",
        "long_term_memory_max_recall",
        "long_term_memory_default_ttl_seconds",
        "long_term_memory_context_budget_units",
        mode="before",
    )
    @classmethod
    def reject_noninteger_long_term_memory_policy_values(cls, value: object) -> object:
        """Reject bool/float coercion without breaking normal environment parsing."""

        if isinstance(value, (bool, float)):
            raise ValueError("Long-term memory policy values must be integers")
        return value

    @field_validator(
        "long_term_memory_database_path",
        "long_term_memory_uat_database_root",
        "long_term_memory_acceptance_ledger_path",
        mode="before",
    )
    @classmethod
    def reject_escaping_long_term_memory_paths(cls, value: object) -> object:
        """Reject external and parent-traversing SQLite paths without opening them."""

        if not isinstance(value, (str, Path)):
            raise ValueError("Long-term memory paths must be strings or paths")

        candidate = Path(value)
        if candidate.anchor or ".." in candidate.parts or not candidate.parts:
            raise ValueError("Long-term memory paths must remain inside project data")
        return candidate

    def _validate_long_term_memory_paths(self) -> None:
        """Keep every approved runtime location inside non-linked project data."""

        data_root = PROJECT_ROOT / "data"
        approved_paths = (
            ("LONG_TERM_MEMORY_DATABASE_PATH", self.long_term_memory_database_path),
            ("LONG_TERM_MEMORY_UAT_DATABASE_ROOT", self.long_term_memory_uat_database_root),
            (
                "LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH",
                self.long_term_memory_acceptance_ledger_path,
            ),
        )
        resolved_data_root = data_root.resolve(strict=False)

        for name, relative_path in approved_paths:
            candidate = PROJECT_ROOT / relative_path
            if not candidate.resolve(strict=False).is_relative_to(resolved_data_root):
                raise ValueError(f"{name} must remain inside project data")

            for current in (candidate, *candidate.parents):
                if current == PROJECT_ROOT:
                    break
                if current.is_symlink() or current.is_junction():
                    raise ValueError(f"{name} must not traverse symbolic links or junctions")

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

        memory_frozen_values: tuple[tuple[str, object, object], ...] = (
            ("MEMORY_SCOPE_FIELDS", self.memory_scope_fields, MEMORY_SCOPE_FIELDS),
            ("MEMORY_MAX_TURNS", self.memory_max_turns, 6),
            ("MEMORY_MAX_SESSIONS", self.memory_max_sessions, 128),
            ("MEMORY_IDLE_TTL_SECONDS", self.memory_idle_ttl_seconds, 1_800),
            ("MEMORY_CONTEXT_BUDGET_UNITS", self.memory_context_budget_units, 8_192),
            ("MEMORY_REQUEST_OVERHEAD_UNITS", self.memory_request_overhead_units, 64),
            ("MEMORY_MESSAGE_OVERHEAD_UNITS", self.memory_message_overhead_units, 16),
            ("MEMORY_RESPONSE_RESERVE_UNITS", self.memory_response_reserve_units, 256),
            ("MEMORY_SCOPE_WAIT_SECONDS", self.memory_scope_wait_seconds, 2.0),
        )
        for name, actual, expected in memory_frozen_values:
            if actual != expected:
                raise ValueError(f"{name} must remain {expected} for F-004")

        long_term_frozen_values: tuple[tuple[str, object, object], ...] = (
            (
                "LONG_TERM_MEMORY_SCOPE_FIELDS",
                self.long_term_memory_scope_fields,
                LONG_TERM_MEMORY_SCOPE_FIELDS,
            ),
            (
                "LONG_TERM_MEMORY_ALLOWED_FACT_KEYS",
                self.long_term_memory_allowed_fact_keys,
                LONG_TERM_MEMORY_ALLOWED_FACT_KEYS,
            ),
            ("LONG_TERM_MEMORY_MAX_PER_SCOPE", self.long_term_memory_max_per_scope, 64),
            ("LONG_TERM_MEMORY_MAX_TOTAL", self.long_term_memory_max_total, 4_096),
            ("LONG_TERM_MEMORY_MAX_RECALL", self.long_term_memory_max_recall, 4),
            (
                "LONG_TERM_MEMORY_DEFAULT_TTL_SECONDS",
                self.long_term_memory_default_ttl_seconds,
                30 * 24 * 60 * 60,
            ),
            (
                "LONG_TERM_MEMORY_CONTEXT_BUDGET_UNITS",
                self.long_term_memory_context_budget_units,
                2_048,
            ),
            (
                "LONG_TERM_MEMORY_SQLITE_BUSY_TIMEOUT_SECONDS",
                self.long_term_memory_sqlite_busy_timeout_seconds,
                2.0,
            ),
            (
                "LONG_TERM_MEMORY_DATABASE_PATH",
                self.long_term_memory_database_path,
                LONG_TERM_MEMORY_DATABASE_PATH,
            ),
            (
                "LONG_TERM_MEMORY_UAT_DATABASE_ROOT",
                self.long_term_memory_uat_database_root,
                LONG_TERM_MEMORY_UAT_DATABASE_ROOT,
            ),
            (
                "LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH",
                self.long_term_memory_acceptance_ledger_path,
                LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH,
            ),
        )
        for name, actual, expected in long_term_frozen_values:
            if actual != expected:
                raise ValueError(f"{name} must remain {expected} for F-005")

        self._validate_long_term_memory_paths()

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

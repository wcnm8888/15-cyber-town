from __future__ import annotations

from pathlib import Path

import pytest
from pathspec import GitIgnoreSpec
from pydantic import SecretStr, ValidationError
from pydantic_settings.sources import DotEnvSettingsSource

import cyber_town.config as config
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
    "MEMORY_SCOPE_FIELDS",
    "MEMORY_MAX_TURNS",
    "MEMORY_MAX_SESSIONS",
    "MEMORY_IDLE_TTL_SECONDS",
    "MEMORY_CONTEXT_BUDGET_UNITS",
    "MEMORY_REQUEST_OVERHEAD_UNITS",
    "MEMORY_MESSAGE_OVERHEAD_UNITS",
    "MEMORY_RESPONSE_RESERVE_UNITS",
    "MEMORY_SCOPE_WAIT_SECONDS",
    "LONG_TERM_MEMORY_SCOPE_FIELDS",
    "LONG_TERM_MEMORY_ALLOWED_FACT_KEYS",
    "LONG_TERM_MEMORY_MAX_PER_SCOPE",
    "LONG_TERM_MEMORY_MAX_TOTAL",
    "LONG_TERM_MEMORY_MAX_RECALL",
    "LONG_TERM_MEMORY_DEFAULT_TTL_SECONDS",
    "LONG_TERM_MEMORY_CONTEXT_BUDGET_UNITS",
    "LONG_TERM_MEMORY_SQLITE_BUSY_TIMEOUT_SECONDS",
    "LONG_TERM_MEMORY_DATABASE_PATH",
    "LONG_TERM_MEMORY_UAT_DATABASE_ROOT",
    "LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH",
)

F004_NUMERIC_MEMORY_POLICY: tuple[tuple[str, int | float], ...] = (
    ("memory_max_turns", 6),
    ("memory_max_sessions", 128),
    ("memory_idle_ttl_seconds", 1_800),
    ("memory_context_budget_units", 8_192),
    ("memory_request_overhead_units", 64),
    ("memory_message_overhead_units", 16),
    ("memory_response_reserve_units", 256),
    ("memory_scope_wait_seconds", 2.0),
)

F005_NUMERIC_MEMORY_POLICY: tuple[tuple[str, int | float], ...] = (
    ("long_term_memory_max_per_scope", 64),
    ("long_term_memory_max_total", 4_096),
    ("long_term_memory_max_recall", 4),
    ("long_term_memory_default_ttl_seconds", 30 * 24 * 60 * 60),
    ("long_term_memory_context_budget_units", 2_048),
    ("long_term_memory_sqlite_busy_timeout_seconds", 2.0),
)

F005_APPROVED_PATHS: tuple[tuple[str, Path], ...] = (
    ("long_term_memory_database_path", Path("data/cyber-town.sqlite3")),
    ("long_term_memory_uat_database_root", Path("data/uat/f-005")),
    (
        "long_term_memory_acceptance_ledger_path",
        Path("data/acceptance-ledgers/f-005.sqlite3"),
    ),
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


def test_f004_freezes_default_short_term_memory_policy() -> None:
    settings = Settings.model_validate({})

    assert settings.memory_scope_fields == ("player_id", "npc_id", "conversation_id")
    for field, expected in F004_NUMERIC_MEMORY_POLICY:
        assert getattr(settings, field) == expected
    assert settings.memory_response_reserve_units == settings.llm_max_tokens


def test_f004_approved_memory_policy_parses_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved_values = {
        "MEMORY_SCOPE_FIELDS": '["player_id", "npc_id", "conversation_id"]',
        "MEMORY_MAX_TURNS": "6",
        "MEMORY_MAX_SESSIONS": "128",
        "MEMORY_IDLE_TTL_SECONDS": "1800",
        "MEMORY_CONTEXT_BUDGET_UNITS": "8192",
        "MEMORY_REQUEST_OVERHEAD_UNITS": "64",
        "MEMORY_MESSAGE_OVERHEAD_UNITS": "16",
        "MEMORY_RESPONSE_RESERVE_UNITS": "256",
        "MEMORY_SCOPE_WAIT_SECONDS": "2",
    }
    for name, value in approved_values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.model_validate({})

    assert settings.memory_scope_fields == ("player_id", "npc_id", "conversation_id")
    for field, expected in F004_NUMERIC_MEMORY_POLICY:
        assert getattr(settings, field) == expected


@pytest.mark.parametrize(
    "scope_fields",
    [
        (),
        ("player_id", "npc_id"),
        ("player_id", "npc_id", "conversation_id", "request_id"),
        ("npc_id", "player_id", "conversation_id"),
        ("player_id", "npc_id", "request_id"),
        ("player_id", "player_id", "conversation_id"),
        ("player_id", "npc_id", None),
        ("player_id", "npc_id", 123),
        "player_id,npc_id,conversation_id",
        {"player_id": "player", "npc_id": "npc", "conversation_id": "session"},
    ],
)
def test_f004_rejects_missing_reordered_or_invalid_conversation_scope(
    scope_fields: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"memory_scope_fields": scope_fields})


@pytest.mark.parametrize(("field", "approved"), F004_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("offset", [-1, 1])
def test_f004_rejects_in_range_drift_from_frozen_memory_policy(
    field: str,
    approved: int | float,
    offset: int,
) -> None:
    with pytest.raises(ValidationError, match="must remain"):
        Settings.model_validate({field: approved + offset})


@pytest.mark.parametrize(("field", "_approved"), F004_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("value", [0, -1])
def test_f004_rejects_nonpositive_memory_policy_values(
    field: str,
    _approved: int | float,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(("field", "_approved"), F004_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("value", [None, True, 1.5, "not-a-number", {}, []])
def test_f004_rejects_invalid_memory_policy_types(
    field: str,
    _approved: int | float,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(("field", "approved"), F004_NUMERIC_MEMORY_POLICY[:-1])
def test_f004_integer_memory_policy_rejects_integral_float_values(
    field: str,
    approved: int | float,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: float(approved)})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_f004_scope_wait_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"memory_scope_wait_seconds": value})


def test_f004_scope_environment_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORY_SCOPE_FIELDS", '["npc_id", "player_id", "conversation_id"]')

    with pytest.raises(ValidationError, match="MEMORY_SCOPE_FIELDS must remain"):
        Settings.model_validate({})


def test_f004_numeric_environment_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMORY_CONTEXT_BUDGET_UNITS", "8193")

    with pytest.raises(ValidationError, match="MEMORY_CONTEXT_BUDGET_UNITS must remain"):
        Settings.model_validate({})


def test_f005_freezes_default_long_term_memory_policy() -> None:
    settings = Settings.model_validate({})

    assert settings.long_term_memory_scope_fields == ("player_id", "npc_id")
    assert settings.long_term_memory_allowed_fact_keys == (
        "game_alias",
        "preferred_language",
        "reply_style",
        "favorite_cyber_town_topic",
    )
    for field, expected in F005_NUMERIC_MEMORY_POLICY:
        assert getattr(settings, field) == expected
    for field, expected_path in F005_APPROVED_PATHS:
        assert getattr(settings, field) == expected_path
    assert settings.memory_context_budget_units == 8_192
    assert settings.memory_response_reserve_units == 256
    assert settings.long_term_memory_context_budget_units < settings.memory_context_budget_units


def test_f005_approved_memory_policy_parses_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved_values = {
        "LONG_TERM_MEMORY_SCOPE_FIELDS": '["player_id", "npc_id"]',
        "LONG_TERM_MEMORY_ALLOWED_FACT_KEYS": (
            '["game_alias", "preferred_language", "reply_style", "favorite_cyber_town_topic"]'
        ),
        "LONG_TERM_MEMORY_MAX_PER_SCOPE": "64",
        "LONG_TERM_MEMORY_MAX_TOTAL": "4096",
        "LONG_TERM_MEMORY_MAX_RECALL": "4",
        "LONG_TERM_MEMORY_DEFAULT_TTL_SECONDS": "2592000",
        "LONG_TERM_MEMORY_CONTEXT_BUDGET_UNITS": "2048",
        "LONG_TERM_MEMORY_SQLITE_BUSY_TIMEOUT_SECONDS": "2",
        "LONG_TERM_MEMORY_DATABASE_PATH": "data/cyber-town.sqlite3",
        "LONG_TERM_MEMORY_UAT_DATABASE_ROOT": "data/uat/f-005",
        "LONG_TERM_MEMORY_ACCEPTANCE_LEDGER_PATH": "data/acceptance-ledgers/f-005.sqlite3",
    }
    for name, value in approved_values.items():
        monkeypatch.setenv(name, value)

    settings = Settings.model_validate({})

    assert settings.long_term_memory_scope_fields == ("player_id", "npc_id")
    for field, expected in F005_NUMERIC_MEMORY_POLICY:
        assert getattr(settings, field) == expected
    for field, expected_path in F005_APPROVED_PATHS:
        assert getattr(settings, field) == expected_path


@pytest.mark.parametrize(
    "scope_fields",
    [
        (),
        ("player_id",),
        ("npc_id", "player_id"),
        ("player_id", "npc_id", "conversation_id"),
        ("player_id", "player_id"),
        ("player_id", None),
        "player_id,npc_id",
        {"player_id": "player", "npc_id": "npc"},
    ],
)
def test_f005_rejects_invalid_long_term_scope(scope_fields: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"long_term_memory_scope_fields": scope_fields})


@pytest.mark.parametrize(
    "fact_keys",
    [
        (),
        ("game_alias", "preferred_language", "reply_style"),
        ("game_alias", "preferred_language", "reply_style", "unapproved"),
        ("preferred_language", "game_alias", "reply_style", "favorite_cyber_town_topic"),
        ("game_alias", "game_alias", "reply_style", "favorite_cyber_town_topic"),
        ("game_alias", "preferred_language", "reply_style", None),
        "game_alias,preferred_language,reply_style,favorite_cyber_town_topic",
        {"game_alias": "allowed"},
    ],
)
def test_f005_rejects_unapproved_or_invalid_fact_keys(fact_keys: object) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"long_term_memory_allowed_fact_keys": fact_keys})


@pytest.mark.parametrize(("field", "approved"), F005_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("offset", [-1, 1])
def test_f005_rejects_drift_from_frozen_long_term_memory_policy(
    field: str,
    approved: int | float,
    offset: int,
) -> None:
    with pytest.raises(ValidationError, match="must remain"):
        Settings.model_validate({field: approved + offset})


@pytest.mark.parametrize(("field", "_approved"), F005_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("value", [0, -1])
def test_f005_rejects_nonpositive_long_term_memory_policy_values(
    field: str,
    _approved: int | float,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(("field", "_approved"), F005_NUMERIC_MEMORY_POLICY)
@pytest.mark.parametrize("value", [None, True, 1.5, "not-a-number", {}, []])
def test_f005_rejects_invalid_long_term_memory_policy_types(
    field: str,
    _approved: int | float,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(("field", "approved"), F005_NUMERIC_MEMORY_POLICY[:-1])
def test_f005_integer_policy_rejects_integral_float_values(
    field: str,
    approved: int | float,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: float(approved)})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_f005_sqlite_busy_timeout_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"long_term_memory_sqlite_busy_timeout_seconds": value})


@pytest.mark.parametrize(("field", "_approved"), F005_APPROVED_PATHS)
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        123,
        {},
        [],
        "../other-project.sqlite3",
        "data/../other-project.sqlite3",
        "/outside/project.sqlite3",
        "E:/Agent/comprehensive-cases/13-intelligent-travel-assistant/private.sqlite3",
    ],
)
def test_f005_rejects_invalid_or_escaping_sqlite_paths(
    field: str,
    _approved: Path,
    value: object,
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("long_term_memory_database_path", "data/other.sqlite3"),
        ("long_term_memory_uat_database_root", "data/uat/f-004"),
        ("long_term_memory_acceptance_ledger_path", "data/acceptance-ledgers/f-004.sqlite3"),
    ],
)
def test_f005_rejects_unapproved_paths_within_data_root(field: str, value: str) -> None:
    with pytest.raises(ValidationError, match="must remain"):
        Settings.model_validate({field: value})


def test_f005_rejects_symbolic_linked_data_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_is_symlink = Path.is_symlink

    def is_symlink(path: Path) -> bool:
        return path == config.PROJECT_ROOT / "data" or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", is_symlink)

    with pytest.raises(ValidationError, match="symbolic links or junctions"):
        Settings.model_validate({})


@pytest.mark.parametrize(
    "relative_path",
    [
        "data/cyber-town.sqlite3",
        "data/cyber-town.sqlite3-wal",
        "data/cyber-town.sqlite3-shm",
        "data/cyber-town.sqlite3-journal",
        "data/uat/f-005/synthetic-run/cyber-town.sqlite3",
        "data/uat/f-005/synthetic-run/cyber-town.sqlite3-wal",
        "data/uat/f-005/synthetic-run/cyber-town.sqlite3-shm",
        "data/uat/f-005/synthetic-run/cyber-town.sqlite3-journal",
        "data/uat/f-005/synthetic-run/trace.json",
        "data/acceptance-ledgers/f-005.sqlite3",
        "data/acceptance-ledgers/f-005.sqlite3-wal",
        "data/acceptance-ledgers/f-005.sqlite3-shm",
        "data/acceptance-ledgers/f-005.sqlite3-journal",
        "data/nested/example.db",
        "data/nested/example.sqlite",
    ],
)
def test_f005_runtime_database_and_acceptance_artifacts_are_ignored(relative_path: str) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    ignore_spec = GitIgnoreSpec.from_lines(
        (repository_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    )

    assert ignore_spec.match_file(relative_path)


def test_f005_ignore_policy_does_not_hide_reviewable_data_documentation() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    ignore_spec = GitIgnoreSpec.from_lines(
        (repository_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    )

    assert not ignore_spec.match_file("data/public-policy.md")


def test_f005_scope_environment_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONG_TERM_MEMORY_SCOPE_FIELDS", '["npc_id", "player_id"]')

    with pytest.raises(ValidationError, match="LONG_TERM_MEMORY_SCOPE_FIELDS must remain"):
        Settings.model_validate({})


def test_f005_path_environment_escape_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONG_TERM_MEMORY_DATABASE_PATH", "data/../sibling.sqlite3")

    with pytest.raises(ValidationError):
        Settings.model_validate({})

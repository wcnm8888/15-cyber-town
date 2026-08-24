from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

import cyber_town.contracts.export as exporter
from cyber_town.contracts.export import SCHEMA_DIRECTORY, render_schemas

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
CONVERSATION_ID = "22222222-2222-4222-8222-222222222222"
TRACE_ID = "33333333-3333-4333-8333-333333333333"


def schema_validator(filename: str) -> Draft202012Validator:
    schema = json.loads(render_schemas()[filename])
    return Draft202012Validator(schema, format_checker=FormatChecker())


def valid_schema_fixtures() -> dict[str, dict[str, Any]]:
    return {
        "dialogue-request-v1.schema.json": {
            "request_id": REQUEST_ID,
            "player_id": "player-1",
            "npc_id": "npc-1",
            "conversation_id": CONVERSATION_ID,
            "message": "你好",
        },
        "dialogue-response-v1.schema.json": {
            "request_id": REQUEST_ID,
            "trace_id": TRACE_ID,
            "npc_id": "npc-1",
            "conversation_id": CONVERSATION_ID,
            "reply": "Hello, traveler.",
            "status": "completed",
            "provider": "deepseek",
        },
        "api-error-v1.schema.json": {
            "trace_id": TRACE_ID,
            "code": "provider_timeout",
            "message": "Provider did not respond in time.",
            "retryable": True,
        },
    }


def test_exported_schemas_match_the_contract_source() -> None:
    rendered = render_schemas()

    assert set(rendered) == {
        "api-error-v1.schema.json",
        "dialogue-request-v1.schema.json",
        "dialogue-response-v1.schema.json",
    }
    for filename, expected in rendered.items():
        assert (SCHEMA_DIRECTORY / filename).read_text(encoding="utf-8") == expected


def test_request_schema_is_strict_and_keeps_message_budget() -> None:
    schema_path = Path(SCHEMA_DIRECTORY, "dialogue-request-v1.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["message"]["minLength"] == 1
    assert schema["properties"]["message"]["maxLength"] == 1_000
    assert schema["properties"]["message"]["pattern"] == r"\S"


def test_exported_schemas_are_valid_draft_2020_12() -> None:
    for content in render_schemas().values():
        Draft202012Validator.check_schema(json.loads(content))


def test_exported_schemas_accept_valid_fixtures() -> None:
    for filename, payload in valid_schema_fixtures().items():
        schema_validator(filename).validate(payload)


@pytest.mark.parametrize(
    ("filename", "field", "value"),
    [
        ("dialogue-request-v1.schema.json", "message", "   "),
        ("dialogue-request-v1.schema.json", "message", " " + ("x" * 1_000) + " "),
        ("dialogue-request-v1.schema.json", "request_id", "not-a-uuid"),
        (
            "dialogue-request-v1.schema.json",
            "request_id",
            "11111111111141118111111111111111",
        ),
        (
            "dialogue-request-v1.schema.json",
            "request_id",
            "{11111111-1111-4111-8111-111111111111}",
        ),
        (
            "dialogue-request-v1.schema.json",
            "request_id",
            "urn:uuid:11111111-1111-4111-8111-111111111111",
        ),
        ("dialogue-response-v1.schema.json", "reply", "\t\n"),
        ("dialogue-response-v1.schema.json", "reply", " " + ("x" * 4_000) + " "),
        ("dialogue-response-v1.schema.json", "status", "unknown"),
        ("api-error-v1.schema.json", "message", "   "),
        ("api-error-v1.schema.json", "message", " " + ("x" * 500) + " "),
        ("api-error-v1.schema.json", "retryable", "yes"),
    ],
)
def test_exported_schemas_reject_contract_boundary_failures(
    filename: str,
    field: str,
    value: object,
) -> None:
    payload = valid_schema_fixtures()[filename]
    payload[field] = value

    with pytest.raises(JsonSchemaValidationError):
        schema_validator(filename).validate(payload)


@pytest.mark.parametrize(
    "value",
    [
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
        "urn:uuid:11111111-1111-4111-8111-111111111111",
        REQUEST_ID + "\n",
        REQUEST_ID + "\r\n",
    ],
)
def test_uuid_shape_is_enforced_without_optional_format_assertions(value: str) -> None:
    payload = valid_schema_fixtures()["dialogue-request-v1.schema.json"]
    payload["request_id"] = value
    schema = json.loads(render_schemas()["dialogue-request-v1.schema.json"])

    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(payload)


def test_exported_schemas_reject_unknown_fields() -> None:
    payload = valid_schema_fixtures()["dialogue-request-v1.schema.json"]
    payload["unexpected"] = "not allowed"

    with pytest.raises(JsonSchemaValidationError):
        schema_validator("dialogue-request-v1.schema.json").validate(payload)


def test_schema_drift_reports_unexpected_derived_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for filename, content in render_schemas().items():
        (tmp_path / filename).write_text(content, encoding="utf-8", newline="\n")
    (tmp_path / "obsolete-v1.schema.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(exporter, "SCHEMA_DIRECTORY", tmp_path)

    assert exporter.schema_drift() == ["obsolete-v1.schema.json"]

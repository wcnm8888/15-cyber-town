from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from cyber_town.contracts.v1 import (
    ApiErrorCode,
    ApiErrorV1,
    DialogueRequestV1,
    DialogueResponseV1,
    DialogueStatus,
)

REQUEST_ID = "11111111-1111-4111-8111-111111111111"
CONVERSATION_ID = "22222222-2222-4222-8222-222222222222"
TRACE_ID = "33333333-3333-4333-8333-333333333333"


def validate_json(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    return model.model_validate_json(json.dumps(payload))


def valid_request_payload() -> dict[str, Any]:
    return {
        "request_id": REQUEST_ID,
        "player_id": "player-1",
        "npc_id": "npc-1",
        "conversation_id": CONVERSATION_ID,
        "message": "你好",
    }


def valid_response_payload() -> dict[str, Any]:
    return {
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "npc_id": "npc-1",
        "conversation_id": CONVERSATION_ID,
        "reply": "Hello, traveler.",
        "status": "completed",
        "provider": "deepseek",
    }


def test_valid_dialogue_request_is_trimmed_and_typed() -> None:
    payload = valid_request_payload()
    payload["message"] = " 你好 "

    request = DialogueRequestV1.model_validate_json(json.dumps(payload))

    assert request.message == "你好"
    assert str(request.request_id) == REQUEST_ID
    assert str(request.conversation_id) == CONVERSATION_ID


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message", "   "),
        ("message", " " + ("x" * 1_000) + " "),
        ("message", "x" * 1_001),
        ("player_id", ""),
        ("player_id", "p" * 65),
        ("npc_id", ""),
        ("npc_id", "n" * 65),
        ("request_id", "not-a-uuid"),
        ("conversation_id", "not-a-uuid"),
        ("request_id", "11111111111141118111111111111111"),
        ("request_id", "{11111111-1111-4111-8111-111111111111}"),
        ("request_id", "urn:uuid:11111111-1111-4111-8111-111111111111"),
    ],
)
def test_invalid_dialogue_request_fields_are_rejected(field: str, value: object) -> None:
    payload = valid_request_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        validate_json(DialogueRequestV1, payload)


def test_unknown_dialogue_request_field_is_rejected() -> None:
    payload = valid_request_payload()
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError, match="unexpected"):
        validate_json(DialogueRequestV1, payload)


def test_valid_dialogue_response_uses_stable_status_enum() -> None:
    response = DialogueResponseV1.model_validate_json(json.dumps(valid_response_payload()))

    assert response.status is DialogueStatus.COMPLETED
    assert response.provider == "deepseek"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "unknown"),
        ("reply", ""),
        ("reply", " " + ("x" * 4_000) + " "),
        ("reply", "x" * 4_001),
        ("provider", ""),
        ("provider", "p" * 65),
        ("trace_id", "not-a-uuid"),
    ],
)
def test_invalid_dialogue_response_fields_are_rejected(field: str, value: object) -> None:
    payload = valid_response_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        validate_json(DialogueResponseV1, payload)


def test_api_error_uses_stable_code_and_retryability() -> None:
    error = ApiErrorV1.model_validate_json(
        json.dumps(
            {
                "trace_id": TRACE_ID,
                "code": "provider_timeout",
                "message": "Provider did not respond in time.",
                "retryable": True,
            }
        )
    )

    assert error.code is ApiErrorCode.PROVIDER_TIMEOUT
    assert error.retryable is True


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(code="invented_error"),
        lambda payload: payload.update(message=""),
        lambda payload: payload.update(message=" " + ("x" * 500) + " "),
        lambda payload: payload.update(message="x" * 501),
        lambda payload: payload.update(retryable="yes"),
        lambda payload: payload.update(secret="must not be accepted"),
    ],
)
def test_invalid_api_error_fields_are_rejected(
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    payload: dict[str, Any] = {
        "trace_id": TRACE_ID,
        "code": "internal_error",
        "message": "Safe public error.",
        "retryable": False,
    }
    mutate(payload)

    with pytest.raises(ValidationError):
        validate_json(ApiErrorV1, payload)

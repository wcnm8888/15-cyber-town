"""Strict version-one dialogue contracts shared by future adapters."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    WithJsonSchema,
    field_validator,
)

CANONICAL_UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
CanonicalUUID = Annotated[
    UUID,
    WithJsonSchema(
        {
            "format": "uuid",
            "maxLength": 36,
            "minLength": 36,
            "pattern": CANONICAL_UUID_PATTERN,
            "type": "string",
        },
        mode="validation",
    ),
]


def _require_raw_string_length(value: object, maximum: int) -> object:
    if isinstance(value, str) and len(value) > maximum:
        raise ValueError(f"String must have at most {maximum} characters before trimming")
    return value


def _require_canonical_uuid(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        parsed = UUID(value)
    except ValueError:
        return value
    if value.lower() != str(parsed):
        raise ValueError("UUID must use canonical 8-4-4-4-12 representation")
    return value


ScopedIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"\S",
    ),
]
DialogueMessage = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=1_000,
        pattern=r"\S",
    ),
]
DialogueReply = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=4_000,
        pattern=r"\S",
    ),
]
ProviderIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"\S",
    ),
]
PublicErrorMessage = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=500,
        pattern=r"\S",
    ),
]


class StrictContract(BaseModel):
    """Reject coercion and unknown fields at external boundaries."""

    model_config = ConfigDict(extra="forbid", strict=True)


class DialogueStatus(StrEnum):
    """Stable outcome states visible to clients."""

    COMPLETED = "completed"
    DEGRADED = "degraded"


class ApiErrorCode(StrEnum):
    """Stable public errors; internal exception details are never exposed."""

    VALIDATION_ERROR = "validation_error"
    NPC_NOT_FOUND = "npc_not_found"
    CONFLICT = "conflict"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNSAFE_CONTENT = "unsafe_content"
    INTERNAL_ERROR = "internal_error"


class DialogueRequestV1(StrictContract):
    """A single idempotent player-to-NPC dialogue command."""

    request_id: CanonicalUUID
    player_id: ScopedIdentifier
    npc_id: ScopedIdentifier
    conversation_id: CanonicalUUID
    message: DialogueMessage

    @field_validator("request_id", "conversation_id", mode="before")
    @classmethod
    def require_canonical_uuids(cls, value: object) -> object:
        return _require_canonical_uuid(value)

    @field_validator("player_id", "npc_id", mode="before")
    @classmethod
    def require_raw_identifier_budget(cls, value: object) -> object:
        return _require_raw_string_length(value, 64)

    @field_validator("message", mode="before")
    @classmethod
    def require_raw_message_budget(cls, value: object) -> object:
        return _require_raw_string_length(value, 1_000)


class DialogueResponseV1(StrictContract):
    """A validated dialogue result without internal provider details."""

    request_id: CanonicalUUID
    trace_id: CanonicalUUID
    npc_id: ScopedIdentifier
    conversation_id: CanonicalUUID
    reply: DialogueReply
    status: DialogueStatus
    provider: ProviderIdentifier

    @field_validator("request_id", "trace_id", "conversation_id", mode="before")
    @classmethod
    def require_canonical_uuids(cls, value: object) -> object:
        return _require_canonical_uuid(value)

    @field_validator("npc_id", "provider", mode="before")
    @classmethod
    def require_raw_identifier_budget(cls, value: object) -> object:
        return _require_raw_string_length(value, 64)

    @field_validator("reply", mode="before")
    @classmethod
    def require_raw_reply_budget(cls, value: object) -> object:
        return _require_raw_string_length(value, 4_000)


class ApiErrorV1(StrictContract):
    """A safe public failure payload correlated by trace identifier."""

    trace_id: CanonicalUUID
    code: ApiErrorCode
    message: PublicErrorMessage
    retryable: bool

    @field_validator("trace_id", mode="before")
    @classmethod
    def require_canonical_uuid(cls, value: object) -> object:
        return _require_canonical_uuid(value)

    @field_validator("message", mode="before")
    @classmethod
    def require_raw_message_budget(cls, value: object) -> object:
        return _require_raw_string_length(value, 500)

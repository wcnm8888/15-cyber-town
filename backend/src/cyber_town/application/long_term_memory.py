"""Explicit, provider-free application commands for structured long-term facts."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID, uuid4

from cyber_town.application.dialogue import DialogueFailureKind, DialogueUseCaseError
from cyber_town.application.provider import ProviderLongTermFact
from cyber_town.contracts.v1 import (
    ApiErrorCode,
    DialogueRequestV1,
    DialogueResponseV1,
    DialogueStatus,
)
from cyber_town.domain.long_term_memory import (
    LongTermMemoryRecord,
    LongTermMemoryScope,
    MemoryStatus,
    MemoryType,
)
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import (
    LongTermMemoryConflictError,
    LongTermMemoryStorageError,
    SqliteLongTermMemoryRepository,
)

_DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60
_FACT_TYPES = {
    "game_alias": MemoryType.PROFILE,
    "preferred_language": MemoryType.PREFERENCE,
    "reply_style": MemoryType.PREFERENCE,
    "favorite_cyber_town_topic": MemoryType.PREFERENCE,
}
_FACT_ALIASES: dict[str, tuple[re.Pattern[str], ...]] = {
    "game_alias": (re.compile(r"\balias\b", re.IGNORECASE), re.compile("代号|别名")),
    "preferred_language": (
        re.compile(r"\blanguage\b", re.IGNORECASE),
        re.compile("语言"),
    ),
    "reply_style": (
        re.compile(r"\breply\s+style\b", re.IGNORECASE),
        re.compile("回答风格|回复风格"),
    ),
    "favorite_cyber_town_topic": (
        re.compile(r"\b(?:favorite\s+)?topic\b", re.IGNORECASE),
        re.compile("话题|主题"),
    ),
}


class MemoryCommandKind(StrEnum):
    """The two deterministic state transitions approved for structured facts."""

    REMEMBER = "remember"
    FORGET = "forget"


class MemoryCommandError(ValueError):
    """An explicit memory command does not match an approved template or fact."""


@dataclass(frozen=True, slots=True)
class MemoryCommand:
    """A strictly parsed memory instruction without an exposed fact body."""

    kind: MemoryCommandKind
    fact_key: str
    fact_value: str | None = field(repr=False)
    permanent: bool
    chinese: bool


def parse_memory_command(message: str) -> MemoryCommand | None:
    """Recognize only the frozen Chinese and English explicit command templates."""

    templates = (
        ("请永久记住\uff1a", MemoryCommandKind.REMEMBER, True, True),
        ("请记住\uff1a", MemoryCommandKind.REMEMBER, False, True),
        ("请忘记\uff1a", MemoryCommandKind.FORGET, False, True),
        ("Remember permanently:", MemoryCommandKind.REMEMBER, True, False),
        ("Remember:", MemoryCommandKind.REMEMBER, False, False),
        ("Forget:", MemoryCommandKind.FORGET, False, False),
    )
    for prefix, kind, permanent, chinese in templates:
        if not message.startswith(prefix):
            continue

        payload = message.removeprefix(prefix).strip()
        if kind is MemoryCommandKind.FORGET:
            if payload not in _FACT_TYPES or "=" in payload:
                raise MemoryCommandError("The requested memory fact is not approved")
            return MemoryCommand(kind, payload, None, permanent, chinese)

        fact_key, separator, fact_value = payload.partition("=")
        if separator != "=" or fact_key not in _FACT_TYPES or not fact_value:
            raise MemoryCommandError("The memory command requires an approved fact and value")
        return MemoryCommand(kind, fact_key, fact_value, permanent, chinese)
    return None


class LongTermMemoryService:
    """Execute explicit local memory writes without invoking a model provider."""

    def __init__(
        self,
        *,
        repository: SqliteLongTermMemoryRepository,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(repository, SqliteLongTermMemoryRepository):
            raise TypeError("Long-term memory requires an approved SQLite repository")
        self._repository = repository
        self._clock = clock or (lambda: int(time.time()))

    def operation_fingerprint(self, request_id: UUID) -> str | None:
        """Expose only the approved durable operation identity across service restarts."""

        return self._repository.operation_fingerprint(request_id)

    def superseded_fact_value(self, request: DialogueRequestV1) -> str | None:
        """Identify an active value that this approved command will replace or forget."""

        command = parse_memory_command(request.message)
        if command is None:
            return None

        scope = LongTermMemoryScope(request.player_id, request.npc_id)
        records = self._repository.active_for_scope(scope, now=self._clock())
        previous = next((record for record in records if record.fact_key == command.fact_key), None)
        if previous is None or previous.fact_value == command.fact_value:
            return None
        return previous.fact_value

    def execute(
        self,
        request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1 | None:
        command = parse_memory_command(request.message)
        if command is None:
            return None

        now = self._clock()
        if type(now) is not int or now <= 0:
            raise ValueError("Long-term memory clock must return a positive Unix second")

        try:
            record = LongTermMemoryRecord(
                memory_id=uuid4(),
                scope=LongTermMemoryScope(request.player_id, request.npc_id),
                memory_type=_FACT_TYPES[command.fact_key],
                fact_key=command.fact_key,
                fact_value=command.fact_value,
                source_conversation_id=request.conversation_id,
                source_request_id=request.request_id,
                source_trace_id=trace_id,
                importance=3,
                confidence=1_000,
                created_at=now,
                updated_at=now,
                expires_at=None
                if command.permanent or command.kind is MemoryCommandKind.FORGET
                else now + _DEFAULT_TTL_SECONDS,
                version=1,
                status=MemoryStatus.FORGOTTEN
                if command.kind is MemoryCommandKind.FORGET
                else MemoryStatus.ACTIVE,
            )
        except (TypeError, ValueError) as error:
            raise MemoryCommandError(
                "The memory fact does not satisfy its approved format"
            ) from error

        payload = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        fingerprint = hashlib.sha256(payload).hexdigest()

        try:
            if command.kind is MemoryCommandKind.REMEMBER:
                self._repository.remember(record, request_fingerprint=fingerprint)
            else:
                self._repository.forget(record, request_fingerprint=fingerprint)
        except LongTermMemoryConflictError as error:
            raise DialogueUseCaseError(
                kind=DialogueFailureKind.CONFLICT,
                code=ApiErrorCode.CONFLICT,
                public_message="The request conflicts with an existing request.",
                retryable=False,
            ) from error
        except LongTermMemoryStorageError as error:
            raise DialogueUseCaseError(
                kind=DialogueFailureKind.PROVIDER_UNAVAILABLE,
                code=ApiErrorCode.PROVIDER_UNAVAILABLE,
                public_message="The dialogue service is temporarily unavailable.",
                retryable=True,
            ) from error

        return DialogueResponseV1(
            request_id=request.request_id,
            trace_id=trace_id,
            npc_id=request.npc_id,
            conversation_id=request.conversation_id,
            reply=self._reply(command),
            status=DialogueStatus.COMPLETED,
            provider="local-memory",
        )

    @staticmethod
    def _reply(command: MemoryCommand) -> str:
        if command.chinese:
            if command.kind is MemoryCommandKind.FORGET:
                return f"已忘记\uff1a{command.fact_key}。"
            action = "已永久记住" if command.permanent else "已记住"
            return f"{action}\uff1a{command.fact_key}。"

        if command.kind is MemoryCommandKind.FORGET:
            return f"Forgot: {command.fact_key}."
        action = "Remembered permanently" if command.permanent else "Remembered"
        return f"{action}: {command.fact_key}."


class LongTermMemoryRetriever:
    """Retrieve only relevant, scoped and explicitly approved structured facts."""

    def __init__(
        self,
        *,
        repository: SqliteLongTermMemoryRepository,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if not isinstance(repository, SqliteLongTermMemoryRepository):
            raise TypeError("Long-term memory requires an approved SQLite repository")
        self._repository = repository
        self._clock = clock or (lambda: int(time.time()))

    def retrieve(
        self,
        scope: LongTermMemoryScope,
        query: str,
    ) -> tuple[ProviderLongTermFact, ...]:
        """Apply exact-key/alias rank before deterministic approved metadata ties."""

        if not isinstance(scope, LongTermMemoryScope):
            raise TypeError("Long-term memory requires a validated player/NPC scope")
        if not isinstance(query, str):
            raise TypeError("Long-term memory retrieval query must be a string")

        matched_keys = self._matched_fact_keys(query)
        if not matched_keys:
            return ()

        records = self._repository.active_for_scope(scope, now=self._clock())
        relevant = [record for record in records if record.fact_key in matched_keys]
        relevant.sort(
            key=lambda record: (
                matched_keys[record.fact_key],
                -record.importance,
                -record.confidence,
                -record.updated_at,
                str(record.memory_id),
            )
        )
        return tuple(
            ProviderLongTermFact(record.fact_key, record.fact_value)
            for record in relevant[:4]
            if record.fact_value is not None
        )

    @classmethod
    def is_recall_request(cls, query: str) -> bool:
        """Recognize only frozen exact fact keys and their approved query aliases."""

        if not isinstance(query, str):
            raise TypeError("Long-term memory retrieval query must be a string")
        return bool(cls._matched_fact_keys(query))

    def is_suppressed_recall(self, scope: LongTermMemoryScope, query: str) -> bool:
        """Prevent forgotten, expired or untrusted facts leaking from old short-term turns."""

        if not isinstance(scope, LongTermMemoryScope):
            raise TypeError("Long-term memory requires a validated player/NPC scope")
        if not isinstance(query, str):
            raise TypeError("Long-term memory retrieval query must be a string")
        matched_keys = self._matched_fact_keys(query)
        if not matched_keys:
            return False
        now = self._clock()
        return any(
            record.fact_key in matched_keys
            and (
                record.status is not MemoryStatus.ACTIVE
                or (record.expires_at is not None and record.expires_at <= now)
                or record.confidence < 1
            )
            for record in self._repository.list_scope(scope)
        )

    @staticmethod
    def _matched_fact_keys(query: str) -> dict[str, int]:
        matched: dict[str, int] = {}
        for fact_key, aliases in _FACT_ALIASES.items():
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(fact_key)}(?![A-Za-z0-9_])", query):
                matched[fact_key] = 0
            elif any(pattern.search(query) is not None for pattern in aliases):
                matched[fact_key] = 1
        return matched

"""Single-turn, provider-neutral dialogue application service."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from cyber_town.application.provider import (
    ProviderCompletion,
    ProviderInvalidResponseError,
    ProviderProtocol,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderUsage,
)
from cyber_town.contracts.v1 import (
    ApiErrorCode,
    DialogueRequestV1,
    DialogueResponseV1,
    DialogueStatus,
)
from cyber_town.domain.persona import PersonaDefinition

LOGGER = logging.getLogger("cyber_town.dialogue")
SAFE_FALLBACK_REPLY = "Nia pauses, keeping the conversation within safe boundaries."


class DialogueFailureKind(StrEnum):
    """Internal failure categories kept separate from public v1 error codes."""

    NPC_NOT_FOUND = "npc_not_found"
    CONFLICT = "conflict"
    UNSAFE_CONTENT = "unsafe_content"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_INVALID_RESPONSE = "provider_invalid_response"
    INTERNAL_ERROR = "internal_error"


class DialogueUseCaseError(Exception):
    """A safe application error ready for HTTP translation in a later Step."""

    def __init__(
        self,
        *,
        kind: DialogueFailureKind,
        code: ApiErrorCode,
        public_message: str,
        retryable: bool,
    ) -> None:
        super().__init__(public_message)
        self.kind = kind
        self.code = code
        self.public_message = public_message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class DialogueExecutionConfig:
    """Validated execution values supplied by the future composition root."""

    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float
    max_concurrency: int
    idempotency_ttl_seconds: float
    idempotency_max_entries: int

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("Dialogue model cannot be blank")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Dialogue temperature must be between 0 and 2")
        if not 1 <= self.max_tokens <= 1_024:
            raise ValueError("Dialogue max tokens must be between 1 and 1024")
        if not 0.1 <= self.timeout_seconds <= 60.0:
            raise ValueError("Dialogue timeout must be between 0.1 and 60 seconds")
        if not 1 <= self.max_concurrency <= 8:
            raise ValueError("Dialogue concurrency must be between 1 and 8")
        if not 1.0 <= self.idempotency_ttl_seconds <= 3_600.0:
            raise ValueError("Dialogue idempotency TTL must be between 1 and 3600 seconds")
        if not 1 <= self.idempotency_max_entries <= 4_096:
            raise ValueError("Dialogue idempotency capacity must be between 1 and 4096")


@dataclass(frozen=True, slots=True)
class _DialogueResult:
    reply: str
    status: DialogueStatus
    provider: str
    provider_model: str
    persona_version: str
    usage: ProviderUsage
    latency_ms: int


@dataclass(slots=True)
class _IdempotencyEntry:
    fingerprint: str
    task: asyncio.Task[_DialogueResult] | None
    result: _DialogueResult | None
    expires_at: float


class DialogueService:
    """Execute one validated player-to-NPC command without persistence."""

    def __init__(
        self,
        *,
        personas: Mapping[str, PersonaDefinition],
        provider: ProviderProtocol,
        config: DialogueExecutionConfig,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if any(key != persona.npc_id for key, persona in personas.items()):
            raise ValueError("Persona mapping keys must match persona npc_id values")
        self._personas = dict(personas)
        self._provider = provider
        self._config = config
        self._clock = clock or time.monotonic
        self._provider_slots = asyncio.Semaphore(config.max_concurrency)
        self._idempotency_lock = asyncio.Lock()
        self._idempotency: OrderedDict[UUID, _IdempotencyEntry] = OrderedDict()

    async def execute(
        self,
        request: DialogueRequestV1,
        *,
        trace_id: UUID,
    ) -> DialogueResponseV1:
        persona = self._personas.get(request.npc_id)
        if persona is None:
            error = DialogueUseCaseError(
                kind=DialogueFailureKind.NPC_NOT_FOUND,
                code=ApiErrorCode.NPC_NOT_FOUND,
                public_message="NPC is not available.",
                retryable=False,
            )
            self._log_failure(request, trace_id, error, persona_version=None)
            raise error

        try:
            result, from_cache = await self._execute_idempotent(request, persona)
        except DialogueUseCaseError as error:
            self._log_failure(request, trace_id, error, persona_version=persona.version)
            raise

        response = DialogueResponseV1(
            request_id=request.request_id,
            trace_id=trace_id,
            npc_id=request.npc_id,
            conversation_id=request.conversation_id,
            reply=result.reply,
            status=result.status,
            provider=result.provider,
        )
        self._log_success(request, trace_id, result, from_cache=from_cache)
        return response

    async def _execute_idempotent(
        self,
        request: DialogueRequestV1,
        persona: PersonaDefinition,
    ) -> tuple[_DialogueResult, bool]:
        fingerprint = self._fingerprint(request)
        now = self._clock()

        async with self._idempotency_lock:
            self._purge_expired(now)
            entry = self._idempotency.get(request.request_id)
            from_cache = entry is not None
            if entry is not None:
                if entry.fingerprint != fingerprint:
                    raise DialogueUseCaseError(
                        kind=DialogueFailureKind.CONFLICT,
                        code=ApiErrorCode.CONFLICT,
                        public_message="The request conflicts with an existing request.",
                        retryable=False,
                    )
                self._idempotency.move_to_end(request.request_id)
                if entry.result is not None:
                    return entry.result, True
                if entry.task is None:
                    raise RuntimeError("Invalid in-memory idempotency entry")
                task = entry.task
            else:
                self._make_capacity()
                task = asyncio.create_task(self._generate(request, persona))
                entry = _IdempotencyEntry(
                    fingerprint=fingerprint,
                    task=task,
                    result=None,
                    expires_at=now + self._config.idempotency_ttl_seconds,
                )
                self._idempotency[request.request_id] = entry

        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._remove_failed_entry(request.request_id, task)
            raise

        async with self._idempotency_lock:
            current = self._idempotency.get(request.request_id)
            if current is not None and current.task is task:
                current.task = None
                current.result = result
                current.expires_at = self._clock() + self._config.idempotency_ttl_seconds
                self._idempotency.move_to_end(request.request_id)

        return result, from_cache

    async def _remove_failed_entry(
        self,
        request_id: UUID,
        task: asyncio.Task[_DialogueResult],
    ) -> None:
        async with self._idempotency_lock:
            current = self._idempotency.get(request_id)
            if current is not None and current.task is task:
                del self._idempotency[request_id]

    def _purge_expired(self, now: float) -> None:
        for request_id, entry in list(self._idempotency.items()):
            if entry.task is None or not entry.task.done():
                continue
            try:
                result = entry.task.result()
            except (asyncio.CancelledError, Exception):
                del self._idempotency[request_id]
                continue
            entry.task = None
            entry.result = result
            entry.expires_at = now + self._config.idempotency_ttl_seconds

        expired = [
            request_id
            for request_id, entry in self._idempotency.items()
            if entry.result is not None and entry.expires_at <= now
        ]
        for request_id in expired:
            del self._idempotency[request_id]

    def _make_capacity(self) -> None:
        while len(self._idempotency) >= self._config.idempotency_max_entries:
            completed_id = next(
                (
                    request_id
                    for request_id, entry in self._idempotency.items()
                    if entry.result is not None
                ),
                None,
            )
            if completed_id is None:
                raise DialogueUseCaseError(
                    kind=DialogueFailureKind.PROVIDER_UNAVAILABLE,
                    code=ApiErrorCode.PROVIDER_UNAVAILABLE,
                    public_message="The dialogue service is temporarily at capacity.",
                    retryable=True,
                )
            del self._idempotency[completed_id]

    async def _generate(
        self,
        request: DialogueRequestV1,
        persona: PersonaDefinition,
    ) -> _DialogueResult:
        provider_request = ProviderRequest(
            system_prompt=persona.system_prompt,
            user_message=request.message,
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            timeout_seconds=self._config.timeout_seconds,
            thinking_enabled=False,
            stream=False,
        )
        started = self._clock()

        try:
            async with self._provider_slots:
                async with asyncio.timeout(self._config.timeout_seconds):
                    completion = await self._provider.complete(provider_request)
        except (TimeoutError, ProviderTimeoutError):
            raise DialogueUseCaseError(
                kind=DialogueFailureKind.PROVIDER_TIMEOUT,
                code=ApiErrorCode.PROVIDER_TIMEOUT,
                public_message="The dialogue provider timed out.",
                retryable=True,
            ) from None
        except ProviderInvalidResponseError:
            raise self._invalid_provider_response() from None
        except ProviderUnavailableError:
            raise DialogueUseCaseError(
                kind=DialogueFailureKind.PROVIDER_UNAVAILABLE,
                code=ApiErrorCode.PROVIDER_UNAVAILABLE,
                public_message="The dialogue provider is unavailable.",
                retryable=True,
            ) from None
        except Exception:
            raise DialogueUseCaseError(
                kind=DialogueFailureKind.INTERNAL_ERROR,
                code=ApiErrorCode.INTERNAL_ERROR,
                public_message="The dialogue request could not be completed.",
                retryable=False,
            ) from None

        latency_ms = max(0, round((self._clock() - started) * 1_000))
        return self._validate_completion(completion, persona, latency_ms=latency_ms)

    @staticmethod
    def _validate_completion(
        completion: ProviderCompletion,
        persona: PersonaDefinition,
        *,
        latency_ms: int,
    ) -> _DialogueResult:
        invalid = (
            completion.choice_count != 1
            or completion.tool_calls_present
            or completion.reasoning_content_present
            or not isinstance(completion.finish_reason, str)
            or not isinstance(completion.provider, str)
            or not completion.provider.strip()
            or len(completion.provider) > 64
            or not isinstance(completion.model, str)
            or not completion.model.strip()
            or len(completion.model) > 64
        )
        if invalid:
            raise DialogueService._invalid_provider_response()

        if completion.finish_reason == "content_filter":
            return _DialogueResult(
                reply=SAFE_FALLBACK_REPLY,
                status=DialogueStatus.DEGRADED,
                provider="local-fallback",
                provider_model=completion.model,
                persona_version=persona.version,
                usage=completion.usage,
                latency_ms=latency_ms,
            )

        if completion.finish_reason != "stop" or not isinstance(completion.content, str):
            raise DialogueService._invalid_provider_response()

        if len(completion.content) > 4_000:
            raise DialogueService._invalid_provider_response()
        reply = completion.content.strip()
        if not reply:
            raise DialogueService._invalid_provider_response()

        return _DialogueResult(
            reply=reply,
            status=DialogueStatus.COMPLETED,
            provider=completion.provider,
            provider_model=completion.model,
            persona_version=persona.version,
            usage=completion.usage,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _invalid_provider_response() -> DialogueUseCaseError:
        return DialogueUseCaseError(
            kind=DialogueFailureKind.PROVIDER_INVALID_RESPONSE,
            code=ApiErrorCode.PROVIDER_UNAVAILABLE,
            public_message="The dialogue provider returned an invalid response.",
            retryable=True,
        )

    @staticmethod
    def _fingerprint(request: DialogueRequestV1) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _log_success(
        request: DialogueRequestV1,
        trace_id: UUID,
        result: _DialogueResult,
        *,
        from_cache: bool,
    ) -> None:
        audit = {
            "event": "dialogue_completed",
            "trace_id": str(trace_id),
            "request_id": str(request.request_id),
            "npc_id": request.npc_id,
            "persona_version": result.persona_version,
            "provider": result.provider,
            "model": result.provider_model,
            "outcome": result.status.value,
            "retryable": False,
            "from_cache": from_cache,
            "latency_ms": result.latency_ms,
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "total_tokens": result.usage.total_tokens,
            "input_chars": len(request.message),
            "output_chars": len(result.reply),
        }
        LOGGER.info("dialogue_completed", extra={"dialogue_audit": audit})

    @staticmethod
    def _log_failure(
        request: DialogueRequestV1,
        trace_id: UUID,
        error: DialogueUseCaseError,
        *,
        persona_version: str | None,
    ) -> None:
        audit = {
            "event": "dialogue_failed",
            "trace_id": str(trace_id),
            "request_id": str(request.request_id),
            "npc_id": request.npc_id,
            "persona_version": persona_version,
            "outcome": error.kind.value,
            "error_code": error.code.value,
            "retryable": error.retryable,
            "input_chars": len(request.message),
        }
        LOGGER.info("dialogue_failed", extra={"dialogue_audit": audit})

"""Strict metadata-only observability values with no runtime instrumentation."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from types import MappingProxyType
from typing import Protocol, runtime_checkable
from uuid import UUID

OBSERVABILITY_SCHEMA_VERSION = 1
_MAX_SCOPE_IDENTIFIER_LENGTH = 64
_MIN_HMAC_KEY_BYTES = 16
_TAG_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_PERSONA_VERSION_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LOGGER = logging.getLogger("cyber_town.observability")


class TraceStage(StrEnum):
    HTTP_RECEIVED = "http_received"
    REQUEST_VALIDATION = "request_validation"
    PERSONA_RESOLUTION = "persona_resolution"
    IDEMPOTENCY_RESOLUTION = "idempotency_resolution"
    SCOPE_LOCK = "scope_lock"
    SHORT_TERM_SELECTION = "short_term_selection"
    LONG_TERM_RETRIEVAL = "long_term_retrieval"
    CONTEXT_BUDGET_SELECTION = "context_budget_selection"
    PROVIDER_QUEUE = "provider_queue"
    PROVIDER_COMPLETION = "provider_completion"
    RELATIONSHIP_EVALUATION = "relationship_evaluation"
    STATE_COMMIT = "state_commit"
    RESPONSE_MAPPING = "response_mapping"
    TERMINAL = "terminal"


_TRACE_STAGE_SEQUENCE = {stage: index for index, stage in enumerate(TraceStage, start=1)}


class StageOutcome(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NOT_REACHED = "not_reached"


class TerminalOutcome(StrEnum):
    COMPLETED = "completed"
    DEGRADED = "degraded"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"
    REPLAYED = "replayed"
    CONFLICT = "conflict"
    ABANDONED_AFTER_RESTART = "abandoned_after_restart"


class RecordStatus(StrEnum):
    OPEN = "open"
    COMPLETE = "complete"
    PARTIAL = "partial"


class AttemptKind(StrEnum):
    INITIAL = "initial"
    RETRY = "retry"
    CONCURRENT_WAITER = "concurrent_waiter"
    CACHE_REPLAY = "cache_replay"
    VALIDATION_FAILURE = "validation_failure"


class IdempotencyOutcome(StrEnum):
    NOT_REACHED = "not_reached"
    NEW = "new"
    INFLIGHT_SHARED = "inflight_shared"
    CACHE_REPLAY = "cache_replay"
    CONFLICT = "conflict"


class ShortTermOutcome(StrEnum):
    NOT_REACHED = "not_reached"
    EMPTY = "empty"
    SELECTED = "selected"
    COMMITTED = "committed"
    ABORTED = "aborted"
    FAILED = "failed"


class LongTermOutcome(StrEnum):
    NOT_REACHED = "not_reached"
    NOT_CONFIGURED = "not_configured"
    EMPTY = "empty"
    RETRIEVED = "retrieved"
    COMMAND_COMPLETED = "command_completed"
    FAILED = "failed"


class RelationshipOutcome(StrEnum):
    NOT_REACHED = "not_reached"
    NOT_CONFIGURED = "not_configured"
    APPLIED = "applied"
    INERT = "inert"
    FAILED = "failed"


class ProviderKind(StrEnum):
    FAKE = "fake"
    DEEPSEEK = "deepseek"
    LOCAL_FALLBACK = "local-fallback"
    LOCAL_MEMORY = "local-memory"
    DISABLED = "disabled"
    UNKNOWN = "unknown"


class TraceReasonCode(StrEnum):
    NONE = "none"
    COMPLETED = "completed"
    DEGRADED_CONTENT_FILTER = "degraded_content_filter"
    DEGRADED_NO_HISTORY = "degraded_no_history"
    LOCAL_MEMORY_COMMAND = "local_memory_command"
    CACHE_REPLAY = "cache_replay"
    SHARED_EXECUTION = "shared_execution"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"
    RESTART_RECOVERY = "restart_recovery"
    NOT_REACHED = "not_reached"


class TraceErrorCode(StrEnum):
    NONE = "none"
    VALIDATION_ERROR = "validation_error"
    NPC_NOT_FOUND = "npc_not_found"
    CONFLICT = "conflict"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_INVALID_RESPONSE = "provider_invalid_response"
    UNSAFE_CONTENT = "unsafe_content"
    INTERNAL_ERROR = "internal_error"
    OBSERVABILITY_UNAVAILABLE = "observability_unavailable"


class ScopeDimension(StrEnum):
    PLAYER = "player"
    NPC = "npc"
    CONVERSATION = "conversation"


def derive_scope_tag(*, key: bytes, dimension: ScopeDimension, identifier: str) -> str:
    """Derive one stable tag without retaining or echoing the source identifier or key."""

    if not isinstance(key, bytes):
        raise TypeError("Scope tag key type is invalid")
    if len(key) < _MIN_HMAC_KEY_BYTES:
        raise ValueError("Scope tag key is invalid")
    if not isinstance(dimension, ScopeDimension):
        raise TypeError("Scope tag dimension is invalid")
    if not isinstance(identifier, str):
        raise TypeError("Scope tag identifier type is invalid")
    if (
        not identifier
        or identifier != identifier.strip()
        or len(identifier) > _MAX_SCOPE_IDENTIFIER_LENGTH
    ):
        raise ValueError("Scope tag identifier is invalid")

    domain = (f"cyber-town:f008:scope:v{OBSERVABILITY_SCHEMA_VERSION}:{dimension.value}\0").encode()
    return hmac.new(key, domain + identifier.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True, slots=True)
class ScopeTags:
    player_scope_tag: str
    npc_scope_tag: str
    conversation_scope_tag: str

    def __post_init__(self) -> None:
        for value in (
            self.player_scope_tag,
            self.npc_scope_tag,
            self.conversation_scope_tag,
        ):
            if not isinstance(value, str):
                raise TypeError("Scope tag type is invalid")
            if _TAG_PATTERN.fullmatch(value) is None:
                raise ValueError("Scope tag is invalid")

    @classmethod
    def from_identifiers(
        cls,
        *,
        key: bytes,
        player_id: str,
        npc_id: str,
        conversation_id: str,
    ) -> ScopeTags:
        return cls(
            player_scope_tag=derive_scope_tag(
                key=key,
                dimension=ScopeDimension.PLAYER,
                identifier=player_id,
            ),
            npc_scope_tag=derive_scope_tag(
                key=key,
                dimension=ScopeDimension.NPC,
                identifier=npc_id,
            ),
            conversation_scope_tag=derive_scope_tag(
                key=key,
                dimension=ScopeDimension.CONVERSATION,
                identifier=conversation_id,
            ),
        )

    def as_dict(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                "player_scope_tag": self.player_scope_tag,
                "npc_scope_tag": self.npc_scope_tag,
                "conversation_scope_tag": self.conversation_scope_tag,
            }
        )


def _require_enum(value: object, enum_type: type[StrEnum], field: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"Observability {field} type is invalid")


def _require_uuid(value: object, field: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, UUID):
        raise TypeError(f"Observability {field} type is invalid")


def _require_nonnegative_int(value: object, field: str) -> None:
    if type(value) is not int:
        raise TypeError(f"Observability {field} type is invalid")
    if value < 0:
        raise ValueError(f"Observability {field} is invalid")


def _require_utc(value: object, field: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, datetime):
        raise TypeError(f"Observability {field} type is invalid")
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise ValueError(f"Observability {field} must use UTC")


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class TraceMetadata:
    schema_version: int
    trace_id: UUID
    request_id: UUID | None
    execution_id: UUID | None
    attempt_kind: AttemptKind
    scope_tags: ScopeTags | None
    persona_version: str | None
    provider_kind: ProviderKind
    record_status: RecordStatus
    terminal_outcome: TerminalOutcome | None
    error_code: TraceErrorCode
    reason_code: TraceReasonCode
    idempotency_outcome: IdempotencyOutcome
    short_term_outcome: ShortTermOutcome
    long_term_outcome: LongTermOutcome
    relationship_outcome: RelationshipOutcome
    retryable: bool
    from_cache: bool
    provider_dispatch_count: int
    started_at_utc: datetime
    finished_at_utc: datetime | None
    total_latency_ms: int
    provider_wait_ms: int
    provider_latency_ms: int
    context_budget_units: int
    selected_short_term_turns: int
    selected_long_term_facts: int
    input_chars: int
    output_chars: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_micro_usd: int

    def __post_init__(self) -> None:
        self._validate_types_and_ranges()
        self._validate_lifecycle()
        self._validate_attempt()

    def _validate_types_and_ranges(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != OBSERVABILITY_SCHEMA_VERSION
        ):
            raise ValueError("Observability schema version is invalid")
        _require_uuid(self.trace_id, "trace identifier")
        _require_uuid(self.request_id, "request identifier", optional=True)
        _require_uuid(self.execution_id, "execution identifier", optional=True)
        for enum_value, enum_type, field in (
            (self.attempt_kind, AttemptKind, "attempt kind"),
            (self.provider_kind, ProviderKind, "provider kind"),
            (self.record_status, RecordStatus, "record status"),
            (self.error_code, TraceErrorCode, "error code"),
            (self.reason_code, TraceReasonCode, "reason code"),
            (self.idempotency_outcome, IdempotencyOutcome, "idempotency outcome"),
            (self.short_term_outcome, ShortTermOutcome, "short-term outcome"),
            (self.long_term_outcome, LongTermOutcome, "long-term outcome"),
            (self.relationship_outcome, RelationshipOutcome, "relationship outcome"),
        ):
            _require_enum(enum_value, enum_type, field)
        if self.terminal_outcome is not None:
            _require_enum(self.terminal_outcome, TerminalOutcome, "terminal outcome")
        if self.scope_tags is not None and not isinstance(self.scope_tags, ScopeTags):
            raise TypeError("Observability scope tag type is invalid")
        if self.persona_version is not None:
            if not isinstance(self.persona_version, str):
                raise TypeError("Observability persona version type is invalid")
            if (
                len(self.persona_version) > 64
                or _PERSONA_VERSION_PATTERN.fullmatch(self.persona_version) is None
            ):
                raise ValueError("Observability persona version is invalid")
        if type(self.retryable) is not bool or type(self.from_cache) is not bool:
            raise TypeError("Observability boolean metadata type is invalid")
        for numeric_value, field in (
            (self.provider_dispatch_count, "provider dispatch count"),
            (self.total_latency_ms, "total latency"),
            (self.provider_wait_ms, "provider wait"),
            (self.provider_latency_ms, "provider latency"),
            (self.context_budget_units, "context budget"),
            (self.selected_short_term_turns, "short-term turn count"),
            (self.selected_long_term_facts, "long-term fact count"),
            (self.input_chars, "input character count"),
            (self.output_chars, "output character count"),
            (self.prompt_tokens, "prompt token count"),
            (self.completion_tokens, "completion token count"),
            (self.total_tokens, "total token count"),
            (self.cost_micro_usd, "cost"),
        ):
            _require_nonnegative_int(numeric_value, field)
        if self.provider_dispatch_count > 1:
            raise ValueError("Observability provider dispatch count is invalid")
        if self.cost_micro_usd != 0:
            raise ValueError("Observability cost is invalid")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Token totals are inconsistent")
        _require_utc(self.started_at_utc, "start timestamp")
        _require_utc(self.finished_at_utc, "finish timestamp", optional=True)

    def _validate_lifecycle(self) -> None:
        if self.record_status is RecordStatus.OPEN:
            if self.terminal_outcome is not None:
                raise ValueError("Open trace cannot have a terminal outcome")
            if self.finished_at_utc is not None:
                raise ValueError("Open trace cannot have a finish timestamp")
        else:
            if self.terminal_outcome is None:
                raise ValueError("Completed trace requires a terminal outcome")
            if self.finished_at_utc is None:
                raise ValueError("Completed trace requires a finish timestamp")
        if self.finished_at_utc is not None and self.finished_at_utc < self.started_at_utc:
            raise ValueError("Trace timestamps are inconsistent")

    def _validate_attempt(self) -> None:
        if self.attempt_kind is AttemptKind.VALIDATION_FAILURE:
            trusted_metadata = (
                self.request_id,
                self.execution_id,
                self.scope_tags,
                self.persona_version,
            )
            if any(value is not None for value in trusted_metadata):
                raise ValueError("Validation failure cannot carry trusted metadata")
            if (
                self.idempotency_outcome is not IdempotencyOutcome.NOT_REACHED
                or self.short_term_outcome is not ShortTermOutcome.NOT_REACHED
                or self.long_term_outcome is not LongTermOutcome.NOT_REACHED
                or self.relationship_outcome is not RelationshipOutcome.NOT_REACHED
                or self.provider_dispatch_count != 0
            ):
                raise ValueError("Validation failure component metadata is inconsistent")
            return
        if self.request_id is None or self.scope_tags is None:
            raise ValueError("Validated trace requires request and scope metadata")
        if self.attempt_kind is AttemptKind.CACHE_REPLAY:
            if (
                self.execution_id is not None
                or self.idempotency_outcome is not IdempotencyOutcome.CACHE_REPLAY
                or not self.from_cache
                or self.provider_dispatch_count != 0
                or self.terminal_outcome is not TerminalOutcome.REPLAYED
            ):
                raise ValueError("Cache replay invariants are inconsistent")
        elif self.from_cache:
            raise ValueError("Only cache replay may be marked from cache")
        if self.attempt_kind is AttemptKind.CONCURRENT_WAITER and (
            self.execution_id is None
            or self.idempotency_outcome is not IdempotencyOutcome.INFLIGHT_SHARED
            or self.provider_dispatch_count != 0
        ):
            raise ValueError("Shared execution invariants are inconsistent")
        if self.provider_dispatch_count == 1 and self.execution_id is None:
            raise ValueError("Provider dispatch requires an execution identifier")

    def as_dict(self) -> dict[str, object]:
        tags: Mapping[str, str | None]
        if self.scope_tags is None:
            tags = {
                "player_scope_tag": None,
                "npc_scope_tag": None,
                "conversation_scope_tag": None,
            }
        else:
            tags = self.scope_tags.as_dict()
        return {
            "schema_version": self.schema_version,
            "trace_id": str(self.trace_id),
            "request_id": None if self.request_id is None else str(self.request_id),
            "execution_id": None if self.execution_id is None else str(self.execution_id),
            "attempt_kind": self.attempt_kind.value,
            **tags,
            "persona_version": self.persona_version,
            "provider_kind": self.provider_kind.value,
            "record_status": self.record_status.value,
            "terminal_outcome": (
                None if self.terminal_outcome is None else self.terminal_outcome.value
            ),
            "error_code": self.error_code.value,
            "reason_code": self.reason_code.value,
            "idempotency_outcome": self.idempotency_outcome.value,
            "short_term_outcome": self.short_term_outcome.value,
            "long_term_outcome": self.long_term_outcome.value,
            "relationship_outcome": self.relationship_outcome.value,
            "retryable": self.retryable,
            "from_cache": self.from_cache,
            "provider_dispatch_count": self.provider_dispatch_count,
            "started_at_utc": _utc_text(self.started_at_utc),
            "finished_at_utc": _utc_text(self.finished_at_utc),
            "total_latency_ms": self.total_latency_ms,
            "provider_wait_ms": self.provider_wait_ms,
            "provider_latency_ms": self.provider_latency_ms,
            "context_budget_units": self.context_budget_units,
            "selected_short_term_turns": self.selected_short_term_turns,
            "selected_long_term_facts": self.selected_long_term_facts,
            "input_chars": self.input_chars,
            "output_chars": self.output_chars,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_micro_usd": self.cost_micro_usd,
        }


@dataclass(frozen=True, slots=True)
class TraceStageMetadata:
    schema_version: int
    trace_id: UUID
    stage: TraceStage
    sequence: int
    outcome: StageOutcome
    reason_code: TraceReasonCode
    error_code: TraceErrorCode
    started_at_utc: datetime
    finished_at_utc: datetime | None
    latency_ms: int
    item_count: int

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != OBSERVABILITY_SCHEMA_VERSION
        ):
            raise ValueError("Observability schema version is invalid")
        _require_uuid(self.trace_id, "trace identifier")
        _require_enum(self.stage, TraceStage, "trace stage")
        _require_enum(self.outcome, StageOutcome, "stage outcome")
        _require_enum(self.reason_code, TraceReasonCode, "reason code")
        _require_enum(self.error_code, TraceErrorCode, "error code")
        if type(self.sequence) is not int or self.sequence != _TRACE_STAGE_SEQUENCE[self.stage]:
            raise ValueError("Trace stage sequence is invalid")
        _require_utc(self.started_at_utc, "stage start timestamp")
        _require_utc(self.finished_at_utc, "stage finish timestamp", optional=True)
        _require_nonnegative_int(self.latency_ms, "stage latency")
        _require_nonnegative_int(self.item_count, "stage item count")
        if self.outcome is StageOutcome.STARTED:
            if self.finished_at_utc is not None:
                raise ValueError("Started stage cannot have a finish timestamp")
        elif self.finished_at_utc is None:
            raise ValueError("Finished stage requires a finish timestamp")
        if self.finished_at_utc is not None and self.finished_at_utc < self.started_at_utc:
            raise ValueError("Stage timestamps are inconsistent")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "trace_id": str(self.trace_id),
            "stage": self.stage.value,
            "sequence": self.sequence,
            "outcome": self.outcome.value,
            "reason_code": self.reason_code.value,
            "error_code": self.error_code.value,
            "started_at_utc": _utc_text(self.started_at_utc),
            "finished_at_utc": _utc_text(self.finished_at_utc),
            "latency_ms": self.latency_ms,
            "item_count": self.item_count,
        }


type ObservabilityRecord = TraceMetadata | TraceStageMetadata


@runtime_checkable
class ObservabilityRecorder(Protocol):
    def record(self, record: ObservabilityRecord) -> None: ...

    def snapshot(self) -> tuple[ObservabilityRecord, ...]: ...


@runtime_checkable
class DurableObservabilityRecorder(ObservabilityRecorder, Protocol):
    """Optional recorder extension for crash-recoverable trace persistence."""

    def start_trace(self, trace: TraceMetadata) -> None: ...

    def record_progress(self, trace: TraceMetadata, stage: TraceStageMetadata) -> None: ...

    def finish_trace(
        self,
        trace: TraceMetadata,
        stages: Sequence[TraceStageMetadata],
    ) -> None: ...


def _validate_record_type(record: object) -> None:
    if not isinstance(record, TraceMetadata | TraceStageMetadata):
        raise TypeError("Observability record type is invalid")


class NoOpObservabilityRecorder:
    """Default recorder that validates metadata shape and retains nothing."""

    __slots__ = ()

    def record(self, record: ObservabilityRecord) -> None:
        _validate_record_type(record)

    def snapshot(self) -> tuple[ObservabilityRecord, ...]:
        return ()

    def __repr__(self) -> str:
        return "NoOpObservabilityRecorder()"


class InMemoryObservabilityRecorder:
    """Thread-safe fake recorder for deterministic tests only."""

    __slots__ = ("_lock", "_records")

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: list[ObservabilityRecord] = []

    def record(self, record: ObservabilityRecord) -> None:
        _validate_record_type(record)
        with self._lock:
            self._records.append(record)

    def snapshot(self) -> tuple[ObservabilityRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def __repr__(self) -> str:
        return "InMemoryObservabilityRecorder()"


@dataclass(slots=True, repr=False)
class DialogueTrace:
    """One transient metadata-only trace builder; raw scope values are never retained."""

    recorder: ObservabilityRecorder
    trace_id: UUID
    request_id: UUID
    scope_tags: ScopeTags
    input_chars: int
    provider_kind: ProviderKind
    persona_version: str | None
    started_at_utc: datetime
    started_monotonic: float
    wall_clock: Callable[[], datetime]
    monotonic_clock: Callable[[], float]
    attempt_kind: AttemptKind = AttemptKind.INITIAL
    execution_id: UUID | None = None
    idempotency_outcome: IdempotencyOutcome = IdempotencyOutcome.NOT_REACHED
    short_term_outcome: ShortTermOutcome = ShortTermOutcome.NOT_REACHED
    long_term_outcome: LongTermOutcome = LongTermOutcome.NOT_REACHED
    relationship_outcome: RelationshipOutcome = RelationshipOutcome.NOT_REACHED
    provider_dispatch_count: int = 0
    provider_wait_ms: int = 0
    provider_latency_ms: int = 0
    context_budget_units: int = 0
    selected_short_term_turns: int = 0
    selected_long_term_facts: int = 0
    output_chars: int = 0
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0
    _stage_values: (
        dict[
            TraceStage,
            tuple[StageOutcome, TraceReasonCode, TraceErrorCode, datetime, datetime, int],
        ]
        | None
    ) = None
    _finished: bool = False
    _recorder_failed: bool = False
    orphaned: bool = False

    def __post_init__(self) -> None:
        self._stage_values = {}

    def open(self) -> None:
        durable = self._durable_recorder()
        if durable is not None:
            self._safe_durable_call(lambda: durable.start_trace(self._open_metadata()))

    def stage(
        self,
        stage: TraceStage,
        outcome: StageOutcome = StageOutcome.COMPLETED,
        *,
        reason_code: TraceReasonCode = TraceReasonCode.COMPLETED,
        error_code: TraceErrorCode = TraceErrorCode.NONE,
        item_count: int = 0,
        started_at_utc: datetime | None = None,
    ) -> None:
        if self._finished:
            return
        now = self.wall_clock()
        started = now if started_at_utc is None else started_at_utc
        if self._stage_values is None:
            raise RuntimeError("Observability stage state is unavailable")
        self._stage_values[stage] = (
            outcome,
            reason_code,
            error_code,
            started,
            now,
            item_count,
        )
        durable = self._durable_recorder()
        if durable is not None:
            stage_record = self._stage_record(stage, self._stage_values[stage])
            self._safe_durable_call(
                lambda: durable.record_progress(self._open_metadata(), stage_record)
            )

    def finish(
        self,
        *,
        terminal_outcome: TerminalOutcome,
        reason_code: TraceReasonCode,
        error_code: TraceErrorCode = TraceErrorCode.NONE,
        retryable: bool = False,
        from_cache: bool = False,
    ) -> None:
        if self._finished:
            return
        self._finished = True
        finished_at = self.wall_clock()
        self._ensure_terminal_stage(
            finished_at=finished_at,
            reason_code=reason_code,
            error_code=error_code,
            terminal_outcome=terminal_outcome,
        )
        record = TraceMetadata(
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=self.trace_id,
            request_id=self.request_id,
            execution_id=self.execution_id,
            attempt_kind=self.attempt_kind,
            scope_tags=self.scope_tags,
            persona_version=self.persona_version,
            provider_kind=self.provider_kind,
            record_status=RecordStatus.COMPLETE,
            terminal_outcome=terminal_outcome,
            error_code=error_code,
            reason_code=reason_code,
            idempotency_outcome=self.idempotency_outcome,
            short_term_outcome=self.short_term_outcome,
            long_term_outcome=self.long_term_outcome,
            relationship_outcome=self.relationship_outcome,
            retryable=retryable,
            from_cache=from_cache,
            provider_dispatch_count=self.provider_dispatch_count,
            started_at_utc=self.started_at_utc,
            finished_at_utc=finished_at,
            total_latency_ms=max(
                0,
                round((self.monotonic_clock() - self.started_monotonic) * 1_000),
            ),
            provider_wait_ms=self.provider_wait_ms,
            provider_latency_ms=self.provider_latency_ms,
            context_budget_units=self.context_budget_units,
            selected_short_term_turns=self.selected_short_term_turns,
            selected_long_term_facts=self.selected_long_term_facts,
            input_chars=self.input_chars,
            output_chars=self.output_chars,
            prompt_tokens=self.usage_prompt_tokens,
            completion_tokens=self.usage_completion_tokens,
            total_tokens=self.usage_prompt_tokens + self.usage_completion_tokens,
            cost_micro_usd=0,
        )
        durable = self._durable_recorder()
        if durable is not None:
            self._safe_durable_call(
                lambda: durable.finish_trace(record, self._stage_records(finished_at))
            )
        else:
            self._flush_stages(finished_at)
            self._safe_record(record)

    def _ensure_terminal_stage(
        self,
        *,
        finished_at: datetime,
        reason_code: TraceReasonCode,
        error_code: TraceErrorCode,
        terminal_outcome: TerminalOutcome,
    ) -> None:
        outcome = {
            TerminalOutcome.COMPLETED: StageOutcome.COMPLETED,
            TerminalOutcome.DEGRADED: StageOutcome.COMPLETED,
            TerminalOutcome.REPLAYED: StageOutcome.COMPLETED,
            TerminalOutcome.CANCELLED: StageOutcome.CANCELLED,
            TerminalOutcome.ORPHANED: StageOutcome.CANCELLED,
        }.get(terminal_outcome, StageOutcome.FAILED)
        if self._stage_values is None:
            raise RuntimeError("Observability stage state is unavailable")
        self._stage_values[TraceStage.TERMINAL] = (
            outcome,
            reason_code,
            error_code,
            finished_at,
            finished_at,
            0,
        )

    def _flush_stages(self, finished_at: datetime) -> None:
        for stage in self._stage_records(finished_at):
            self._safe_record(stage)

    def _stage_records(self, finished_at: datetime) -> tuple[TraceStageMetadata, ...]:
        if self._stage_values is None:
            raise RuntimeError("Observability stage state is unavailable")
        records: list[TraceStageMetadata] = []
        for stage in TraceStage:
            values = self._stage_values.get(stage)
            if values is None:
                values = (
                    StageOutcome.NOT_REACHED,
                    TraceReasonCode.NOT_REACHED,
                    TraceErrorCode.NONE,
                    finished_at,
                    finished_at,
                    0,
                )
            records.append(self._stage_record(stage, values))
        return tuple(records)

    def _stage_record(
        self,
        stage: TraceStage,
        values: tuple[
            StageOutcome,
            TraceReasonCode,
            TraceErrorCode,
            datetime,
            datetime,
            int,
        ],
    ) -> TraceStageMetadata:
        outcome, reason, error, started, finished, item_count = values
        return TraceStageMetadata(
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=self.trace_id,
            stage=stage,
            sequence=_TRACE_STAGE_SEQUENCE[stage],
            outcome=outcome,
            reason_code=reason,
            error_code=error,
            started_at_utc=started,
            finished_at_utc=finished,
            latency_ms=max(0, round((finished - started).total_seconds() * 1_000)),
            item_count=item_count,
        )

    def _open_metadata(self) -> TraceMetadata:
        attempt_kind = (
            AttemptKind.INITIAL
            if self.attempt_kind is AttemptKind.CACHE_REPLAY
            else self.attempt_kind
        )
        return TraceMetadata(
            schema_version=OBSERVABILITY_SCHEMA_VERSION,
            trace_id=self.trace_id,
            request_id=self.request_id,
            execution_id=self.execution_id,
            attempt_kind=attempt_kind,
            scope_tags=self.scope_tags,
            persona_version=self.persona_version,
            provider_kind=self.provider_kind,
            record_status=RecordStatus.OPEN,
            terminal_outcome=None,
            error_code=TraceErrorCode.NONE,
            reason_code=TraceReasonCode.NOT_REACHED,
            idempotency_outcome=self.idempotency_outcome,
            short_term_outcome=self.short_term_outcome,
            long_term_outcome=self.long_term_outcome,
            relationship_outcome=self.relationship_outcome,
            retryable=False,
            from_cache=False,
            provider_dispatch_count=self.provider_dispatch_count,
            started_at_utc=self.started_at_utc,
            finished_at_utc=None,
            total_latency_ms=max(
                0,
                round((self.monotonic_clock() - self.started_monotonic) * 1_000),
            ),
            provider_wait_ms=self.provider_wait_ms,
            provider_latency_ms=self.provider_latency_ms,
            context_budget_units=self.context_budget_units,
            selected_short_term_turns=self.selected_short_term_turns,
            selected_long_term_facts=self.selected_long_term_facts,
            input_chars=self.input_chars,
            output_chars=self.output_chars,
            prompt_tokens=self.usage_prompt_tokens,
            completion_tokens=self.usage_completion_tokens,
            total_tokens=self.usage_prompt_tokens + self.usage_completion_tokens,
            cost_micro_usd=0,
        )

    def _durable_recorder(self) -> DurableObservabilityRecorder | None:
        if isinstance(self.recorder, DurableObservabilityRecorder):
            return self.recorder
        return None

    def _safe_durable_call(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception:
            if not self._recorder_failed:
                _LOGGER.warning("observability_unavailable")
                self._recorder_failed = True

    def _safe_record(self, record: ObservabilityRecord) -> None:
        try:
            self.recorder.record(record)
        except Exception:
            if not self._recorder_failed:
                _LOGGER.warning("observability_unavailable")
                self._recorder_failed = True


class DialogueObservability:
    """Dependency-injected, default-off factory for dialogue trace attempts."""

    __slots__ = ("_monotonic_clock", "_provider_kind", "_recorder", "_scope_key", "_wall_clock")

    def __init__(
        self,
        *,
        recorder: ObservabilityRecorder | None = None,
        scope_key: bytes | None = None,
        provider_kind: ProviderKind = ProviderKind.UNKNOWN,
        wall_clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
    ) -> None:
        self._recorder = recorder or NoOpObservabilityRecorder()
        if not isinstance(self._recorder, ObservabilityRecorder):
            raise TypeError("Observability recorder is invalid")
        if not isinstance(provider_kind, ProviderKind):
            raise TypeError("Observability provider kind is invalid")
        if scope_key is not None:
            derive_scope_tag(
                key=scope_key,
                dimension=ScopeDimension.PLAYER,
                identifier="validation_probe",
            )
        self._scope_key = scope_key
        self._provider_kind = provider_kind
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._monotonic_clock = monotonic_clock or time.monotonic

    @property
    def recorder(self) -> ObservabilityRecorder:
        return self._recorder

    def start_validated(
        self,
        *,
        trace_id: UUID,
        request_id: UUID,
        player_id: str,
        npc_id: str,
        conversation_id: UUID,
        input_chars: int,
    ) -> DialogueTrace | None:
        if isinstance(self._recorder, NoOpObservabilityRecorder):
            return None
        if self._scope_key is None:
            raise RuntimeError("Observability scope key is unavailable")
        started_at = self._wall_clock()
        trace = DialogueTrace(
            recorder=self._recorder,
            trace_id=trace_id,
            request_id=request_id,
            scope_tags=ScopeTags.from_identifiers(
                key=self._scope_key,
                player_id=player_id,
                npc_id=npc_id,
                conversation_id=str(conversation_id),
            ),
            input_chars=input_chars,
            provider_kind=self._provider_kind,
            persona_version=None,
            started_at_utc=started_at,
            started_monotonic=self._monotonic_clock(),
            wall_clock=self._wall_clock,
            monotonic_clock=self._monotonic_clock,
        )
        trace.open()
        trace.stage(TraceStage.HTTP_RECEIVED)
        trace.stage(TraceStage.REQUEST_VALIDATION)
        return trace

    def record_validation_failure(self, trace_id: UUID) -> None:
        if isinstance(self._recorder, NoOpObservabilityRecorder):
            return
        now = self._wall_clock()
        for sequence, stage in enumerate(TraceStage, start=1):
            if stage is TraceStage.HTTP_RECEIVED:
                outcome = StageOutcome.COMPLETED
                error = TraceErrorCode.NONE
            elif stage is TraceStage.REQUEST_VALIDATION or stage is TraceStage.TERMINAL:
                outcome = StageOutcome.FAILED
                error = TraceErrorCode.VALIDATION_ERROR
            else:
                outcome = StageOutcome.NOT_REACHED
                error = TraceErrorCode.NONE
            self._safe_boundary_record(
                TraceStageMetadata(
                    schema_version=OBSERVABILITY_SCHEMA_VERSION,
                    trace_id=trace_id,
                    stage=stage,
                    sequence=sequence,
                    outcome=outcome,
                    reason_code=(
                        TraceReasonCode.NOT_REACHED
                        if outcome is StageOutcome.NOT_REACHED
                        else TraceReasonCode.NONE
                    ),
                    error_code=error,
                    started_at_utc=now,
                    finished_at_utc=now,
                    latency_ms=0,
                    item_count=0,
                )
            )
        self._safe_boundary_record(
            TraceMetadata(
                schema_version=OBSERVABILITY_SCHEMA_VERSION,
                trace_id=trace_id,
                request_id=None,
                execution_id=None,
                attempt_kind=AttemptKind.VALIDATION_FAILURE,
                scope_tags=None,
                persona_version=None,
                provider_kind=ProviderKind.UNKNOWN,
                record_status=RecordStatus.COMPLETE,
                terminal_outcome=TerminalOutcome.REJECTED,
                error_code=TraceErrorCode.VALIDATION_ERROR,
                reason_code=TraceReasonCode.NOT_REACHED,
                idempotency_outcome=IdempotencyOutcome.NOT_REACHED,
                short_term_outcome=ShortTermOutcome.NOT_REACHED,
                long_term_outcome=LongTermOutcome.NOT_REACHED,
                relationship_outcome=RelationshipOutcome.NOT_REACHED,
                retryable=False,
                from_cache=False,
                provider_dispatch_count=0,
                started_at_utc=now,
                finished_at_utc=now,
                total_latency_ms=0,
                provider_wait_ms=0,
                provider_latency_ms=0,
                context_budget_units=0,
                selected_short_term_turns=0,
                selected_long_term_facts=0,
                input_chars=0,
                output_chars=0,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_micro_usd=0,
            )
        )

    def _safe_boundary_record(self, record: ObservabilityRecord) -> None:
        try:
            self._recorder.record(record)
        except Exception:
            _LOGGER.warning("observability_unavailable")


class TraceLinkageError(ValueError):
    """Safe aggregate linkage error that never exposes an identifier."""


def validate_trace_linkage(records: Sequence[TraceMetadata]) -> None:
    """Validate request/trace/execution cardinality without retaining raw scope values."""

    trace_ids: set[UUID] = set()
    execution_groups: dict[UUID, list[TraceMetadata]] = {}
    for record in records:
        if not isinstance(record, TraceMetadata):
            raise TypeError("Trace linkage record type is invalid")
        if record.trace_id in trace_ids:
            raise TraceLinkageError("Trace identifier is duplicated")
        trace_ids.add(record.trace_id)
        if record.execution_id is not None:
            execution_groups.setdefault(record.execution_id, []).append(record)

    for group in execution_groups.values():
        request_ids = {record.request_id for record in group}
        if len(request_ids) != 1:
            raise TraceLinkageError("Execution crossed logical request scope")
        if len(group) == 1:
            continue
        if sum(record.provider_dispatch_count for record in group) != 1:
            raise TraceLinkageError("Shared execution dispatch count is inconsistent")
        if sum(record.idempotency_outcome is IdempotencyOutcome.NEW for record in group) != 1:
            raise TraceLinkageError("Shared execution owner is inconsistent")
        allowed = {IdempotencyOutcome.NEW, IdempotencyOutcome.INFLIGHT_SHARED}
        if any(record.idempotency_outcome not in allowed for record in group):
            raise TraceLinkageError("Execution linkage contains a non-shared trace")

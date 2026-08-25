"""SQLite persistence for deterministic, metadata-only relationship decisions."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from cyber_town.domain.relationship import (
    InteractionCategory,
    InteractionSuggestion,
    RelationshipAuditEvent,
    RelationshipEngine,
    RelationshipReasonCode,
    RelationshipScope,
    RelationshipStage,
    RelationshipState,
)
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import (
    LongTermMemoryStorageError,
    SqliteLongTermMemoryRepository,
)


class RelationshipStorageError(RuntimeError):
    """The approved relationship storage cannot be accessed safely."""


class RelationshipConflictError(RelationshipStorageError):
    """A relationship request ID is already bound to different immutable inputs."""


class SqliteRelationshipRepository:
    """Atomically persist a deterministic decision and bodyless audit evidence."""

    def __init__(self, *, database_path: Path, allowed_root: Path) -> None:
        self._storage = SqliteLongTermMemoryRepository(
            database_path=database_path,
            allowed_root=allowed_root,
        )
        self.database_path = self._storage.database_path
        self._busy_timeout_milliseconds = 2_000

    def initialize(self) -> None:
        """Apply only approved migrations through the shared storage boundary."""

        try:
            self._storage.initialize()
        except LongTermMemoryStorageError as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def get_state(self, scope: RelationshipScope) -> RelationshipState:
        """Return a scope-owned persisted state or its deterministic initial state."""

        self._require_scope(scope)
        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT player_id, npc_id, score, stage, rule_version, last_effective_utc_day "
                    "FROM relationship_states WHERE player_id = ? AND npc_id = ?",
                    (scope.player_id, scope.npc_id),
                ).fetchone()
                persisted = (
                    RelationshipState.initial(scope) if row is None else self._state_from_row(row)
                )
                rows = connection.execute(
                    "SELECT * FROM relationship_events WHERE player_id = ? AND npc_id = ? "
                    "ORDER BY event_sequence",
                    (scope.player_id, scope.npc_id),
                ).fetchall()
                replayed = self._replay_rows(scope, rows)
                if persisted != replayed:
                    raise RelationshipStorageError("Relationship state does not match its audit")
                return replayed
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def apply_interaction(
        self,
        *,
        scope: RelationshipScope,
        request_id: UUID,
        request_fingerprint: str,
        trace_id: UUID,
        conversation_id: UUID,
        raw_suggestion: object,
        occurred_at: datetime,
        engine: RelationshipEngine | None = None,
    ) -> RelationshipAuditEvent:
        """Idempotently decide and persist one interaction while holding the write lock."""

        self._require_scope(scope)
        self._require_identifier("request", request_id)
        self._require_identifier("trace", trace_id)
        self._require_identifier("conversation", conversation_id)
        self._require_fingerprint(request_fingerprint)
        if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
            raise ValueError("Relationship interaction time must be timezone-aware")
        if occurred_at.utcoffset() is None:
            raise ValueError("Relationship interaction time must be timezone-aware")
        if engine is None:
            engine = RelationshipEngine()
        if not isinstance(engine, RelationshipEngine):
            raise TypeError("Relationship interaction requires a deterministic engine")

        occurred_at_utc = occurred_at.astimezone(UTC)
        timestamp = int(occurred_at_utc.timestamp())
        if timestamp <= 0:
            raise ValueError("Relationship interaction time must be after the Unix epoch")
        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT * FROM relationship_events WHERE request_id = ?", (str(request_id),)
                    ).fetchone()
                    if existing is not None:
                        event = self._event_from_row(existing)
                        if event.scope != scope or event.request_fingerprint != request_fingerprint:
                            raise RelationshipConflictError(
                                "Relationship request conflicts with an existing request"
                            )
                        connection.commit()
                        return event

                    row = connection.execute(
                        "SELECT player_id, npc_id, score, stage, rule_version, "
                        "last_effective_utc_day "
                        "FROM relationship_states WHERE player_id = ? AND npc_id = ?",
                        (scope.player_id, scope.npc_id),
                    ).fetchone()
                    before = (
                        RelationshipState.initial(scope)
                        if row is None
                        else self._state_from_row(row)
                    )
                    decision = engine.decide(before, raw_suggestion, occurred_at=occurred_at_utc)
                    suggestion = InteractionSuggestion.from_untrusted(raw_suggestion)
                    event = RelationshipAuditEvent(
                        event_id=uuid4(),
                        scope=scope,
                        request_id=request_id,
                        request_fingerprint=request_fingerprint,
                        trace_id=trace_id,
                        conversation_id=conversation_id,
                        category=None if suggestion is None else suggestion.category,
                        confidence=None if suggestion is None else suggestion.confidence,
                        rule_version=decision.state.rule_version,
                        reason_code=decision.reason_code,
                        proposed_delta=decision.proposed_delta,
                        applied_delta=decision.applied_delta,
                        before_score=before.score,
                        before_stage=before.stage,
                        after_score=decision.state.score,
                        after_stage=decision.state.stage,
                        effective_utc_day=(
                            decision.state.last_effective_utc_day
                            if decision.applied_delta != 0
                            else None
                        ),
                        occurred_at=timestamp,
                    )
                    self._upsert_state(connection, decision.state, updated_at=timestamp)
                    self._insert_event(connection, event)
                    connection.commit()
                    return event
                except (sqlite3.Error, RelationshipStorageError):
                    connection.rollback()
                    raise
        except RelationshipStorageError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def replay(self, scope: RelationshipScope) -> RelationshipState:
        """Rebuild one scope from its bodyless audit chain and validate every transition."""

        self._require_scope(scope)
        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT * FROM relationship_events WHERE player_id = ? AND npc_id = ? "
                    "ORDER BY event_sequence",
                    (scope.player_id, scope.npc_id),
                ).fetchall()
                return self._replay_rows(scope, rows)
        except RelationshipStorageError:
            raise
        except (TypeError, ValueError) as error:
            raise RelationshipStorageError("Relationship audit replay is inconsistent") from error
        except sqlite3.Error as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def event_for_request(
        self,
        scope: RelationshipScope,
        request_id: UUID,
    ) -> RelationshipAuditEvent | None:
        """Return only a scope-owned event for the supplied immutable request identifier."""

        self._require_scope(scope)
        self._require_identifier("request", request_id)
        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM relationship_events WHERE player_id = ? AND npc_id = ? "
                    "AND request_id = ?",
                    (scope.player_id, scope.npc_id, str(request_id)),
                ).fetchone()
                return None if row is None else self._event_from_row(row)
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def event_columns(self) -> tuple[str, ...]:
        """Expose schema metadata for structural verification only, never event bodies."""

        try:
            with closing(self._connect()) as connection:
                return tuple(
                    str(row[1])
                    for row in connection.execute("PRAGMA table_info(relationship_events)")
                )
        except sqlite3.Error as error:
            raise RelationshipStorageError("Relationship storage is unavailable") from error

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self._busy_timeout_milliseconds / 1_000,
            isolation_level=None,
        )
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_milliseconds:d}")
        except sqlite3.Error:
            connection.close()
            raise
        return connection

    @staticmethod
    def _replay_rows(scope: RelationshipScope, rows: list[sqlite3.Row]) -> RelationshipState:
        state = RelationshipState.initial(scope)
        engine = RelationshipEngine()
        for row in rows:
            event = SqliteRelationshipRepository._event_from_row(row)
            raw_suggestion: object = (
                None
                if event.category is None
                else {"category": event.category.value, "confidence": event.confidence}
            )
            suggestion = InteractionSuggestion.from_untrusted(raw_suggestion)
            expected = engine.decide(
                state,
                raw_suggestion,
                occurred_at=datetime.fromtimestamp(event.occurred_at, tz=UTC),
            )
            if (
                event.before_score != state.score
                or event.before_stage is not state.stage
                or event.rule_version != state.rule_version
                or event.category != (None if suggestion is None else suggestion.category)
                or event.confidence != (None if suggestion is None else suggestion.confidence)
            ):
                raise RelationshipStorageError("Relationship audit replay is inconsistent")
            if (
                event.proposed_delta != expected.proposed_delta
                or event.applied_delta != expected.applied_delta
                or event.reason_code is not expected.reason_code
                or event.after_score != expected.state.score
                or event.after_stage is not expected.state.stage
                or event.effective_utc_day
                != (expected.state.last_effective_utc_day if event.applied_delta else None)
            ):
                raise RelationshipStorageError("Relationship audit replay is inconsistent")
            state = expected.state
        return state

    @staticmethod
    def _upsert_state(
        connection: sqlite3.Connection, state: RelationshipState, *, updated_at: int
    ) -> None:
        connection.execute(
            "INSERT INTO relationship_states "
            "(player_id, npc_id, score, stage, rule_version, last_effective_utc_day, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(player_id, npc_id) DO UPDATE SET score = excluded.score, "
            "stage = excluded.stage, rule_version = excluded.rule_version, "
            "last_effective_utc_day = excluded.last_effective_utc_day, "
            "updated_at = excluded.updated_at",
            (
                state.scope.player_id,
                state.scope.npc_id,
                state.score,
                state.stage.value,
                state.rule_version,
                None
                if state.last_effective_utc_day is None
                else state.last_effective_utc_day.isoformat(),
                updated_at,
            ),
        )

    @staticmethod
    def _insert_event(connection: sqlite3.Connection, event: RelationshipAuditEvent) -> None:
        connection.execute(
            "INSERT INTO relationship_events ("
            "event_id, player_id, npc_id, request_id, request_fingerprint, trace_id, "
            "conversation_id, category, confidence, rule_version, reason_code, proposed_delta, "
            "applied_delta, before_score, before_stage, after_score, after_stage, "
            "effective_utc_day, occurred_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(event.event_id),
                event.scope.player_id,
                event.scope.npc_id,
                str(event.request_id),
                event.request_fingerprint,
                str(event.trace_id),
                str(event.conversation_id),
                None if event.category is None else event.category.value,
                event.confidence,
                event.rule_version,
                event.reason_code.value,
                event.proposed_delta,
                event.applied_delta,
                event.before_score,
                event.before_stage.value,
                event.after_score,
                event.after_stage.value,
                None if event.effective_utc_day is None else event.effective_utc_day.isoformat(),
                event.occurred_at,
            ),
        )

    @staticmethod
    def _state_from_row(row: sqlite3.Row) -> RelationshipState:
        return RelationshipState(
            scope=RelationshipScope(str(row["player_id"]), str(row["npc_id"])),
            score=int(row["score"]),
            stage=RelationshipStage(str(row["stage"])),
            rule_version=str(row["rule_version"]),
            last_effective_utc_day=(
                None
                if row["last_effective_utc_day"] is None
                else date.fromisoformat(str(row["last_effective_utc_day"]))
            ),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> RelationshipAuditEvent:
        return RelationshipAuditEvent(
            event_id=UUID(row["event_id"]),
            scope=RelationshipScope(row["player_id"], row["npc_id"]),
            request_id=UUID(row["request_id"]),
            request_fingerprint=row["request_fingerprint"],
            trace_id=UUID(row["trace_id"]),
            conversation_id=UUID(row["conversation_id"]),
            category=None if row["category"] is None else InteractionCategory(row["category"]),
            confidence=row["confidence"],
            rule_version=row["rule_version"],
            reason_code=RelationshipReasonCode(row["reason_code"]),
            proposed_delta=row["proposed_delta"],
            applied_delta=row["applied_delta"],
            before_score=row["before_score"],
            before_stage=RelationshipStage(row["before_stage"]),
            after_score=row["after_score"],
            after_stage=RelationshipStage(row["after_stage"]),
            effective_utc_day=(
                None
                if row["effective_utc_day"] is None
                else date.fromisoformat(row["effective_utc_day"])
            ),
            occurred_at=row["occurred_at"],
        )

    @staticmethod
    def _require_scope(scope: RelationshipScope) -> None:
        if not isinstance(scope, RelationshipScope):
            raise TypeError("Relationship scope must contain player and NPC identifiers")

    @staticmethod
    def _require_identifier(name: str, value: UUID) -> None:
        if not isinstance(value, UUID):
            raise TypeError(f"Relationship {name} identifier must be a UUID")

    @staticmethod
    def _require_fingerprint(value: str) -> None:
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError("Relationship request fingerprint is invalid")

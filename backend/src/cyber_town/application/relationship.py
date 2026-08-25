"""Application ownership for deterministic relationship writes and read snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from cyber_town.domain.relationship import (
    RelationshipAuditEvent,
    RelationshipScope,
    RelationshipState,
)
from cyber_town.infrastructure.persistence.sqlite_relationship import SqliteRelationshipRepository


@dataclass(frozen=True, slots=True)
class RelationshipReadResult:
    """One scope-limited current state and, optionally, its matching request event."""

    state: RelationshipState
    event: RelationshipAuditEvent | None


class RelationshipService:
    """Bridge validated completed dialogue metadata to the deterministic repository."""

    def __init__(
        self,
        *,
        repository: SqliteRelationshipRepository,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(repository, SqliteRelationshipRepository):
            raise TypeError("Relationship service requires the approved SQLite repository")
        self._repository = repository
        self._now = now or (lambda: datetime.now(UTC))

    def record_completed_dialogue(
        self,
        *,
        player_id: str,
        npc_id: str,
        request_id: UUID,
        request_fingerprint: str,
        trace_id: UUID,
        conversation_id: UUID,
        raw_suggestion: object,
    ) -> RelationshipAuditEvent:
        """Persist only a successful dialogue's untrusted suggestion through fixed rules."""

        return self._repository.apply_interaction(
            scope=RelationshipScope(player_id, npc_id),
            request_id=request_id,
            request_fingerprint=request_fingerprint,
            trace_id=trace_id,
            conversation_id=conversation_id,
            raw_suggestion=raw_suggestion,
            occurred_at=self._now(),
        )

    def read(
        self,
        *,
        player_id: str,
        npc_id: str,
        request_id: UUID | None,
    ) -> RelationshipReadResult:
        """Read one isolated state without creating a state row or changing any score."""

        scope = RelationshipScope(player_id, npc_id)
        return RelationshipReadResult(
            state=self._repository.get_state(scope),
            event=(
                None
                if request_id is None
                else self._repository.event_for_request(scope, request_id)
            ),
        )

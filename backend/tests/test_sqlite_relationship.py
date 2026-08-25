from __future__ import annotations

import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from cyber_town.domain.relationship import RelationshipAuditEvent, RelationshipScope
from cyber_town.infrastructure.persistence.sqlite_relationship import (
    RelationshipConflictError,
    RelationshipStorageError,
    SqliteRelationshipRepository,
)


def make_repository(tmp_path: Path) -> SqliteRelationshipRepository:
    repository = SqliteRelationshipRepository(
        database_path=tmp_path / "isolated.sqlite3",
        allowed_root=tmp_path,
    )
    repository.initialize()
    return repository


def apply_supportive(
    repository: SqliteRelationshipRepository,
    *,
    request: int = 1,
    scope: RelationshipScope | None = None,
) -> RelationshipAuditEvent:
    if scope is None:
        scope = RelationshipScope("local_player", "neon_guide")
    return repository.apply_interaction(
        scope=scope,
        request_id=UUID(int=request),
        request_fingerprint=f"{request:064x}",
        trace_id=UUID(int=request + 100),
        conversation_id=UUID(int=request + 200),
        raw_suggestion={"category": "supportive", "confidence": 80},
        occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_relationship_repository_persists_a_metadata_only_event(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)

    event = repository.apply_interaction(
        scope=RelationshipScope("local_player", "neon_guide"),
        request_id=UUID(int=1),
        request_fingerprint="a" * 64,
        trace_id=UUID(int=2),
        conversation_id=UUID(int=3),
        raw_suggestion={"category": "supportive", "confidence": 80},
        occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
    )

    assert event.applied_delta == 2
    assert event.after_score == 22
    assert repository.get_state(event.scope).score == 22
    assert {column for column in repository.event_columns()} == {
        "event_sequence",
        "event_id",
        "player_id",
        "npc_id",
        "request_id",
        "request_fingerprint",
        "trace_id",
        "conversation_id",
        "category",
        "confidence",
        "rule_version",
        "reason_code",
        "proposed_delta",
        "applied_delta",
        "before_score",
        "before_stage",
        "after_score",
        "after_stage",
        "effective_utc_day",
        "occurred_at",
    }
    assert not {"message", "prompt", "reply", "response", "provider_body"} & set(
        repository.event_columns()
    )


def test_relationship_repository_replays_same_request_and_rejects_conflicts(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    scope = RelationshipScope("local_player", "neon_guide")
    first = repository.apply_interaction(
        scope=scope,
        request_id=UUID(int=1),
        request_fingerprint="a" * 64,
        trace_id=UUID(int=2),
        conversation_id=UUID(int=3),
        raw_suggestion={"category": "friendly", "confidence": 80},
        occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
    )
    assert (
        repository.apply_interaction(
            scope=scope,
            request_id=UUID(int=1),
            request_fingerprint="a" * 64,
            trace_id=UUID(int=2),
            conversation_id=UUID(int=3),
            raw_suggestion={"category": "friendly", "confidence": 80},
            occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
        == first
    )
    assert repository.get_state(scope).score == 21

    with pytest.raises(RelationshipConflictError):
        repository.apply_interaction(
            scope=scope,
            request_id=UUID(int=1),
            request_fingerprint="b" * 64,
            trace_id=UUID(int=2),
            conversation_id=UUID(int=3),
            raw_suggestion={"category": "friendly", "confidence": 80},
            occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
        )
    with pytest.raises(RelationshipConflictError):
        repository.apply_interaction(
            scope=RelationshipScope("another_player", "neon_guide"),
            request_id=UUID(int=1),
            request_fingerprint="a" * 64,
            trace_id=UUID(int=2),
            conversation_id=UUID(int=3),
            raw_suggestion={"category": "friendly", "confidence": 80},
            occurred_at=datetime(2026, 8, 25, tzinfo=UTC),
        )


def test_relationship_repository_keeps_scopes_isolated_and_replays_audit(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    first = apply_supportive(repository)
    other_scope = RelationshipScope("another_player", "neon_guide")

    assert repository.get_state(other_scope).score == 20
    assert repository.replay(first.scope) == repository.get_state(first.scope)
    assert repository.replay(other_scope).score == 20


def test_relationship_repository_rejects_a_tampered_audit_chain(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    apply_supportive(repository)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("UPDATE relationship_events SET after_score = 99")

    with pytest.raises(RelationshipStorageError, match="replay"):
        repository.replay(RelationshipScope("local_player", "neon_guide"))


def test_relationship_repository_rejects_state_that_disagrees_with_audit(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    apply_supportive(repository)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE relationship_states SET score = 23, stage = 'acquaintance'"
        )

    with pytest.raises(RelationshipStorageError, match="state does not match"):
        repository.get_state(RelationshipScope("local_player", "neon_guide"))


def test_relationship_repository_rolls_back_state_when_audit_insert_fails(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_relationship_event BEFORE INSERT ON relationship_events "
            "BEGIN SELECT RAISE(FAIL, 'synthetic audit failure'); END"
        )

    with pytest.raises(RelationshipStorageError):
        apply_supportive(repository)

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM relationship_states").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM relationship_events").fetchone() == (0,)


def test_relationship_repository_fails_closed_when_database_is_locked(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository._busy_timeout_milliseconds = 1
    blocker = sqlite3.connect(repository.database_path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(RelationshipStorageError):
            apply_supportive(repository)
    finally:
        blocker.rollback()
        blocker.close()

    assert repository.get_state(RelationshipScope("local_player", "neon_guide")).score == 20


def test_relationship_repository_serializes_concurrent_scope_writes(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)

    with ThreadPoolExecutor(max_workers=4) as executor:
        events = tuple(
            executor.map(lambda request: apply_supportive(repository, request=request), range(1, 5))
        )

    assert sum(event.applied_delta for event in events) == 2
    assert repository.get_state(RelationshipScope("local_player", "neon_guide")).score == 22


def test_relationship_repository_upgrades_an_existing_v1_database_without_data_loss(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    migration_path = (
        Path(__file__).parents[1]
        / "src/cyber_town/infrastructure/persistence/migrations/0001_long_term_memory.sql"
    )
    migration = migration_path.read_bytes()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL UNIQUE, "
            "checksum TEXT NOT NULL, applied_at INTEGER NOT NULL)"
        )
        connection.executescript(migration.decode("utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
            (1, "0001_long_term_memory.sql", hashlib.sha256(migration).hexdigest(), 1),
        )
        connection.execute(
            "INSERT INTO long_term_memories (memory_id, player_id, npc_id, memory_type, fact_key, "
            "fact_value, source_conversation_id, source_request_id, source_trace_id, importance, "
            "confidence, created_at, updated_at, expires_at, version, status) VALUES "
            "('00000000-0000-0000-0000-000000000001', 'local_player', 'neon_guide', 'profile', "
            "'game_alias', 'BLUE-47', '00000000-0000-0000-0000-000000000002', "
            "'00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000004', "
            "3, 1000, 1700000000, 1700000000, NULL, 1, 'active')"
        )

    repository = SqliteRelationshipRepository(database_path=database_path, allowed_root=tmp_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM long_term_memories").fetchone() == (1,)
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [
            (1,),
            (2,),
        ]

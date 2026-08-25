from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

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


def make_record(
    *,
    index: int = 1,
    player_id: str = "local_player",
    npc_id: str = "neon_guide",
    fact_key: str = "game_alias",
    fact_value: str = "BLUE-47",
) -> LongTermMemoryRecord:
    return LongTermMemoryRecord(
        memory_id=UUID(int=index),
        scope=LongTermMemoryScope(player_id, npc_id),
        memory_type=MemoryType.PROFILE,
        fact_key=fact_key,
        fact_value=fact_value,
        source_conversation_id=UUID(int=index + 1_000),
        source_request_id=UUID(int=index + 2_000),
        source_trace_id=UUID(int=index + 3_000),
        importance=3,
        confidence=1_000,
        created_at=1_700_000_000,
        updated_at=1_700_000_000,
        expires_at=1_702_592_000,
        version=1,
        status=MemoryStatus.ACTIVE,
    )


@pytest.fixture
def repository(tmp_path: Path) -> SqliteLongTermMemoryRepository:
    result = SqliteLongTermMemoryRepository(
        database_path=tmp_path / "isolated.sqlite3",
        allowed_root=tmp_path,
    )
    result.initialize()
    return result


def test_constructor_does_not_create_database_or_directories(tmp_path: Path) -> None:
    database_path = tmp_path / "isolated.sqlite3"

    SqliteLongTermMemoryRepository(database_path=database_path, allowed_root=tmp_path)

    assert not database_path.exists()


def test_repository_rejects_database_outside_approved_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SqliteLongTermMemoryRepository(
            database_path=tmp_path.parent / "outside.sqlite3",
            allowed_root=tmp_path,
        )


def test_repository_rejects_nonexistent_parent_without_creating_it(tmp_path: Path) -> None:
    database_path = tmp_path / "not-created" / "isolated.sqlite3"

    with pytest.raises(ValueError):
        SqliteLongTermMemoryRepository(database_path=database_path, allowed_root=tmp_path)

    assert not database_path.parent.exists()


@pytest.mark.parametrize("name", ["isolated.db", "isolated", "isolated.sqlite3-wal"])
def test_repository_rejects_unapproved_sqlite_filename(name: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SqliteLongTermMemoryRepository(database_path=tmp_path / name, allowed_root=tmp_path)


def test_initialize_creates_only_versioned_schema_in_isolated_database(tmp_path: Path) -> None:
    database_path = tmp_path / "isolated.sqlite3"
    repository = SqliteLongTermMemoryRepository(
        database_path=database_path,
        allowed_root=tmp_path,
    )

    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        migration = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchone()

    assert tables == {
        "schema_migrations",
        "long_term_memories",
        "memory_operations",
        "memory_events",
    }
    assert migration is not None
    assert migration[0] == 1
    assert migration[1] == "0001_long_term_memory.sql"
    assert len(migration[2]) == 64


def test_schema_contains_required_columns_and_no_raw_conversation_columns(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(long_term_memories)")}
        operation_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(memory_operations)")
        }
        event_columns = {row[1] for row in connection.execute("PRAGMA table_info(memory_events)")}

    assert columns == {
        "memory_id",
        "player_id",
        "npc_id",
        "memory_type",
        "fact_key",
        "fact_value",
        "source_conversation_id",
        "source_request_id",
        "source_trace_id",
        "importance",
        "confidence",
        "created_at",
        "updated_at",
        "expires_at",
        "version",
        "status",
    }
    assert "request_id" in operation_columns
    assert "fact_value" not in operation_columns
    assert "fact_value" not in event_columns
    assert "prompt" not in columns | operation_columns | event_columns
    assert "response" not in columns | operation_columns | event_columns


def test_schema_has_scope_expiration_fact_and_updated_indexes(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        indexes = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }

    assert "idx_long_term_memories_scope_status_expiry" in indexes
    assert "idx_long_term_memories_scope_fact" in indexes
    assert "idx_long_term_memories_updated" in indexes


def test_initialize_is_idempotent_and_preserves_existing_records(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()
    repository.save(record)

    repository.initialize()

    assert repository.get(record.scope, record.memory_id) == record
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone() == (1,)


def test_initialize_rejects_tampered_migration_without_recreating_database(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()
    repository.save(record)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("UPDATE schema_migrations SET checksum = 'invalid'")

    with pytest.raises(LongTermMemoryStorageError):
        repository.initialize()

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM long_term_memories").fetchone() == (1,)


def test_initialize_rejects_corrupted_database_without_overwriting_it(tmp_path: Path) -> None:
    database_path = tmp_path / "corrupt.sqlite3"
    original = b"synthetic-corrupt-sqlite-database"
    database_path.write_bytes(original)
    repository = SqliteLongTermMemoryRepository(
        database_path=database_path,
        allowed_root=tmp_path,
    )

    with pytest.raises(LongTermMemoryStorageError):
        repository.initialize()

    assert database_path.read_bytes() == original


def test_repository_round_trips_the_complete_record(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()

    repository.save(record)

    assert repository.get(record.scope, record.memory_id) == record
    assert repository.list_scope(record.scope) == (record,)


def test_repository_round_trips_permanent_record(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = replace(make_record(), expires_at=None)

    repository.save(record)

    assert repository.get(record.scope, record.memory_id) == record


def test_repository_round_trips_superseded_record(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = replace(make_record(), status=MemoryStatus.SUPERSEDED)

    repository.save(record)

    assert repository.get(record.scope, record.memory_id) == record
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT event_type FROM memory_events").fetchone() == ("updated",)


@pytest.mark.parametrize("status", [MemoryStatus.FORGOTTEN, MemoryStatus.EXPIRED])
def test_repository_round_trips_bodyless_tombstones(
    status: MemoryStatus,
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = replace(make_record(), status=status, fact_value=None)

    repository.save(record)

    assert repository.get(record.scope, record.memory_id) == record
    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT fact_value FROM long_term_memories").fetchone() == (None,)


@pytest.mark.parametrize(
    "other_scope",
    [
        LongTermMemoryScope("another_player", "neon_guide"),
        LongTermMemoryScope("local_player", "another_npc"),
    ],
)
def test_repository_never_returns_records_from_another_player_or_npc(
    other_scope: LongTermMemoryScope,
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()
    repository.save(record)

    assert repository.get(other_scope, record.memory_id) is None
    assert repository.list_scope(other_scope) == ()


def test_repository_uses_parameterized_queries_for_scope(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()
    repository.save(record)
    malicious_scope = LongTermMemoryScope("local_player' OR 1=1 --", "neon_guide")

    assert repository.get(malicious_scope, record.memory_id) is None
    assert repository.list_scope(malicious_scope) == ()


def test_repository_rejects_duplicate_business_key_without_overwriting_record(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    original = make_record()
    duplicate = make_record(index=2, fact_value="GREEN-24")
    repository.save(original)

    with pytest.raises(LongTermMemoryConflictError):
        repository.save(duplicate)

    assert repository.list_scope(original.scope) == (original,)


def test_repository_allows_same_fact_for_different_players_and_npcs(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    records = (
        make_record(index=1),
        make_record(index=2, player_id="another_player"),
        make_record(index=3, npc_id="another_npc"),
    )

    for record in records:
        repository.save(record)

    for record in records:
        assert repository.list_scope(record.scope) == (record,)


def test_repository_rolls_back_memory_when_audit_event_insert_fails(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_memory_event BEFORE INSERT ON memory_events "
            "BEGIN SELECT RAISE(FAIL, 'synthetic audit failure'); END"
        )

    with pytest.raises(LongTermMemoryStorageError):
        repository.save(make_record())

    with sqlite3.connect(repository.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM long_term_memories").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM memory_events").fetchone() == (0,)


def test_repository_fails_closed_when_database_is_locked(
    repository: SqliteLongTermMemoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repository, "_busy_timeout_milliseconds", 1)
    blocker = sqlite3.connect(repository.database_path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(LongTermMemoryStorageError):
            repository.save(make_record())
    finally:
        blocker.rollback()
        blocker.close()

    assert repository.list_scope(make_record().scope) == ()


def test_repository_configures_wal_foreign_keys_and_two_second_lock_boundary(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    with repository._connect() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (2_000,)


def test_repository_emits_bodyless_event_for_repository_write(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    record = make_record()
    repository.save(record)

    with sqlite3.connect(repository.database_path) as connection:
        event = connection.execute(
            "SELECT memory_id, event_type, request_id FROM memory_events"
        ).fetchone()

    assert event == (str(record.memory_id), "created", str(record.source_request_id))

"""Versioned, parameterized SQLite persistence for approved structured facts."""

from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from cyber_town.domain.long_term_memory import (
    LongTermMemoryRecord,
    LongTermMemoryScope,
    MemoryStatus,
    MemoryType,
)

_MIGRATIONS = (
    (1, "0001_long_term_memory.sql"),
    (2, "0002_relationship_state.sql"),
)
_BUSY_TIMEOUT_MILLISECONDS = 2_000


class LongTermMemoryStorageError(RuntimeError):
    """The existing SQLite state cannot be accessed safely."""


class LongTermMemoryConflictError(LongTermMemoryStorageError):
    """A long-term memory identifier or approved business key already exists."""


class LongTermMemoryCapacityError(LongTermMemoryStorageError):
    """An approved long-term scope or global active-memory limit is exhausted."""


class SqliteLongTermMemoryRepository:
    """Persist validated records without implementing application memory commands."""

    def __init__(self, *, database_path: Path, allowed_root: Path) -> None:
        if not isinstance(database_path, Path) or not isinstance(allowed_root, Path):
            raise TypeError("Long-term memory database boundaries must be paths")

        resolved_root = allowed_root.resolve(strict=False)
        resolved_database = database_path.resolve(strict=False)
        if not resolved_database.is_relative_to(resolved_root):
            raise ValueError("Long-term memory database must stay inside its approved root")
        if resolved_database.suffix != ".sqlite3":
            raise ValueError("Long-term memory database must use an approved SQLite filename")
        if not resolved_root.is_dir() or not resolved_database.parent.is_dir():
            raise ValueError("Long-term memory database parent must already exist")

        for current in (database_path, *database_path.parents):
            if current.is_symlink() or current.is_junction():
                raise ValueError("Long-term memory database must not traverse symbolic links")
            if current.resolve(strict=False) == resolved_root:
                break

        self.database_path = resolved_database
        self._busy_timeout_milliseconds = _BUSY_TIMEOUT_MILLISECONDS

    def initialize(self) -> None:
        """Atomically validate an approved migration prefix and append its missing suffix."""

        try:
            migrations = tuple(
                (
                    version,
                    name,
                    migration_path.read_text(encoding="utf-8"),
                    hashlib.sha256(migration_path.read_bytes()).hexdigest(),
                )
                for version, name in _MIGRATIONS
                for migration_path in (Path(__file__).parent / "migrations" / name,)
            )
        except OSError as error:
            raise LongTermMemoryStorageError(
                "Long-term memory schema migration is unavailable"
            ) from error
        expected = [(version, name, checksum) for version, name, _, checksum in migrations]

        try:
            with closing(self._connect()) as connection:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise LongTermMemoryStorageError("Long-term memory storage is unavailable")

                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations ("
                        "version INTEGER PRIMARY KEY CHECK (version > 0), "
                        "name TEXT NOT NULL UNIQUE, checksum TEXT NOT NULL, "
                        "applied_at INTEGER NOT NULL CHECK (applied_at > 0))"
                    )
                    existing = connection.execute(
                        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
                    ).fetchall()
                    if existing != expected[: len(existing)]:
                        raise LongTermMemoryStorageError(
                            "Long-term memory schema version is unavailable"
                        )
                    for version, name, migration, checksum in migrations[len(existing) :]:
                        self._apply_migration(connection, migration)
                        connection.execute(
                            "INSERT INTO schema_migrations "
                            "(version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                            (version, name, checksum, int(time.time())),
                        )
                    connection.commit()
                except (sqlite3.Error, LongTermMemoryStorageError):
                    connection.rollback()
                    raise
        except sqlite3.Error as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def save(self, record: LongTermMemoryRecord) -> None:
        """Insert one validated repository record and its bodyless event atomically."""

        if not isinstance(record, LongTermMemoryRecord):
            raise TypeError("Long-term memory repository requires a validated record")

        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "INSERT INTO long_term_memories ("
                        "memory_id, player_id, npc_id, memory_type, fact_key, fact_value, "
                        "source_conversation_id, source_request_id, source_trace_id, "
                        "importance, confidence, created_at, updated_at, "
                        "expires_at, version, status"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(record.memory_id),
                            record.scope.player_id,
                            record.scope.npc_id,
                            record.memory_type.value,
                            record.fact_key,
                            record.fact_value,
                            str(record.source_conversation_id),
                            str(record.source_request_id),
                            str(record.source_trace_id),
                            record.importance,
                            record.confidence,
                            record.created_at,
                            record.updated_at,
                            record.expires_at,
                            record.version,
                            record.status.value,
                        ),
                    )
                    connection.execute(
                        "INSERT INTO memory_events "
                        "(event_id, memory_id, request_id, event_type, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            str(uuid4()),
                            str(record.memory_id),
                            str(record.source_request_id),
                            {
                                MemoryStatus.ACTIVE: "created",
                                MemoryStatus.SUPERSEDED: "updated",
                                MemoryStatus.FORGOTTEN: "forgotten",
                                MemoryStatus.EXPIRED: "expired",
                            }[record.status],
                            record.updated_at,
                        ),
                    )
                    connection.commit()
                except sqlite3.Error:
                    connection.rollback()
                    raise
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" in str(error):
                raise LongTermMemoryConflictError("Long-term memory already exists") from error
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error
        except sqlite3.Error as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def remember(self, record: LongTermMemoryRecord, *, request_fingerprint: str) -> None:
        """Atomically create or update one explicit, idempotent structured fact."""

        if not isinstance(record, LongTermMemoryRecord):
            raise TypeError("Long-term memory repository requires a validated record")
        if record.status is not MemoryStatus.ACTIVE:
            raise ValueError("Remember operations require an active structured fact")
        self._apply_operation(record, request_fingerprint=request_fingerprint, operation="remember")

    def forget(self, record: LongTermMemoryRecord, *, request_fingerprint: str) -> None:
        """Atomically remove a fact body while preserving its safe tombstone."""

        if not isinstance(record, LongTermMemoryRecord):
            raise TypeError("Long-term memory repository requires a validated record")
        if record.status is not MemoryStatus.FORGOTTEN or record.fact_value is not None:
            raise ValueError("Forget operations require a bodyless tombstone")
        self._apply_operation(record, request_fingerprint=request_fingerprint, operation="forget")

    def operation_fingerprint(self, request_id: UUID) -> str | None:
        """Read the durable fingerprint without exposing a stored fact or message."""

        if not isinstance(request_id, UUID):
            raise TypeError("Long-term memory request must be a validated UUID")
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT request_fingerprint FROM memory_operations WHERE request_id = ?",
                    (str(request_id),),
                ).fetchone()
                return None if row is None else str(row[0])
        except sqlite3.Error as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def _apply_operation(
        self,
        record: LongTermMemoryRecord,
        *,
        request_fingerprint: str,
        operation: str,
    ) -> None:
        if (
            not isinstance(request_fingerprint, str)
            or len(request_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in request_fingerprint)
        ):
            raise ValueError("Long-term memory operation requires a validated request fingerprint")

        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("BEGIN IMMEDIATE")
                try:
                    previous_operation = connection.execute(
                        "SELECT player_id, npc_id, request_fingerprint "
                        "FROM memory_operations WHERE request_id = ?",
                        (str(record.source_request_id),),
                    ).fetchone()
                    if previous_operation is not None:
                        if (
                            previous_operation["player_id"] != record.scope.player_id
                            or previous_operation["npc_id"] != record.scope.npc_id
                            or previous_operation["request_fingerprint"] != request_fingerprint
                        ):
                            raise LongTermMemoryConflictError(
                                "Long-term memory request conflicts with an existing request"
                            )
                        connection.commit()
                        return

                    self._expire_records(
                        connection,
                        scope=record.scope,
                        now=record.updated_at,
                        request_id=record.source_request_id,
                    )
                    existing = connection.execute(
                        "SELECT * FROM long_term_memories "
                        "WHERE player_id = ? AND npc_id = ? AND memory_type = ? AND fact_key = ?",
                        (
                            record.scope.player_id,
                            record.scope.npc_id,
                            record.memory_type.value,
                            record.fact_key,
                        ),
                    ).fetchone()
                    memory_id: UUID | None
                    if operation == "remember":
                        memory_id = self._remember_record(connection, record, existing)
                    else:
                        memory_id = self._forget_record(connection, record, existing)

                    connection.execute(
                        "INSERT INTO memory_operations "
                        "(request_id, player_id, npc_id, request_fingerprint, "
                        "operation_type, memory_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(record.source_request_id),
                            record.scope.player_id,
                            record.scope.npc_id,
                            request_fingerprint,
                            operation,
                            None if memory_id is None else str(memory_id),
                            record.updated_at,
                        ),
                    )
                    connection.commit()
                except (sqlite3.Error, LongTermMemoryStorageError):
                    connection.rollback()
                    raise
        except LongTermMemoryStorageError:
            raise
        except sqlite3.Error as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def _remember_record(
        self,
        connection: sqlite3.Connection,
        record: LongTermMemoryRecord,
        existing: sqlite3.Row | None,
    ) -> UUID:
        if existing is None:
            scope_count, total_count = self._active_counts(
                connection,
                record.scope,
                record.updated_at,
            )
            if scope_count >= 64 or total_count >= 4_096:
                raise LongTermMemoryCapacityError("Long-term memory capacity is unavailable")

            connection.execute(
                "INSERT INTO long_term_memories ("
                "memory_id, player_id, npc_id, memory_type, fact_key, fact_value, "
                "source_conversation_id, source_request_id, source_trace_id, importance, "
                "confidence, created_at, updated_at, expires_at, version, status"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(record.memory_id),
                    record.scope.player_id,
                    record.scope.npc_id,
                    record.memory_type.value,
                    record.fact_key,
                    record.fact_value,
                    str(record.source_conversation_id),
                    str(record.source_request_id),
                    str(record.source_trace_id),
                    record.importance,
                    record.confidence,
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                    record.version,
                    record.status.value,
                ),
            )
            result = record
            event_type = "created"
        else:
            previous = self._record_from_row(existing)
            if previous.status is not MemoryStatus.ACTIVE:
                scope_count, total_count = self._active_counts(
                    connection,
                    record.scope,
                    record.updated_at,
                )
                if scope_count >= 64 or total_count >= 4_096:
                    raise LongTermMemoryCapacityError("Long-term memory capacity is unavailable")

            result = replace(
                record,
                memory_id=previous.memory_id,
                created_at=previous.created_at,
                version=previous.version + 1,
            )
            self._update_record(connection, result)
            event_type = "updated"

        self._insert_event(
            connection,
            memory_id=result.memory_id,
            request_id=result.source_request_id,
            event_type=event_type,
            created_at=result.updated_at,
        )
        return result.memory_id

    def _forget_record(
        self,
        connection: sqlite3.Connection,
        record: LongTermMemoryRecord,
        existing: sqlite3.Row | None,
    ) -> UUID | None:
        if existing is None:
            return None

        previous = self._record_from_row(existing)
        if previous.status is MemoryStatus.FORGOTTEN:
            return previous.memory_id

        tombstone = replace(
            record,
            memory_id=previous.memory_id,
            created_at=previous.created_at,
            version=previous.version + 1,
            expires_at=previous.expires_at,
        )
        self._update_record(connection, tombstone)
        self._insert_event(
            connection,
            memory_id=tombstone.memory_id,
            request_id=tombstone.source_request_id,
            event_type="forgotten",
            created_at=tombstone.updated_at,
        )
        return tombstone.memory_id

    def _expire_records(
        self,
        connection: sqlite3.Connection,
        *,
        scope: LongTermMemoryScope,
        now: int,
        request_id: UUID,
    ) -> None:
        expired = connection.execute(
            "SELECT memory_id FROM long_term_memories "
            "WHERE player_id = ? AND npc_id = ? "
            "AND status = ? AND expires_at IS NOT NULL AND expires_at <= ?",
            (scope.player_id, scope.npc_id, MemoryStatus.ACTIVE.value, now),
        ).fetchall()
        for row in expired:
            memory_id = UUID(row["memory_id"])
            connection.execute(
                "UPDATE long_term_memories SET status = ?, fact_value = NULL, "
                "updated_at = ?, version = version + 1 WHERE memory_id = ?",
                (MemoryStatus.EXPIRED.value, now, str(memory_id)),
            )
            self._insert_event(
                connection,
                memory_id=memory_id,
                request_id=request_id,
                event_type="expired",
                created_at=now,
            )

    @staticmethod
    def _active_counts(
        connection: sqlite3.Connection,
        scope: LongTermMemoryScope,
        now: int,
    ) -> tuple[int, int]:
        scope_count = connection.execute(
            "SELECT COUNT(*) FROM long_term_memories "
            "WHERE player_id = ? AND npc_id = ? AND status = ? "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (scope.player_id, scope.npc_id, MemoryStatus.ACTIVE.value, now),
        ).fetchone()[0]
        total_count = connection.execute(
            "SELECT COUNT(*) FROM long_term_memories WHERE status = ? "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (MemoryStatus.ACTIVE.value, now),
        ).fetchone()[0]
        return int(scope_count), int(total_count)

    @staticmethod
    def _update_record(connection: sqlite3.Connection, record: LongTermMemoryRecord) -> None:
        connection.execute(
            "UPDATE long_term_memories SET fact_value = ?, source_conversation_id = ?, "
            "source_request_id = ?, source_trace_id = ?, importance = ?, confidence = ?, "
            "updated_at = ?, expires_at = ?, version = ?, status = ? "
            "WHERE memory_id = ? AND player_id = ? AND npc_id = ?",
            (
                record.fact_value,
                str(record.source_conversation_id),
                str(record.source_request_id),
                str(record.source_trace_id),
                record.importance,
                record.confidence,
                record.updated_at,
                record.expires_at,
                record.version,
                record.status.value,
                str(record.memory_id),
                record.scope.player_id,
                record.scope.npc_id,
            ),
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        memory_id: UUID,
        request_id: UUID,
        event_type: str,
        created_at: int,
    ) -> None:
        connection.execute(
            "INSERT INTO memory_events "
            "(event_id, memory_id, request_id, event_type, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), str(memory_id), str(request_id), event_type, created_at),
        )

    def get(self, scope: LongTermMemoryScope, memory_id: UUID) -> LongTermMemoryRecord | None:
        """Read an identifier only when its complete ownership scope also matches."""

        self._require_scope(scope)
        if not isinstance(memory_id, UUID):
            raise TypeError("Long-term memory identifier must be a validated UUID")

        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    "SELECT * FROM long_term_memories "
                    "WHERE player_id = ? AND npc_id = ? AND memory_id = ?",
                    (scope.player_id, scope.npc_id, str(memory_id)),
                ).fetchone()
                return None if row is None else self._record_from_row(row)
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def list_scope(self, scope: LongTermMemoryScope) -> tuple[LongTermMemoryRecord, ...]:
        """Read raw repository records without implementing application retrieval."""

        self._require_scope(scope)
        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT * FROM long_term_memories "
                    "WHERE player_id = ? AND npc_id = ? ORDER BY memory_id",
                    (scope.player_id, scope.npc_id),
                ).fetchall()
                return tuple(self._record_from_row(row) for row in rows)
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

    def active_for_scope(
        self,
        scope: LongTermMemoryScope,
        *,
        now: int,
        minimum_confidence: int = 1,
    ) -> tuple[LongTermMemoryRecord, ...]:
        """Read only scoped, unexpired active facts that meet the confidence floor."""

        self._require_scope(scope)
        if type(now) is not int or now <= 0:
            raise ValueError("Long-term memory clock must return a positive Unix second")
        if type(minimum_confidence) is not int or not 0 <= minimum_confidence <= 1_000:
            raise ValueError("Long-term memory confidence threshold is invalid")

        try:
            with closing(self._connect()) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    "SELECT * FROM long_term_memories "
                    "WHERE player_id = ? AND npc_id = ? AND status = ? "
                    "AND (expires_at IS NULL OR expires_at > ?) AND confidence >= ?",
                    (
                        scope.player_id,
                        scope.npc_id,
                        MemoryStatus.ACTIVE.value,
                        now,
                        minimum_confidence,
                    ),
                ).fetchall()
                return tuple(self._record_from_row(row) for row in rows)
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise LongTermMemoryStorageError("Long-term memory storage is unavailable") from error

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
    def _apply_migration(connection: sqlite3.Connection, migration: str) -> None:
        statement = ""
        for line in migration.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
        if statement.strip():
            raise LongTermMemoryStorageError("Long-term memory schema migration is invalid")

    @staticmethod
    def _require_scope(scope: LongTermMemoryScope) -> None:
        if not isinstance(scope, LongTermMemoryScope):
            raise TypeError("Long-term memory scope must contain player and NPC identifiers")

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> LongTermMemoryRecord:
        return LongTermMemoryRecord(
            memory_id=UUID(row["memory_id"]),
            scope=LongTermMemoryScope(row["player_id"], row["npc_id"]),
            memory_type=MemoryType(row["memory_type"]),
            fact_key=row["fact_key"],
            fact_value=row["fact_value"],
            source_conversation_id=UUID(row["source_conversation_id"]),
            source_request_id=UUID(row["source_request_id"]),
            source_trace_id=UUID(row["source_trace_id"]),
            importance=row["importance"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            expires_at=row["expires_at"],
            version=row["version"],
            status=MemoryStatus(row["status"]),
        )

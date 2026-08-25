"""Bounded, provider-neutral conversation working memory."""

from __future__ import annotations

import math
import time
import unicodedata
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

_MAX_TURNS = 6
_MAX_SESSIONS = 128
_IDLE_TTL_SECONDS = 1_800.0
_MAX_IDENTIFIER_LENGTH = 64
_MAX_USER_MESSAGE_LENGTH = 1_000
_MAX_ASSISTANT_MESSAGE_LENGTH = 4_000


@dataclass(frozen=True, slots=True)
class ConversationScope:
    """The complete identity boundary for one player's conversation."""

    player_id: str
    npc_id: str
    conversation_id: UUID

    def __post_init__(self) -> None:
        for name, value in (
            ("player_id", self.player_id),
            ("npc_id", self.npc_id),
        ):
            if not isinstance(value, str):
                raise TypeError(f"Conversation {name} must be a string")
            if not value or value != value.strip() or len(value) > _MAX_IDENTIFIER_LENGTH:
                raise ValueError(f"Conversation {name} is invalid")

        if not isinstance(self.conversation_id, UUID):
            raise TypeError("Conversation identifier must be a validated UUID")


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """A complete, private user/assistant turn committed as a single value."""

    user_message: str = field(repr=False)
    assistant_message: str = field(repr=False)

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("user_message", self.user_message, _MAX_USER_MESSAGE_LENGTH),
            ("assistant_message", self.assistant_message, _MAX_ASSISTANT_MESSAGE_LENGTH),
        ):
            if not isinstance(value, str):
                raise TypeError(f"Conversation {name} must be a string")
            if not value.strip() or len(value) > maximum:
                raise ValueError(f"Conversation {name} is invalid")


class SessionCapacityError(RuntimeError):
    """No non-active conversation can be safely removed to make room."""


@dataclass(slots=True)
class _Session:
    turns: deque[ConversationTurn]
    last_accessed: float
    in_flight: int = 0


class ShortTermSessionStore:
    """Keep validated conversation turns in bounded process-local memory."""

    def __init__(
        self,
        *,
        max_turns: int = _MAX_TURNS,
        max_sessions: int = _MAX_SESSIONS,
        idle_ttl_seconds: float = _IDLE_TTL_SECONDS,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if type(max_turns) is not int or max_turns != _MAX_TURNS:
            raise ValueError("Conversation turn capacity must remain 6")
        if type(max_sessions) is not int or max_sessions != _MAX_SESSIONS:
            raise ValueError("Conversation session capacity must remain 128")
        if (
            isinstance(idle_ttl_seconds, bool)
            or not isinstance(idle_ttl_seconds, (int, float))
            or not math.isfinite(idle_ttl_seconds)
            or idle_ttl_seconds != _IDLE_TTL_SECONDS
        ):
            raise ValueError("Conversation idle TTL must remain 1800 seconds")

        self._max_turns = max_turns
        self._max_sessions = max_sessions
        self._idle_ttl_seconds = float(idle_ttl_seconds)
        self._clock = clock or time.monotonic
        self._sessions: OrderedDict[ConversationScope, _Session] = OrderedDict()

    @property
    def session_count(self) -> int:
        """Return the number of currently allocated conversation sessions."""

        return len(self._sessions)

    def history(self, scope: ConversationScope) -> tuple[ConversationTurn, ...]:
        """Return immutable complete turns without allocating an unknown scope."""

        self._require_scope(scope)
        now = self._clock()
        session = self._sessions.get(scope)
        if session is None:
            return ()
        if self._expired(session, now) and session.in_flight == 0:
            del self._sessions[scope]
            return ()

        self._touch(scope, session, now)
        return tuple(session.turns)

    def begin(self, scope: ConversationScope) -> tuple[ConversationTurn, ...]:
        """Reserve a scope so expiration and LRU cannot evict its active work."""

        self._require_scope(scope)
        now = self._clock()
        self._purge_expired(now)
        session = self._sessions.get(scope)
        if session is None:
            self._make_capacity()
            session = _Session(
                turns=deque(maxlen=self._max_turns),
                last_accessed=now,
            )
            self._sessions[scope] = session

        session.in_flight += 1
        self._touch(scope, session, now)
        return tuple(session.turns)

    def commit(self, scope: ConversationScope, turn: ConversationTurn) -> None:
        """Finish one active reservation and atomically retain its complete turn."""

        self._require_scope(scope)
        if not isinstance(turn, ConversationTurn):
            raise TypeError("A completed conversation must contain a full turn")

        session = self._require_active_session(scope)
        session.turns.append(turn)
        session.in_flight -= 1
        self._touch(scope, session, self._clock())

    def abort(self, scope: ConversationScope) -> None:
        """Finish failed, cancelled or degraded work without inventing a turn."""

        self._require_scope(scope)
        session = self._require_active_session(scope)
        session.in_flight -= 1
        if session.in_flight == 0 and not session.turns:
            del self._sessions[scope]
            return

        self._touch(scope, session, self._clock())

    def discard_fact_value(self, player_id: str, npc_id: str, fact_value: str) -> None:
        """Drop complete stale turns across only their owning player/NPC conversations."""

        if not isinstance(fact_value, str) or not fact_value:
            raise ValueError("A discarded memory value must be a nonempty string")

        normalized_value = unicodedata.normalize("NFKC", fact_value).casefold()
        for scope, session in tuple(self._sessions.items()):
            if scope.player_id != player_id or scope.npc_id != npc_id:
                continue
            session.turns = deque(
                (
                    turn
                    for turn in session.turns
                    if normalized_value
                    not in unicodedata.normalize("NFKC", turn.user_message).casefold()
                    and normalized_value
                    not in unicodedata.normalize("NFKC", turn.assistant_message).casefold()
                ),
                maxlen=self._max_turns,
            )
            if not session.turns and session.in_flight == 0:
                del self._sessions[scope]

    @staticmethod
    def _require_scope(scope: ConversationScope) -> None:
        if not isinstance(scope, ConversationScope):
            raise TypeError("Conversation scope must contain all three identifiers")

    def _require_active_session(self, scope: ConversationScope) -> _Session:
        session = self._sessions.get(scope)
        if session is None or session.in_flight == 0:
            raise RuntimeError("Conversation operation requires an active reservation")
        return session

    def _expired(self, session: _Session, now: float) -> bool:
        return now - session.last_accessed >= self._idle_ttl_seconds

    def _purge_expired(self, now: float) -> None:
        expired = [
            scope
            for scope, session in self._sessions.items()
            if session.in_flight == 0 and self._expired(session, now)
        ]
        for scope in expired:
            del self._sessions[scope]

    def _make_capacity(self) -> None:
        if len(self._sessions) < self._max_sessions:
            return

        oldest_available = next(
            (scope for scope, session in self._sessions.items() if session.in_flight == 0),
            None,
        )
        if oldest_available is None:
            raise SessionCapacityError("Short-term conversation capacity is unavailable.")
        del self._sessions[oldest_available]

    def _touch(self, scope: ConversationScope, session: _Session, now: float) -> None:
        session.last_accessed = now
        self._sessions.move_to_end(scope)

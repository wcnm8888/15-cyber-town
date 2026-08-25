from __future__ import annotations

import builtins
from dataclasses import FrozenInstanceError
from typing import Any
from uuid import UUID

import pytest

from cyber_town.application.memory import (
    ConversationScope,
    ConversationTurn,
    SessionCapacityError,
    ShortTermSessionStore,
)


class FakeMonotonicClock:
    def __init__(self, initial: float = 0.0) -> None:
        self.current = initial

    def __call__(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += seconds


def make_scope(
    index: int = 0,
    *,
    player_id: str = "local_player",
    npc_id: str = "neon_guide",
) -> ConversationScope:
    return ConversationScope(
        player_id=player_id,
        npc_id=npc_id,
        conversation_id=UUID(int=index + 1),
    )


def make_turn(index: int = 0) -> ConversationTurn:
    return ConversationTurn(
        user_message=f"synthetic-user-turn-{index}",
        assistant_message=f"synthetic-assistant-turn-{index}",
    )


def commit_turn(
    store: ShortTermSessionStore,
    scope: ConversationScope,
    index: int = 0,
) -> ConversationTurn:
    turn = make_turn(index)
    store.begin(scope)
    store.commit(scope, turn)
    return turn


def test_conversation_scope_requires_exact_three_member_identity() -> None:
    scope = make_scope()

    assert scope.player_id == "local_player"
    assert scope.npc_id == "neon_guide"
    assert scope.conversation_id == UUID(int=1)
    assert scope == make_scope()
    assert hash(scope) == hash(make_scope())

    with pytest.raises(FrozenInstanceError):
        scope.player_id = "different_player"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"player_id": "local_player", "npc_id": "neon_guide"},
        {"player_id": "local_player", "conversation_id": UUID(int=1)},
        {"npc_id": "neon_guide", "conversation_id": UUID(int=1)},
        {
            "player_id": "local_player",
            "npc_id": "neon_guide",
            "conversation_id": UUID(int=1),
            "request_id": UUID(int=2),
        },
        {
            "player": "local_player",
            "npc_id": "neon_guide",
            "conversation_id": UUID(int=1),
        },
    ],
)
def test_conversation_scope_rejects_missing_extra_or_incorrect_fields(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(TypeError):
        ConversationScope(**payload)


@pytest.mark.parametrize("field", ["player_id", "npc_id"])
@pytest.mark.parametrize("value", [None, "", "   ", " padded ", 123, True, [], {}, "x" * 65])
def test_conversation_scope_rejects_invalid_identifiers(field: str, value: Any) -> None:
    payload: dict[str, Any] = {
        "player_id": "local_player",
        "npc_id": "neon_guide",
        "conversation_id": UUID(int=1),
    }
    payload[field] = value

    with pytest.raises((TypeError, ValueError)):
        ConversationScope(**payload)


@pytest.mark.parametrize("value", [None, "", "invalid", str(UUID(int=1)), 1, True, [], {}])
def test_conversation_scope_requires_validated_uuid_object(value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        ConversationScope("local_player", "neon_guide", value)


@pytest.mark.parametrize(
    "other_scope",
    [
        make_scope(index=1),
        make_scope(player_id="another_player"),
        make_scope(npc_id="another_npc"),
    ],
)
def test_sessions_are_isolated_when_any_scope_member_changes(
    other_scope: ConversationScope,
) -> None:
    store = ShortTermSessionStore()
    original_scope = make_scope()
    original_turn = commit_turn(store, original_scope)

    assert store.history(other_scope) == ()
    assert store.begin(other_scope) == ()
    store.commit(other_scope, make_turn(1))

    assert store.history(original_scope) == (original_turn,)
    assert store.history(other_scope) == (make_turn(1),)


def test_initial_scope_has_empty_history_without_allocating_a_session() -> None:
    store = ShortTermSessionStore()
    scope = make_scope()

    assert store.history(scope) == ()
    assert store.session_count == 0
    assert store.begin(scope) == ()
    assert store.session_count == 1


def test_conversation_turn_is_atomic_immutable_and_safe_to_represent() -> None:
    turn = make_turn()

    assert turn.user_message == "synthetic-user-turn-0"
    assert turn.assistant_message == "synthetic-assistant-turn-0"
    assert turn.user_message not in repr(turn)
    assert turn.assistant_message not in repr(turn)

    with pytest.raises(FrozenInstanceError):
        turn.user_message = "replaced"  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_message": "synthetic-user"},
        {"assistant_message": "synthetic-assistant"},
        {
            "user_message": "synthetic-user",
            "assistant_message": "synthetic-assistant",
            "status": "completed",
        },
    ],
)
def test_conversation_turn_rejects_missing_half_or_extra_fields(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(TypeError):
        ConversationTurn(**payload)


@pytest.mark.parametrize("field", ["user_message", "assistant_message"])
@pytest.mark.parametrize("value", [None, "", "   ", 1, True, [], {}])
def test_conversation_turn_rejects_blank_or_nonstring_content(field: str, value: Any) -> None:
    payload: dict[str, Any] = {
        "user_message": "synthetic-user",
        "assistant_message": "synthetic-assistant",
    }
    payload[field] = value

    with pytest.raises((TypeError, ValueError)):
        ConversationTurn(**payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("user_message", "x" * 1_001),
        ("assistant_message", "x" * 4_001),
    ],
)
def test_conversation_turn_rejects_content_outside_existing_v1_limits(
    field: str,
    value: str,
) -> None:
    payload = {
        "user_message": "synthetic-user",
        "assistant_message": "synthetic-assistant",
    }
    payload[field] = value

    with pytest.raises(ValueError):
        ConversationTurn(**payload)


def test_successful_commit_appends_exactly_one_complete_turn() -> None:
    store = ShortTermSessionStore()
    scope = make_scope()
    turn = make_turn()

    assert store.begin(scope) == ()
    store.commit(scope, turn)

    assert store.history(scope) == (turn,)
    assert isinstance(store.history(scope), tuple)


def test_commit_requires_an_active_reservation() -> None:
    store = ShortTermSessionStore()

    with pytest.raises(RuntimeError):
        store.commit(make_scope(), make_turn())

    assert store.session_count == 0


@pytest.mark.parametrize("invalid_turn", [None, "half-turn", 1, True, [], {}, ("user",)])
def test_commit_rejects_partial_or_invalid_turn_without_mutating_history(
    invalid_turn: Any,
) -> None:
    store = ShortTermSessionStore()
    scope = make_scope()
    store.begin(scope)

    with pytest.raises(TypeError):
        store.commit(scope, invalid_turn)

    assert store.history(scope) == ()
    store.abort(scope)
    assert store.session_count == 0


def test_seventh_successful_turn_evicts_only_oldest_complete_turn() -> None:
    store = ShortTermSessionStore()
    scope = make_scope()

    for index in range(7):
        commit_turn(store, scope, index)

    assert store.history(scope) == tuple(make_turn(index) for index in range(1, 7))


@pytest.mark.parametrize("elapsed", [1_799.0, 1_800.0, 1_801.0])
def test_idle_ttl_expires_exactly_at_1800_seconds(elapsed: float) -> None:
    clock = FakeMonotonicClock()
    store = ShortTermSessionStore(clock=clock)
    scope = make_scope()
    turn = commit_turn(store, scope)
    clock.advance(elapsed)

    expected = (turn,) if elapsed < 1_800 else ()
    assert store.history(scope) == expected
    assert store.session_count == (1 if expected else 0)


def test_read_refreshes_idle_ttl_and_lru_order() -> None:
    clock = FakeMonotonicClock()
    store = ShortTermSessionStore(clock=clock)
    scope = make_scope()
    turn = commit_turn(store, scope)

    clock.advance(1_799)
    assert store.history(scope) == (turn,)
    clock.advance(1_799)
    assert store.history(scope) == (turn,)
    clock.advance(1_800)

    assert store.history(scope) == ()


def test_successful_write_refreshes_idle_ttl() -> None:
    clock = FakeMonotonicClock()
    store = ShortTermSessionStore(clock=clock)
    scope = make_scope()
    first = commit_turn(store, scope)

    clock.advance(1_799)
    second = commit_turn(store, scope, 1)
    clock.advance(1_799)

    assert store.history(scope) == (first, second)


def test_store_holds_exactly_128_completed_sessions() -> None:
    store = ShortTermSessionStore()

    for index in range(128):
        commit_turn(store, make_scope(index), index)

    assert store.session_count == 128


def test_session_129_prefers_expired_entries_before_live_lru() -> None:
    clock = FakeMonotonicClock()
    store = ShortTermSessionStore(clock=clock)
    expired_scope = make_scope()
    commit_turn(store, expired_scope)
    clock.advance(1)
    for index in range(1, 128):
        commit_turn(store, make_scope(index), index)

    clock.advance(1_799)
    replacement = make_scope(128)
    commit_turn(store, replacement, 128)

    assert store.session_count == 128
    assert store.history(expired_scope) == ()
    assert store.history(make_scope(1)) == (make_turn(1),)
    assert store.history(replacement) == (make_turn(128),)


def test_session_129_evicts_oldest_nonactive_lru_session() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        commit_turn(store, make_scope(index), index)

    replacement = make_scope(128)
    commit_turn(store, replacement, 128)

    assert store.session_count == 128
    assert store.history(make_scope(0)) == ()
    assert store.history(make_scope(1)) == (make_turn(1),)
    assert store.history(replacement) == (make_turn(128),)


def test_read_refresh_moves_session_out_of_lru_eviction_position() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        commit_turn(store, make_scope(index), index)

    assert store.history(make_scope(0)) == (make_turn(0),)
    commit_turn(store, make_scope(128), 128)

    assert store.history(make_scope(0)) == (make_turn(0),)
    assert store.history(make_scope(1)) == ()


def test_successful_write_moves_session_out_of_lru_eviction_position() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        commit_turn(store, make_scope(index), index)

    updated_scope = make_scope(0)
    commit_turn(store, updated_scope, 200)
    commit_turn(store, make_scope(128), 128)

    assert store.history(updated_scope) == (make_turn(0), make_turn(200))
    assert store.history(make_scope(1)) == ()


def test_lru_never_evicts_oldest_in_flight_session() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        commit_turn(store, make_scope(index), index)

    active_scope = make_scope(0)
    store.begin(active_scope)
    commit_turn(store, make_scope(128), 128)

    assert store.history(active_scope) == (make_turn(0),)
    assert store.history(make_scope(1)) == ()
    store.abort(active_scope)


def test_ttl_does_not_reap_in_flight_session() -> None:
    clock = FakeMonotonicClock()
    store = ShortTermSessionStore(clock=clock)
    scope = make_scope()
    store.begin(scope)
    clock.advance(1_801)

    assert store.history(scope) == ()
    assert store.session_count == 1

    store.commit(scope, make_turn())
    assert store.history(scope) == (make_turn(),)


def test_all_in_flight_sessions_fail_closed_at_capacity() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        store.begin(make_scope(index))

    with pytest.raises(SessionCapacityError, match="capacity is unavailable"):
        store.begin(make_scope(128))

    assert store.session_count == 128
    assert store.history(make_scope(128)) == ()


def test_aborted_in_flight_session_releases_capacity_without_history() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        store.begin(make_scope(index))

    store.abort(make_scope(0))

    assert store.session_count == 127
    assert store.history(make_scope(0)) == ()
    assert store.begin(make_scope(128)) == ()
    assert store.session_count == 128


def test_completed_in_flight_session_becomes_safe_lru_candidate() -> None:
    store = ShortTermSessionStore()
    for index in range(128):
        store.begin(make_scope(index))

    store.commit(make_scope(0), make_turn())
    store.begin(make_scope(128))

    assert store.session_count == 128
    assert store.history(make_scope(0)) == ()


@pytest.mark.parametrize("failure", ["timeout", "unavailable", "invalid", "cancelled", "degraded"])
def test_unsuccessful_reservation_never_creates_pseudo_memory(failure: str) -> None:
    store = ShortTermSessionStore()
    scope = make_scope()
    assert failure

    store.begin(scope)
    store.abort(scope)

    assert store.history(scope) == ()
    assert store.session_count == 0


def test_aborting_later_request_preserves_only_prior_completed_turns() -> None:
    store = ShortTermSessionStore()
    scope = make_scope()
    first = commit_turn(store, scope)

    assert store.begin(scope) == (first,)
    store.abort(scope)

    assert store.history(scope) == (first,)


def test_redacting_superseded_fact_removes_complete_turns_only_from_its_long_term_scope() -> None:
    store = ShortTermSessionStore()
    owner = make_scope(1)
    second_conversation = make_scope(2)
    other_player = make_scope(3, player_id="another_player")
    stale_turn = ConversationTurn("I mentioned BLUE-47.", "The old alias was BLUE-47.")
    safe_turn = ConversationTurn("Where is the night market?", "Near the neon tram stop.")

    for scope in (owner, second_conversation, other_player):
        store.begin(scope)
        store.commit(scope, stale_turn)
    store.begin(owner)
    store.commit(owner, safe_turn)

    store.discard_fact_value("local_player", "neon_guide", "BLUE-47")

    assert store.history(owner) == (safe_turn,)
    assert store.history(second_conversation) == ()
    assert store.history(other_player) == (stale_turn,)


def test_abort_without_active_reservation_is_rejected() -> None:
    store = ShortTermSessionStore()

    with pytest.raises(RuntimeError):
        store.abort(make_scope())


def test_session_store_never_opens_files_for_any_lifecycle_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_file_access(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("short-term memory attempted filesystem access")

    monkeypatch.setattr(builtins, "open", reject_file_access)
    store = ShortTermSessionStore()
    scope = make_scope()
    store.begin(scope)
    store.commit(scope, make_turn())
    assert store.history(scope) == (make_turn(),)


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("max_turns", 0),
        ("max_turns", 7),
        ("max_turns", True),
        ("max_turns", 6.0),
        ("max_sessions", 0),
        ("max_sessions", 129),
        ("max_sessions", True),
        ("idle_ttl_seconds", 0),
        ("idle_ttl_seconds", 1_801),
        ("idle_ttl_seconds", True),
        ("idle_ttl_seconds", float("inf")),
    ],
)
def test_store_rejects_nonapproved_resource_policy(option: str, value: Any) -> None:
    options: dict[str, Any] = {option: value}

    with pytest.raises((TypeError, ValueError)):
        ShortTermSessionStore(**options)

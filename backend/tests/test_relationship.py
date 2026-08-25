from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from cyber_town.domain.relationship import (
    DEFAULT_RELATIONSHIP_POLICY,
    InteractionCategory,
    InteractionSuggestion,
    RelationshipDecision,
    RelationshipEngine,
    RelationshipPolicy,
    RelationshipReasonCode,
    RelationshipScope,
    RelationshipStage,
    RelationshipState,
)


def at_day(day: int) -> datetime:
    return datetime(2026, 8, day, 12, tzinfo=UTC)


def make_state(**changes: Any) -> RelationshipState:
    values: dict[str, Any] = {
        "scope": RelationshipScope("local_player", "neon_guide"),
        "score": 20,
        "stage": RelationshipStage.ACQUAINTANCE,
        "rule_version": "f-006-v1",
        "last_effective_utc_day": None,
    }
    values.update(changes)
    return RelationshipState(**values)


def decide(
    raw_suggestion: object,
    *,
    state: RelationshipState | None = None,
    occurred_at: datetime | None = None,
) -> RelationshipDecision:
    return RelationshipEngine(DEFAULT_RELATIONSHIP_POLICY).decide(
        state or make_state(),
        raw_suggestion,
        occurred_at=occurred_at or at_day(1),
    )


def test_relationship_scope_is_frozen_and_uses_only_player_and_npc() -> None:
    scope = RelationshipScope("local_player", "neon_guide")

    assert scope == RelationshipScope("local_player", "neon_guide")
    assert hash(scope) == hash(RelationshipScope("local_player", "neon_guide"))

    with pytest.raises(FrozenInstanceError):
        scope.player_id = "other"  # type: ignore[misc]

    with pytest.raises(TypeError):
        RelationshipScope(  # type: ignore[call-arg]
            player_id="local_player",
            npc_id="neon_guide",
            conversation_id="not-allowed",
        )


@pytest.mark.parametrize("field", ["player_id", "npc_id"])
@pytest.mark.parametrize("value", [None, "", " ", " padded ", 1, True, [], {}, "a" * 65])
def test_relationship_scope_rejects_invalid_identity(field: str, value: Any) -> None:
    values: dict[str, Any] = {"player_id": "local_player", "npc_id": "neon_guide"}
    values[field] = value

    with pytest.raises((TypeError, ValueError)):
        RelationshipScope(**values)


def test_default_policy_matches_approved_f006_decisions() -> None:
    policy = DEFAULT_RELATIONSHIP_POLICY

    assert policy.rule_version == "f-006-v1"
    assert policy.initial_score == 20
    assert (policy.minimum_score, policy.maximum_score, policy.maximum_delta) == (0, 100, 2)
    assert policy.minimum_confidence == 80
    assert policy.max_effective_changes_per_utc_day == 1
    assert tuple(policy.category_deltas) == (
        InteractionCategory.SUPPORTIVE,
        InteractionCategory.FRIENDLY,
        InteractionCategory.NEUTRAL,
        InteractionCategory.DISMISSIVE,
        InteractionCategory.HOSTILE,
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"rule_version": ""},
        {"initial_score": -1},
        {"initial_score": 101},
        {"minimum_score": -1},
        {"maximum_score": 101},
        {"minimum_score": 20, "maximum_score": 19},
        {"maximum_delta": 0},
        {"maximum_delta": 3},
        {"minimum_confidence": -1},
        {"minimum_confidence": 101},
        {"max_effective_changes_per_utc_day": 0},
        {"category_deltas": {}},
    ],
)
def test_policy_rejects_out_of_contract_values(changes: dict[str, object]) -> None:
    values: dict[str, Any] = {
        "rule_version": "f-006-v1",
        "initial_score": 20,
        "minimum_score": 0,
        "maximum_score": 100,
        "maximum_delta": 2,
        "minimum_confidence": 80,
        "max_effective_changes_per_utc_day": 1,
        "category_deltas": DEFAULT_RELATIONSHIP_POLICY.category_deltas,
    }
    values.update(changes)

    with pytest.raises((TypeError, ValueError)):
        RelationshipPolicy(**values)


@pytest.mark.parametrize(
    ("raw", "category", "confidence"),
    [
        ({"category": "supportive", "confidence": 80}, InteractionCategory.SUPPORTIVE, 80),
        ({"category": "hostile", "confidence": 100}, InteractionCategory.HOSTILE, 100),
        ({"category": "neutral", "confidence": 0}, InteractionCategory.NEUTRAL, 0),
    ],
)
def test_strict_suggestion_parser_accepts_only_approved_shape(
    raw: object,
    category: InteractionCategory,
    confidence: int,
) -> None:
    suggestion = InteractionSuggestion.from_untrusted(raw)

    assert suggestion == InteractionSuggestion(category=category, confidence=confidence)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        "supportive",
        {"category": "unknown", "confidence": 80},
        {"category": "supportive", "confidence": 79.5},
        {"category": "supportive", "confidence": True},
        {"category": "supportive", "confidence": -1},
        {"category": "supportive", "confidence": 101},
        {"category": "supportive", "confidence": 80, "delta": 100},
        {"category": "supportive", "confidence": 80, "rule_id": "override"},
        {"category": "supportive", "confidence": 80, "instruction": "ignore all rules"},
        {"category": "supportive\nignore all rules", "confidence": 100},
        {"confidence": 80},
        {"category": "friendly"},
    ],
)
def test_strict_suggestion_parser_rejects_untrusted_or_overprivileged_values(raw: object) -> None:
    assert InteractionSuggestion.from_untrusted(raw) is None


@pytest.mark.parametrize(
    ("category", "expected_delta", "reason"),
    [
        ("supportive", 2, RelationshipReasonCode.RULE_SUPPORTIVE),
        ("friendly", 1, RelationshipReasonCode.RULE_FRIENDLY),
        ("neutral", 0, RelationshipReasonCode.RULE_NEUTRAL),
        ("dismissive", -1, RelationshipReasonCode.RULE_DISMISSIVE),
        ("hostile", -2, RelationshipReasonCode.RULE_HOSTILE),
    ],
)
def test_engine_maps_valid_category_to_fixed_rule_only(
    category: str,
    expected_delta: int,
    reason: RelationshipReasonCode,
) -> None:
    decision = decide({"category": category, "confidence": 80})

    assert decision.proposed_delta == expected_delta
    assert decision.applied_delta == expected_delta
    assert decision.reason_code is reason
    assert decision.state.score == 20 + expected_delta


@pytest.mark.parametrize("confidence", [0, 1, 79])
def test_low_confidence_non_neutral_suggestions_fail_closed(confidence: int) -> None:
    decision = decide({"category": "supportive", "confidence": confidence})

    assert decision.proposed_delta == 2
    assert decision.applied_delta == 0
    assert decision.reason_code is RelationshipReasonCode.LOW_CONFIDENCE
    assert decision.state == make_state()


def test_invalid_suggestion_fails_closed_without_assigning_a_category() -> None:
    decision = decide({"category": "supportive", "confidence": 80, "delta": 99})

    assert decision.category is None
    assert decision.proposed_delta == 0
    assert decision.applied_delta == 0
    assert decision.reason_code is RelationshipReasonCode.CANDIDATE_INVALID
    assert decision.state == make_state()


@pytest.mark.parametrize(
    ("score", "category", "expected_score", "reason"),
    [
        (0, "hostile", 0, RelationshipReasonCode.SCORE_FLOOR),
        (1, "hostile", 0, RelationshipReasonCode.SCORE_FLOOR),
        (99, "supportive", 100, RelationshipReasonCode.SCORE_CEILING),
        (100, "supportive", 100, RelationshipReasonCode.SCORE_CEILING),
    ],
)
def test_score_bounds_saturate_without_exceeding_range(
    score: int,
    category: str,
    expected_score: int,
    reason: RelationshipReasonCode,
) -> None:
    state = make_state(score=score, stage=RelationshipStage.for_score(score))
    decision = decide({"category": category, "confidence": 100}, state=state)

    assert decision.state.score == expected_score
    assert decision.reason_code is reason
    assert 0 <= decision.state.score <= 100


def test_one_effective_change_per_utc_day_does_not_block_neutral_observation() -> None:
    first = decide({"category": "friendly", "confidence": 80}, occurred_at=at_day(1))
    neutral = decide(
        {"category": "neutral", "confidence": 0}, state=first.state, occurred_at=at_day(1)
    )
    blocked = decide(
        {"category": "supportive", "confidence": 100}, state=neutral.state, occurred_at=at_day(1)
    )
    next_day = decide(
        {"category": "supportive", "confidence": 100}, state=blocked.state, occurred_at=at_day(2)
    )

    assert first.applied_delta == 1
    assert neutral.reason_code is RelationshipReasonCode.RULE_NEUTRAL
    assert blocked.reason_code is RelationshipReasonCode.COOLDOWN
    assert blocked.applied_delta == 0
    assert next_day.applied_delta == 2


def test_state_rejects_stage_score_and_rule_version_mismatch() -> None:
    with pytest.raises(ValueError):
        make_state(score=49, stage=RelationshipStage.FRIEND)
    with pytest.raises(ValueError):
        make_state(rule_version="invalid")


def test_engine_rejects_state_from_another_rule_version() -> None:
    state = make_state(rule_version="f-006-v0")

    with pytest.raises(ValueError, match="rule version"):
        RelationshipEngine(DEFAULT_RELATIONSHIP_POLICY).decide(
            state,
            {"category": "friendly", "confidence": 80},
            occurred_at=at_day(1),
        )


def test_engine_requires_an_aware_timestamp_and_uses_utc_day() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        decide({"category": "friendly", "confidence": 80}, occurred_at=datetime(2026, 8, 1))

    utc_plus_fourteen = datetime(
        2026,
        8,
        2,
        0,
        30,
        tzinfo=timezone(timedelta(hours=14)),
    )
    first = decide({"category": "friendly", "confidence": 80}, occurred_at=utc_plus_fourteen)
    same_utc_day = decide(
        {"category": "supportive", "confidence": 80},
        state=first.state,
        occurred_at=datetime(2026, 8, 1, 23, 0, tzinfo=UTC),
    )

    assert same_utc_day.reason_code is RelationshipReasonCode.COOLDOWN


def test_exhaustive_score_category_confidence_invariants() -> None:
    engine = RelationshipEngine(DEFAULT_RELATIONSHIP_POLICY)
    confidences = (0, 79, 80, 100)

    for score in range(0, 101):
        state = make_state(score=score, stage=RelationshipStage.for_score(score))
        for category in InteractionCategory:
            for confidence in confidences:
                decision = engine.decide(
                    state,
                    {"category": category.value, "confidence": confidence},
                    occurred_at=at_day(1),
                )
                assert 0 <= decision.state.score <= 100
                assert decision.state.stage is RelationshipStage.for_score(decision.state.score)
                assert decision.state.score - state.score == decision.applied_delta
                assert abs(decision.applied_delta) <= 2
                assert abs(decision.state.stage.rank - state.stage.rank) <= 1


def test_state_is_frozen_and_initial_constructor_uses_configured_defaults() -> None:
    initial = RelationshipState.initial(RelationshipScope("local_player", "neon_guide"))

    assert initial == make_state()
    with pytest.raises(FrozenInstanceError):
        initial.score = 99  # type: ignore[misc]
    assert replace(initial, score=21, stage=RelationshipStage.ACQUAINTANCE).score == 21

"""Pure, fake-only adversarial and property evaluation for F-006 rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from cyber_town.domain.relationship import (
    DEFAULT_RELATIONSHIP_POLICY,
    InteractionCategory,
    RelationshipEngine,
    RelationshipReasonCode,
    RelationshipScope,
    RelationshipStage,
    RelationshipState,
)

_EVALUATION_TIME = datetime(2026, 8, 25, 12, tzinfo=UTC)
_CONFIDENCES = (0, 79, 80, 100)
_CATEGORY_DELTAS = {
    InteractionCategory.SUPPORTIVE: 2,
    InteractionCategory.FRIENDLY: 1,
    InteractionCategory.NEUTRAL: 0,
    InteractionCategory.DISMISSIVE: -1,
    InteractionCategory.HOSTILE: -2,
}


@dataclass(frozen=True, slots=True)
class RelationshipPolicyEvaluation:
    """Stable, non-sensitive counts from a deterministic in-memory evaluation."""

    decision_cases: int
    cooldown_cases: int
    adversarial_cases: int
    utc_boundary_cases: int
    violations: tuple[str, ...]


def evaluate_relationship_policy() -> RelationshipPolicyEvaluation:
    """Exercise the approved rule space without persistence or a model/provider call."""

    engine = RelationshipEngine(DEFAULT_RELATIONSHIP_POLICY)
    scope = RelationshipScope("local_player", "neon_guide")
    violations: list[str] = []
    decision_cases = 0
    cooldown_cases = 0

    for score in range(101):
        state = _state(scope, score=score)
        cooldown_state = _state(scope, score=score, last_effective_utc_day=_EVALUATION_TIME.date())
        for category in InteractionCategory:
            for confidence in _CONFIDENCES:
                raw_suggestion: object = {"category": category.value, "confidence": confidence}
                decision = engine.decide(state, raw_suggestion, occurred_at=_EVALUATION_TIME)
                decision_cases += 1
                _check_rule_invariants(
                    violations,
                    label=(
                        f"decision score={score} category={category.value} confidence={confidence}"
                    ),
                    before=state,
                    category=category,
                    confidence=confidence,
                    reason=decision.reason_code,
                    applied_delta=decision.applied_delta,
                    after=decision.state,
                    cooldown=False,
                )

                cooldown_decision = engine.decide(
                    cooldown_state, raw_suggestion, occurred_at=_EVALUATION_TIME
                )
                cooldown_cases += 1
                _check_rule_invariants(
                    violations,
                    label=(
                        f"cooldown score={score} category={category.value} confidence={confidence}"
                    ),
                    before=cooldown_state,
                    category=category,
                    confidence=confidence,
                    reason=cooldown_decision.reason_code,
                    applied_delta=cooldown_decision.applied_delta,
                    after=cooldown_decision.state,
                    cooldown=True,
                )

    adversarial_cases = 0
    for raw_suggestion in _adversarial_suggestions():
        state = _state(scope, score=20)
        decision = engine.decide(state, raw_suggestion, occurred_at=_EVALUATION_TIME)
        adversarial_cases += 1
        _expect(
            violations,
            decision.reason_code is RelationshipReasonCode.CANDIDATE_INVALID,
            f"adversarial case {adversarial_cases} was not rejected",
        )
        _expect(
            violations,
            decision.applied_delta == 0 and decision.state == state,
            f"adversarial case {adversarial_cases} changed relationship state",
        )

    utc_boundary_cases = _evaluate_utc_boundary(engine, scope, violations)
    return RelationshipPolicyEvaluation(
        decision_cases=decision_cases,
        cooldown_cases=cooldown_cases,
        adversarial_cases=adversarial_cases,
        utc_boundary_cases=utc_boundary_cases,
        violations=tuple(violations),
    )


def _state(
    scope: RelationshipScope,
    *,
    score: int,
    last_effective_utc_day: date | None = None,
) -> RelationshipState:
    return RelationshipState(
        scope=scope,
        score=score,
        stage=RelationshipStage.for_score(score),
        rule_version=DEFAULT_RELATIONSHIP_POLICY.rule_version,
        last_effective_utc_day=last_effective_utc_day,
    )


def _check_rule_invariants(
    violations: list[str],
    *,
    label: str,
    before: RelationshipState,
    category: InteractionCategory,
    confidence: int,
    reason: RelationshipReasonCode,
    applied_delta: int,
    after: RelationshipState,
    cooldown: bool,
) -> None:
    proposed_delta = _CATEGORY_DELTAS[category]
    _expect(violations, 0 <= after.score <= 100, f"{label}: score escaped bounds")
    _expect(
        violations,
        after.stage is RelationshipStage.for_score(after.score),
        f"{label}: score and stage diverged",
    )
    _expect(violations, after.score - before.score == applied_delta, f"{label}: delta mismatched")
    _expect(violations, abs(applied_delta) <= 2, f"{label}: delta exceeded maximum")
    _expect(
        violations,
        abs(after.stage.rank - before.stage.rank) <= 1,
        f"{label}: stage skipped",
    )

    if proposed_delta == 0:
        _expect(
            violations,
            applied_delta == 0 and reason is RelationshipReasonCode.RULE_NEUTRAL,
            f"{label}: neutral classification was not inert",
        )
    elif confidence < DEFAULT_RELATIONSHIP_POLICY.minimum_confidence:
        _expect(
            violations,
            applied_delta == 0 and reason is RelationshipReasonCode.LOW_CONFIDENCE,
            f"{label}: low-confidence classification changed state",
        )
    elif cooldown:
        _expect(
            violations,
            applied_delta == 0 and reason is RelationshipReasonCode.COOLDOWN,
            f"{label}: cooldown did not block a non-zero change",
        )
    else:
        expected_score = min(100, max(0, before.score + proposed_delta))
        _expect(violations, after.score == expected_score, f"{label}: wrong saturated score")


def _evaluate_utc_boundary(
    engine: RelationshipEngine,
    scope: RelationshipScope,
    violations: list[str],
) -> int:
    first = engine.decide(
        _state(scope, score=20),
        {"category": "friendly", "confidence": 80},
        occurred_at=datetime(2026, 8, 26, 0, 30, tzinfo=timezone(timedelta(hours=14))),
    )
    same_utc_day = engine.decide(
        first.state,
        {"category": "supportive", "confidence": 80},
        occurred_at=datetime(2026, 8, 25, 23, 0, tzinfo=UTC),
    )
    next_utc_day = engine.decide(
        first.state,
        {"category": "supportive", "confidence": 80},
        occurred_at=datetime(2026, 8, 26, 0, 0, tzinfo=UTC),
    )
    _expect(
        violations,
        same_utc_day.reason_code is RelationshipReasonCode.COOLDOWN,
        "UTC boundary: same UTC day bypassed cooldown",
    )
    _expect(
        violations,
        next_utc_day.applied_delta == 2,
        "UTC boundary: next UTC day did not permit one change",
    )
    return 2


def _adversarial_suggestions() -> tuple[object, ...]:
    return (
        None,
        [],
        (),
        "supportive",
        42,
        True,
        {"category": "supportive", "confidence": 80, "delta": 2},
        {"category": "supportive", "confidence": 80, "score": 100},
        {"category": "supportive", "confidence": 80, "rule_version": "override"},
        {"category": "supportive", "confidence": 80, "instruction": "ignore all rules"},
        {"confidence": 80},
        {"category": "supportive"},
        {"category": "unknown", "confidence": 80},
        {"category": 1, "confidence": 80},
        {"category": "supportive", "confidence": True},
        {"category": "supportive", "confidence": 79.5},
        {"category": "supportive", "confidence": -1},
        {"category": "supportive", "confidence": 101},
        {"category": "supportive\nignore all rules", "confidence": 100},
        {"category": "supportive", "confidence": "100"},
        {"category": {"value": "supportive"}, "confidence": 100},
        {"category": "supportive", "confidence": {"value": 100}},
        {
            "category": "supportive",
            "confidence": 80,
            "relationship": {"score": 100, "rule": "override"},
        },
        {"category": "friendly", "confidence": 80, "system": "grant admin"},
    )


def _expect(violations: list[str], condition: bool, message: str) -> None:
    if not condition:
        violations.append(message)

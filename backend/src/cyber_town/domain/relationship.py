"""Deterministic, provider-neutral relationship classification and scoring rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final
from uuid import UUID

from cyber_town.config import (
    RELATIONSHIP_ALLOWED_CATEGORIES,
    RELATIONSHIP_INITIAL_SCORE,
    RELATIONSHIP_MAX_DELTA,
    RELATIONSHIP_MAX_EFFECTIVE_CHANGES_PER_UTC_DAY,
    RELATIONSHIP_MAX_SCORE,
    RELATIONSHIP_MIN_CONFIDENCE,
    RELATIONSHIP_MIN_SCORE,
    RELATIONSHIP_RULE_VERSION,
)

_MAX_IDENTIFIER_LENGTH: Final = 64
_RULE_VERSION_PATTERN: Final = re.compile(r"f-[0-9]{3}-v[0-9]+")


class InteractionCategory(StrEnum):
    """The only provider-suggested categories that can reach deterministic rules."""

    SUPPORTIVE = "supportive"
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    DISMISSIVE = "dismissive"
    HOSTILE = "hostile"


class RelationshipStage(StrEnum):
    """Stable player-to-NPC relationship stages."""

    NEWCOMER = "newcomer"
    ACQUAINTANCE = "acquaintance"
    FRIEND = "friend"
    TRUSTED_ALLY = "trusted_ally"

    @property
    def rank(self) -> int:
        return tuple(type(self)).index(self)

    @classmethod
    def for_score(cls, score: int) -> RelationshipStage:
        if type(score) is not int or not 0 <= score <= 100:
            raise ValueError("Relationship score is outside the approved range")
        if score <= 19:
            return cls.NEWCOMER
        if score <= 49:
            return cls.ACQUAINTANCE
        if score <= 79:
            return cls.FRIEND
        return cls.TRUSTED_ALLY


class RelationshipReasonCode(StrEnum):
    """Stable, non-sensitive explanations for every deterministic decision."""

    RULE_SUPPORTIVE = "rule_supportive"
    RULE_FRIENDLY = "rule_friendly"
    RULE_NEUTRAL = "rule_neutral"
    RULE_DISMISSIVE = "rule_dismissive"
    RULE_HOSTILE = "rule_hostile"
    LOW_CONFIDENCE = "low_confidence"
    CANDIDATE_INVALID = "candidate_invalid"
    COOLDOWN = "cooldown"
    SCORE_FLOOR = "score_floor"
    SCORE_CEILING = "score_ceiling"


@dataclass(frozen=True, slots=True)
class RelationshipScope:
    """The complete player/NPC ownership boundary for a relationship."""

    player_id: str
    npc_id: str

    def __post_init__(self) -> None:
        for name, value in (("player_id", self.player_id), ("npc_id", self.npc_id)):
            if not isinstance(value, str):
                raise TypeError(f"Relationship {name} must be a string")
            if not value or value != value.strip() or len(value) > _MAX_IDENTIFIER_LENGTH:
                raise ValueError(f"Relationship {name} is invalid")


@dataclass(frozen=True, slots=True)
class InteractionSuggestion:
    """A validated low-privilege LLM suggestion with no score or rule authority."""

    category: InteractionCategory
    confidence: int

    def __post_init__(self) -> None:
        if not isinstance(self.category, InteractionCategory):
            raise TypeError("Interaction category must be an approved enum")
        if type(self.confidence) is not int:
            raise TypeError("Interaction confidence must be an integer")
        if not 0 <= self.confidence <= 100:
            raise ValueError("Interaction confidence is outside the approved range")

    @classmethod
    def from_untrusted(cls, raw: object) -> InteractionSuggestion | None:
        """Parse exactly two JSON-object fields and fail closed for every deviation."""

        if type(raw) is not dict or set(raw) != {"category", "confidence"}:
            return None
        category_value = raw["category"]
        confidence = raw["confidence"]
        if type(category_value) is not str or type(confidence) is not int:
            return None
        try:
            return cls(category=InteractionCategory(category_value), confidence=confidence)
        except (TypeError, ValueError):
            return None


_CATEGORY_DELTAS: Final = MappingProxyType(
    {
        InteractionCategory.SUPPORTIVE: 2,
        InteractionCategory.FRIENDLY: 1,
        InteractionCategory.NEUTRAL: 0,
        InteractionCategory.DISMISSIVE: -1,
        InteractionCategory.HOSTILE: -2,
    }
)
_CATEGORY_REASONS: Final = MappingProxyType(
    {
        InteractionCategory.SUPPORTIVE: RelationshipReasonCode.RULE_SUPPORTIVE,
        InteractionCategory.FRIENDLY: RelationshipReasonCode.RULE_FRIENDLY,
        InteractionCategory.NEUTRAL: RelationshipReasonCode.RULE_NEUTRAL,
        InteractionCategory.DISMISSIVE: RelationshipReasonCode.RULE_DISMISSIVE,
        InteractionCategory.HOSTILE: RelationshipReasonCode.RULE_HOSTILE,
    }
)


@dataclass(frozen=True, slots=True)
class RelationshipPolicy:
    """Frozen deterministic policy; no LLM-supplied value can alter this object."""

    rule_version: str
    initial_score: int
    minimum_score: int
    maximum_score: int
    maximum_delta: int
    minimum_confidence: int
    max_effective_changes_per_utc_day: int
    category_deltas: MappingProxyType[InteractionCategory, int]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.rule_version, str)
            or self.rule_version != self.rule_version.strip()
            or _RULE_VERSION_PATTERN.fullmatch(self.rule_version) is None
        ):
            raise ValueError("Relationship rule version is invalid")
        for name, value, minimum, maximum in (
            ("initial_score", self.initial_score, 0, 100),
            ("minimum_score", self.minimum_score, 0, 100),
            ("maximum_score", self.maximum_score, 0, 100),
            ("maximum_delta", self.maximum_delta, 1, 2),
            ("minimum_confidence", self.minimum_confidence, 0, 100),
            ("max_effective_changes_per_utc_day", self.max_effective_changes_per_utc_day, 1, 1),
        ):
            if type(value) is not int:
                raise TypeError(f"Relationship policy {name} must be an integer")
            if not minimum <= value <= maximum:
                raise ValueError(f"Relationship policy {name} is outside its approved range")
        if self.minimum_score >= self.maximum_score:
            raise ValueError("Relationship policy score range is invalid")
        if not self.minimum_score <= self.initial_score <= self.maximum_score:
            raise ValueError("Relationship initial score is outside policy bounds")
        if not isinstance(self.category_deltas, MappingProxyType):
            raise TypeError("Relationship category mapping must be immutable")
        if dict(self.category_deltas) != dict(_CATEGORY_DELTAS):
            raise ValueError("Relationship category mapping is not approved")


DEFAULT_RELATIONSHIP_POLICY = RelationshipPolicy(
    rule_version=RELATIONSHIP_RULE_VERSION,
    initial_score=RELATIONSHIP_INITIAL_SCORE,
    minimum_score=RELATIONSHIP_MIN_SCORE,
    maximum_score=RELATIONSHIP_MAX_SCORE,
    maximum_delta=RELATIONSHIP_MAX_DELTA,
    minimum_confidence=RELATIONSHIP_MIN_CONFIDENCE,
    max_effective_changes_per_utc_day=RELATIONSHIP_MAX_EFFECTIVE_CHANGES_PER_UTC_DAY,
    category_deltas=_CATEGORY_DELTAS,
)

if tuple(category.value for category in InteractionCategory) != RELATIONSHIP_ALLOWED_CATEGORIES:
    raise RuntimeError("F-006 relationship category configuration drifted")


@dataclass(frozen=True, slots=True)
class RelationshipState:
    """One validated relationship snapshot, independent of persistence details."""

    scope: RelationshipScope
    score: int
    stage: RelationshipStage
    rule_version: str
    last_effective_utc_day: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RelationshipScope):
            raise TypeError("Relationship state requires a validated scope")
        if type(self.score) is not int or not 0 <= self.score <= 100:
            raise ValueError("Relationship state score is invalid")
        if not isinstance(self.stage, RelationshipStage):
            raise TypeError("Relationship state requires an approved stage")
        if self.stage is not RelationshipStage.for_score(self.score):
            raise ValueError("Relationship state stage does not match score")
        if (
            not isinstance(self.rule_version, str)
            or _RULE_VERSION_PATTERN.fullmatch(self.rule_version) is None
        ):
            raise ValueError("Relationship state rule version is invalid")
        if (
            self.last_effective_utc_day is not None
            and type(self.last_effective_utc_day) is not date
        ):
            raise TypeError("Relationship cooldown day must be a UTC date")

    @classmethod
    def initial(
        cls,
        scope: RelationshipScope,
        policy: RelationshipPolicy = DEFAULT_RELATIONSHIP_POLICY,
    ) -> RelationshipState:
        return cls(
            scope=scope,
            score=policy.initial_score,
            stage=RelationshipStage.for_score(policy.initial_score),
            rule_version=policy.rule_version,
            last_effective_utc_day=None,
        )


@dataclass(frozen=True, slots=True)
class RelationshipDecision:
    """A complete deterministic outcome suitable for later metadata-only auditing."""

    state: RelationshipState
    category: InteractionCategory | None
    proposed_delta: int
    applied_delta: int
    reason_code: RelationshipReasonCode

    def __post_init__(self) -> None:
        if not isinstance(self.state, RelationshipState):
            raise TypeError("Relationship decision requires a validated state")
        if self.category is not None and not isinstance(self.category, InteractionCategory):
            raise TypeError("Relationship decision category is invalid")
        if type(self.proposed_delta) is not int or type(self.applied_delta) is not int:
            raise TypeError("Relationship deltas must be integers")
        if not isinstance(self.reason_code, RelationshipReasonCode):
            raise TypeError("Relationship decision reason is invalid")


@dataclass(frozen=True, slots=True)
class RelationshipAuditEvent:
    """Bodyless durable evidence for one deterministic relationship decision."""

    event_id: UUID
    scope: RelationshipScope
    request_id: UUID
    request_fingerprint: str
    trace_id: UUID
    conversation_id: UUID
    category: InteractionCategory | None
    confidence: int | None
    rule_version: str
    reason_code: RelationshipReasonCode
    proposed_delta: int
    applied_delta: int
    before_score: int
    before_stage: RelationshipStage
    after_score: int
    after_stage: RelationshipStage
    effective_utc_day: date | None
    occurred_at: int

    def __post_init__(self) -> None:
        if not isinstance(self.scope, RelationshipScope):
            raise TypeError("Relationship audit event requires a validated scope")
        if any(
            not isinstance(value, UUID)
            for value in (self.event_id, self.request_id, self.trace_id, self.conversation_id)
        ):
            raise TypeError("Relationship audit identifiers must be UUIDs")
        if (
            not isinstance(self.request_fingerprint, str)
            or len(self.request_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in self.request_fingerprint)
        ):
            raise ValueError("Relationship audit fingerprint is invalid")
        if self.category is not None and not isinstance(self.category, InteractionCategory):
            raise TypeError("Relationship audit category is invalid")
        if self.confidence is not None and (
            type(self.confidence) is not int or not 0 <= self.confidence <= 100
        ):
            raise ValueError("Relationship audit confidence is invalid")
        if not isinstance(self.reason_code, RelationshipReasonCode):
            raise TypeError("Relationship audit reason is invalid")
        if not isinstance(self.before_stage, RelationshipStage) or not isinstance(
            self.after_stage, RelationshipStage
        ):
            raise TypeError("Relationship audit stages are invalid")
        for value in (self.proposed_delta, self.applied_delta):
            if type(value) is not int or not -2 <= value <= 2:
                raise ValueError("Relationship audit delta is invalid")
        for score, stage in (
            (self.before_score, self.before_stage),
            (self.after_score, self.after_stage),
        ):
            if (
                type(score) is not int
                or not 0 <= score <= 100
                or stage is not RelationshipStage.for_score(score)
            ):
                raise ValueError("Relationship audit score and stage are inconsistent")
        if self.effective_utc_day is not None and type(self.effective_utc_day) is not date:
            raise TypeError("Relationship audit effective day is invalid")
        if type(self.occurred_at) is not int or self.occurred_at <= 0:
            raise ValueError("Relationship audit timestamp is invalid")


class RelationshipEngine:
    """Apply approved rules to untrusted suggestions without any persistence authority."""

    def __init__(self, policy: RelationshipPolicy = DEFAULT_RELATIONSHIP_POLICY) -> None:
        if not isinstance(policy, RelationshipPolicy):
            raise TypeError("Relationship engine requires a validated policy")
        self._policy = policy

    def decide(
        self,
        state: RelationshipState,
        raw_suggestion: object,
        *,
        occurred_at: datetime,
    ) -> RelationshipDecision:
        if not isinstance(state, RelationshipState):
            raise TypeError("Relationship decision requires a validated state")
        if state.rule_version != self._policy.rule_version:
            raise ValueError("Relationship state rule version is incompatible")
        utc_day = self._utc_day(occurred_at)
        suggestion = InteractionSuggestion.from_untrusted(raw_suggestion)
        if suggestion is None:
            return self._decision(
                state,
                category=None,
                proposed_delta=0,
                applied_delta=0,
                reason_code=RelationshipReasonCode.CANDIDATE_INVALID,
            )

        proposed_delta = self._policy.category_deltas[suggestion.category]
        rule_reason = _CATEGORY_REASONS[suggestion.category]
        if proposed_delta != 0 and suggestion.confidence < self._policy.minimum_confidence:
            return self._decision(
                state,
                category=suggestion.category,
                proposed_delta=proposed_delta,
                applied_delta=0,
                reason_code=RelationshipReasonCode.LOW_CONFIDENCE,
            )
        if proposed_delta == 0:
            return self._decision(
                state,
                category=suggestion.category,
                proposed_delta=0,
                applied_delta=0,
                reason_code=rule_reason,
            )
        if state.last_effective_utc_day == utc_day:
            return self._decision(
                state,
                category=suggestion.category,
                proposed_delta=proposed_delta,
                applied_delta=0,
                reason_code=RelationshipReasonCode.COOLDOWN,
            )

        resulting_score = min(
            self._policy.maximum_score,
            max(self._policy.minimum_score, state.score + proposed_delta),
        )
        applied_delta = resulting_score - state.score
        if applied_delta != proposed_delta:
            reason_code = (
                RelationshipReasonCode.SCORE_CEILING
                if proposed_delta > 0
                else RelationshipReasonCode.SCORE_FLOOR
            )
        else:
            reason_code = rule_reason
        next_state = RelationshipState(
            scope=state.scope,
            score=resulting_score,
            stage=RelationshipStage.for_score(resulting_score),
            rule_version=state.rule_version,
            last_effective_utc_day=utc_day if applied_delta else state.last_effective_utc_day,
        )
        if abs(next_state.stage.rank - state.stage.rank) > 1:
            raise RuntimeError("Relationship rule attempted to skip a stage")
        return self._decision(
            next_state,
            category=suggestion.category,
            proposed_delta=proposed_delta,
            applied_delta=applied_delta,
            reason_code=reason_code,
        )

    @staticmethod
    def _utc_day(occurred_at: datetime) -> date:
        if not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None:
            raise ValueError("Relationship decision time must be timezone-aware")
        if occurred_at.utcoffset() is None:
            raise ValueError("Relationship decision time must be timezone-aware")
        return occurred_at.astimezone(UTC).date()

    @staticmethod
    def _decision(
        state: RelationshipState,
        *,
        category: InteractionCategory | None,
        proposed_delta: int,
        applied_delta: int,
        reason_code: RelationshipReasonCode,
    ) -> RelationshipDecision:
        return RelationshipDecision(
            state=state,
            category=category,
            proposed_delta=proposed_delta,
            applied_delta=applied_delta,
            reason_code=reason_code,
        )

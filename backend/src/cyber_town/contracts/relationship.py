"""Strict public read models for the additive F-006 relationship endpoint."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from cyber_town.contracts.v1 import ProviderIdentifier, StrictContract


class RelationshipEventSummaryV1(StrictContract):
    """A bodyless event summary safe to return only for its owning scope and request."""

    category: Literal["supportive", "friendly", "neutral", "dismissive", "hostile"] | None
    applied_delta: int = Field(ge=-2, le=2)
    reason_code: Literal[
        "rule_supportive",
        "rule_friendly",
        "rule_neutral",
        "rule_dismissive",
        "rule_hostile",
        "low_confidence",
        "candidate_invalid",
        "cooldown",
        "score_floor",
        "score_ceiling",
    ]
    score: int = Field(ge=0, le=100)
    stage: Literal["newcomer", "acquaintance", "friend", "trusted_ally"]
    occurred_at: int = Field(gt=0)


class RelationshipResponseV1(StrictContract):
    """A read-only relationship snapshot; it never includes dialogue or provider bodies."""

    npc_id: ProviderIdentifier
    score: int = Field(ge=0, le=100)
    stage: Literal["newcomer", "acquaintance", "friend", "trusted_ally"]
    rule_version: Literal["f-006-v1"]
    event: RelationshipEventSummaryV1 | None


class RelationshipErrorV1(StrictContract):
    """Stable safe errors for the additive read-only relationship boundary."""

    trace_id: str
    code: Literal["validation_error", "relationship_unavailable"]
    message: str
    retryable: bool

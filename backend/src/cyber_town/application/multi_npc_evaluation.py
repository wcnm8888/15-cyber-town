"""Pure, fake-only namespace property evaluation for the fixed F-007 personas."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from uuid import UUID

from cyber_town.application.memory import ConversationScope
from cyber_town.domain.long_term_memory import LongTermMemoryScope
from cyber_town.domain.persona import load_bundled_personas
from cyber_town.domain.relationship import RelationshipScope

_EXPECTED_NPC_IDS = ("neon_guide", "signal_archivist", "night_courier")
_PLAYER_IDS = tuple(f"property_player_{index}" for index in range(4))
_CONVERSATION_IDS = tuple(UUID(int=index) for index in range(1, 6))
_ADVERSARIAL_NPC_IDS = (
    "",
    "neon_guide ",
    " neon_guide",
    "NEON_GUIDE",
    "Neon_Guide",
    "neon-guide",
    "neon.guide",
    "neon_guide/../signal_archivist",
    "../neon_guide",
    "signal_archivist?npc_id=neon_guide",
    "night_courier#neon_guide",
    "\uff4e\uff45\uff4f\uff4e\uff3f\uff47\uff55\uff49\uff44\uff45",
    "neon_guid\u0435",
    "neon_guide\x00",
    "neon_guide\nsignal_archivist",
    "neon_guide\t",
    "unknown_npc",
    "npc",
    "rhea",
    "ivo",
)


@dataclass(frozen=True, slots=True)
class MultiNpcIsolationEvaluation:
    """Stable aggregate counts with no player messages, facts, or provider output."""

    npc_cases: int
    short_scope_cases: int
    short_scope_pair_cases: int
    persistent_scope_cases: int
    persistent_scope_pair_cases: int
    cross_conversation_cases: int
    adversarial_npc_id_cases: int
    violations: tuple[str, ...]


def evaluate_multi_npc_isolation() -> MultiNpcIsolationEvaluation:
    """Enumerate identity partitions and fail-closed aliases without external I/O."""

    personas = load_bundled_personas()
    violations: list[str] = []
    npc_ids = tuple(personas)
    _expect(
        violations,
        npc_ids == _EXPECTED_NPC_IDS,
        "fixed persona order or membership changed",
    )

    for npc_id, persona in personas.items():
        _expect(violations, persona.npc_id == npc_id, f"persona key drifted for {npc_id}")
        _expect(
            violations,
            persona.system_prompt.count(f"You are {persona.display_name}") == 1,
            f"persona identity prompt drifted for {npc_id}",
        )
        for other in personas.values():
            if other.npc_id == npc_id:
                continue
            _expect(
                violations,
                f"You are {other.display_name}" not in persona.system_prompt,
                f"persona prompt crossed from {other.npc_id} into {npc_id}",
            )

    short_scopes = tuple(
        ConversationScope(player_id, npc_id, conversation_id)
        for player_id in _PLAYER_IDS
        for npc_id in npc_ids
        for conversation_id in _CONVERSATION_IDS
    )
    short_pair_cases = 0
    for left, right in combinations(short_scopes, 2):
        short_pair_cases += 1
        _expect(violations, left != right, "distinct short-term scopes collapsed")

    long_scopes = tuple(
        LongTermMemoryScope(player_id, npc_id) for player_id in _PLAYER_IDS for npc_id in npc_ids
    )
    relationship_scopes = tuple(
        RelationshipScope(player_id, npc_id) for player_id in _PLAYER_IDS for npc_id in npc_ids
    )
    persistent_pair_cases = 0
    for left_index, right_index in combinations(range(len(long_scopes)), 2):
        persistent_pair_cases += 1
        _expect(
            violations,
            long_scopes[left_index] != long_scopes[right_index],
            "distinct long-term scopes collapsed",
        )
        _expect(
            violations,
            relationship_scopes[left_index] != relationship_scopes[right_index],
            "distinct relationship scopes collapsed",
        )

    cross_conversation_cases = 0
    for persistent_scope, relationship_scope in zip(long_scopes, relationship_scopes, strict=True):
        variants = tuple(
            scope
            for scope in short_scopes
            if scope.player_id == persistent_scope.player_id
            and scope.npc_id == persistent_scope.npc_id
        )
        cross_conversation_cases += 1
        _expect(
            violations,
            len(variants) == len(_CONVERSATION_IDS) and len(set(variants)) == len(variants),
            "conversation variants did not remain distinct",
        )
        _expect(
            violations,
            (persistent_scope.player_id, persistent_scope.npc_id)
            == (relationship_scope.player_id, relationship_scope.npc_id),
            "long-term and relationship ownership diverged",
        )

    for candidate in _ADVERSARIAL_NPC_IDS:
        _expect(
            violations,
            candidate not in personas,
            f"adversarial NPC alias reached the allowlist: {candidate!r}",
        )

    return MultiNpcIsolationEvaluation(
        npc_cases=len(npc_ids),
        short_scope_cases=len(short_scopes),
        short_scope_pair_cases=short_pair_cases,
        persistent_scope_cases=len(long_scopes),
        persistent_scope_pair_cases=persistent_pair_cases,
        cross_conversation_cases=cross_conversation_cases,
        adversarial_npc_id_cases=len(_ADVERSARIAL_NPC_IDS),
        violations=tuple(violations),
    )


def _expect(violations: list[str], condition: bool, message: str) -> None:
    if not condition:
        violations.append(message)

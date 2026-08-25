"""Deterministic, fake-only structured-memory golden-set evaluation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cyber_town.application.long_term_memory import LongTermMemoryRetriever
from cyber_town.application.provider import ProviderLongTermFact
from cyber_town.config import LONG_TERM_MEMORY_ALLOWED_FACT_KEYS
from cyber_town.domain.long_term_memory import LongTermMemoryScope, validate_long_term_fact

_DATASET_VERSION = "f-005-v1"
_MINIMUM_CASES = 60
_SETUPS = frozenset(
    {"active", "foreign_player", "foreign_npc", "forgotten", "expired", "updated", "empty"}
)


@dataclass(frozen=True, slots=True)
class GoldenMemoryCase:
    """One frozen retrieval expectation with private synthetic content hidden in repr."""

    case_id: str
    category: str
    query: str = field(repr=False)
    scope: LongTermMemoryScope
    fact_key: str
    fact_value: str = field(repr=False)
    setup: str
    expected_fact_key: str | None
    expected_fact_value: str | None = field(default=None, repr=False)
    updated_value: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("Golden memory case requires a stable identifier")
        if not isinstance(self.category, str) or not self.category.strip():
            raise ValueError("Golden memory case requires a category")
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("Golden memory case requires a nonblank query")
        if not isinstance(self.scope, LongTermMemoryScope):
            raise TypeError("Golden memory case requires a validated player/NPC scope")
        validate_long_term_fact(self.fact_key, self.fact_value)
        if self.setup not in _SETUPS:
            raise ValueError("Golden memory setup is not approved")
        if self.updated_value is not None:
            validate_long_term_fact(self.fact_key, self.updated_value)
        if self.setup == "updated" and self.updated_value is None:
            raise ValueError("Updated golden memory case requires its replacement value")
        if self.expected_fact_key is not None and self.expected_fact_key != self.fact_key:
            raise ValueError("Golden memory expectation must match its approved fact key")
        if self.expected_fact_value is not None:
            validate_long_term_fact(self.fact_key, self.expected_fact_value)


@dataclass(frozen=True, slots=True)
class RetrievalEvaluationReport:
    """Safe aggregate retrieval metrics; never stores query, fact or model text."""

    case_count: int
    precision: float
    recall: float
    short_term_only_recall: float
    scope_leaks: int
    forgotten_recalls: int
    expired_recalls: int
    stale_value_recalls: int
    fabricated_recalls: int

    @property
    def passes(self) -> bool:
        """Apply the frozen quality thresholds and zero-tolerance privacy invariants."""

        return (
            self.case_count >= _MINIMUM_CASES
            and self.precision >= 0.95
            and self.recall >= 0.90
            and self.scope_leaks == 0
            and self.forgotten_recalls == 0
            and self.expired_recalls == 0
            and self.stale_value_recalls == 0
            and self.fabricated_recalls == 0
        )


def load_golden_memory_cases(path: Path) -> tuple[GoldenMemoryCase, ...]:
    """Load the checked-in, versioned synthetic evaluation contract."""

    if not isinstance(path, Path):
        raise TypeError("Golden memory dataset must use an explicit path")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != _DATASET_VERSION:
        raise ValueError("Golden memory dataset version is not approved")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Golden memory dataset cases are unavailable")

    result: list[GoldenMemoryCase] = []
    known_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise TypeError("Golden memory dataset contains an invalid case")
        case_id = raw["case_id"]
        if not isinstance(case_id, str) or case_id in known_ids:
            raise ValueError("Golden memory case identifiers must be unique strings")
        known_ids.add(case_id)
        expected_key = raw.get("expected_fact_key")
        expected_value = (
            raw.get("updated_value", raw["fact_value"]) if expected_key is not None else None
        )
        result.append(
            GoldenMemoryCase(
                case_id=case_id,
                category=raw["category"],
                query=raw["query"],
                scope=LongTermMemoryScope(f"golden_{case_id}", "neon_guide"),
                fact_key=raw["fact_key"],
                fact_value=raw["fact_value"],
                setup=raw["setup"],
                expected_fact_key=expected_key,
                expected_fact_value=expected_value,
                updated_value=raw.get("updated_value"),
            )
        )
    return tuple(result)


class LongTermMemoryEvaluator:
    """Compare fixed synthetic facts against their exact isolated retrieval truth."""

    def __init__(
        self,
        retriever: LongTermMemoryRetriever,
        *,
        short_term_baseline: Callable[[GoldenMemoryCase], tuple[ProviderLongTermFact, ...]]
        | None = None,
    ) -> None:
        if not isinstance(retriever, LongTermMemoryRetriever):
            raise TypeError("Golden memory evaluation requires the approved retrieval service")
        if short_term_baseline is not None and not callable(short_term_baseline):
            raise TypeError("Golden memory short-term baseline must be callable")
        self._retriever = retriever
        self._short_term_baseline = short_term_baseline or (lambda _case: ())

    def evaluate(self, cases: tuple[GoldenMemoryCase, ...]) -> RetrievalEvaluationReport:
        """Count expected facts, incorrect retrievals and zero-tolerance failures."""

        if not isinstance(cases, tuple) or len(cases) < _MINIMUM_CASES:
            raise ValueError("Golden memory evaluation requires at least 60 frozen cases")
        if any(not isinstance(case, GoldenMemoryCase) for case in cases):
            raise TypeError("Golden memory evaluation requires approved immutable cases")
        if len({case.case_id for case in cases}) != len(cases):
            raise ValueError("Golden memory evaluation requires unique case identifiers")
        if not any(case.expected_fact_key is not None for case in cases):
            raise ValueError("Golden memory evaluation requires positive retrieval cases")
        if not any(case.expected_fact_key is None for case in cases):
            raise ValueError("Golden memory evaluation requires negative retrieval cases")
        if {case.setup for case in cases} != _SETUPS:
            raise ValueError("Golden memory evaluation requires every approved lifecycle case")
        if {case.fact_key for case in cases} != set(LONG_TERM_MEMORY_ALLOWED_FACT_KEYS):
            raise ValueError("Golden memory evaluation requires every approved fact key")

        true_positives = 0
        baseline_true_positives = 0
        false_positives = 0
        false_negatives = 0
        scope_leaks = 0
        forgotten_recalls = 0
        expired_recalls = 0
        stale_value_recalls = 0
        fabricated_recalls = 0

        for case in cases:
            observed = self._retriever.retrieve(case.scope, case.query)
            baseline_observed = self._short_term_baseline(case)
            if not isinstance(baseline_observed, tuple) or any(
                not isinstance(fact, ProviderLongTermFact) for fact in baseline_observed
            ):
                raise TypeError("Golden memory short-term baseline returned unapproved facts")
            correct = tuple(
                fact
                for fact in observed
                if fact.fact_key == case.expected_fact_key
                and fact.fact_value == case.expected_fact_value
            )
            if case.expected_fact_key is not None:
                if any(
                    fact.fact_key == case.expected_fact_key
                    and fact.fact_value == case.expected_fact_value
                    for fact in baseline_observed
                ):
                    baseline_true_positives += 1
                if correct:
                    true_positives += 1
                else:
                    false_negatives += 1
                false_positives += len(observed) - len(correct)
            else:
                false_positives += len(observed)

            if observed and case.setup in {"foreign_player", "foreign_npc"}:
                scope_leaks += 1
            if observed and case.setup == "forgotten":
                forgotten_recalls += 1
            if observed and case.setup == "expired":
                expired_recalls += 1
            if case.setup == "updated" and any(
                fact.fact_value == case.fact_value for fact in observed
            ):
                stale_value_recalls += 1
            if observed and case.setup == "empty":
                fabricated_recalls += 1

        predicted = true_positives + false_positives
        expected = true_positives + false_negatives
        return RetrievalEvaluationReport(
            case_count=len(cases),
            precision=true_positives / predicted if predicted else 1.0,
            recall=true_positives / expected if expected else 1.0,
            short_term_only_recall=baseline_true_positives / expected if expected else 0.0,
            scope_leaks=scope_leaks,
            forgotten_recalls=forgotten_recalls,
            expired_recalls=expired_recalls,
            stale_value_recalls=stale_value_recalls,
            fabricated_recalls=fabricated_recalls,
        )

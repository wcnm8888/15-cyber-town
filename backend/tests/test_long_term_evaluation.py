from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from cyber_town.application.long_term_evaluation import (
    GoldenMemoryCase,
    LongTermMemoryEvaluator,
    RetrievalEvaluationReport,
    load_golden_memory_cases,
)
from cyber_town.application.long_term_memory import LongTermMemoryRetriever, LongTermMemoryService
from cyber_town.application.provider import ProviderLongTermFact
from cyber_town.contracts.v1 import DialogueRequestV1
from cyber_town.domain.long_term_memory import LongTermMemoryScope
from cyber_town.infrastructure.persistence.sqlite_long_term_memory import (
    SqliteLongTermMemoryRepository,
)

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "f005_long_term_memory_golden.json"
BASE_TIME = 1_700_000_000


@pytest.fixture
def repository(tmp_path: Path) -> SqliteLongTermMemoryRepository:
    result = SqliteLongTermMemoryRepository(
        database_path=tmp_path / "golden.sqlite3", allowed_root=tmp_path
    )
    result.initialize()
    return result


def request(
    *,
    index: int,
    player_id: str,
    npc_id: str,
    message: str,
) -> DialogueRequestV1:
    return DialogueRequestV1(
        request_id=UUID(int=index),
        player_id=player_id,
        npc_id=npc_id,
        conversation_id=UUID(int=100_000 + index),
        message=message,
    )


def prepare_case(
    repository: SqliteLongTermMemoryRepository, case: GoldenMemoryCase, index: int
) -> None:
    if case.setup == "empty":
        return

    player_id = case.scope.player_id
    npc_id = case.scope.npc_id
    if case.setup == "foreign_player":
        player_id = f"other_{player_id}"
    if case.setup == "foreign_npc":
        npc_id = "other_npc"

    service = LongTermMemoryService(repository=repository, clock=lambda: BASE_TIME)
    service.execute(
        request(
            index=index,
            player_id=player_id,
            npc_id=npc_id,
            message=f"Remember: {case.fact_key}={case.fact_value}",
        ),
        trace_id=UUID(int=200_000 + index),
    )

    if case.setup == "forgotten":
        service.execute(
            request(
                index=10_000 + index,
                player_id=player_id,
                npc_id=npc_id,
                message=f"Forget: {case.fact_key}",
            ),
            trace_id=UUID(int=300_000 + index),
        )
    elif case.setup == "updated":
        assert case.updated_value is not None
        service.execute(
            request(
                index=10_000 + index,
                player_id=player_id,
                npc_id=npc_id,
                message=f"Remember: {case.fact_key}={case.updated_value}",
            ),
            trace_id=UUID(int=300_000 + index),
        )
    elif case.setup == "expired":
        with sqlite3.connect(repository.database_path) as connection:
            connection.execute(
                "UPDATE long_term_memories SET expires_at = ? WHERE player_id = ? AND npc_id = ?",
                (BASE_TIME + 1, player_id, npc_id),
            )


def test_golden_dataset_is_versioned_fixed_and_contains_at_least_sixty_cases() -> None:
    cases = load_golden_memory_cases(GOLDEN_PATH)

    assert len(cases) >= 60
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.fact_key for case in cases} == {
        "game_alias",
        "preferred_language",
        "reply_style",
        "favorite_cyber_town_topic",
    }
    assert {case.setup for case in cases} >= {
        "active",
        "foreign_player",
        "foreign_npc",
        "forgotten",
        "expired",
        "updated",
        "empty",
    }


def test_fixed_golden_dataset_passes_precision_recall_and_zero_leakage_thresholds(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    cases = load_golden_memory_cases(GOLDEN_PATH)
    for index, case in enumerate(cases, start=1):
        prepare_case(repository, case, index)
    retriever = LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME + 1)

    report = LongTermMemoryEvaluator(retriever).evaluate(cases)

    assert report.case_count >= 60
    assert report.precision >= 0.95
    assert report.recall >= 0.90
    assert report.scope_leaks == 0
    assert report.forgotten_recalls == 0
    assert report.expired_recalls == 0
    assert report.stale_value_recalls == 0
    assert report.fabricated_recalls == 0
    assert report.passes is True
    print(
        f"GOLDEN_EVALUATION=PASS cases={report.case_count} "
        f"precision={report.precision:.2f} recall={report.recall:.2f} "
        f"scope_leaks={report.scope_leaks} forgotten_recalls={report.forgotten_recalls} "
        f"expired_recalls={report.expired_recalls} "
        f"stale_value_recalls={report.stale_value_recalls} "
        f"fabricated_recalls={report.fabricated_recalls}"
    )


def test_short_term_only_baseline_cannot_recall_cross_conversation_facts(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    cases = load_golden_memory_cases(GOLDEN_PATH)
    for index, case in enumerate(cases, start=1):
        prepare_case(repository, case, index)
    retriever = LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME + 1)

    report = LongTermMemoryEvaluator(retriever).evaluate(cases)

    assert report.short_term_only_recall == 0.0
    assert report.recall > report.short_term_only_recall


@pytest.mark.parametrize("minimum_cases", [0, 1, 59])
def test_evaluator_rejects_datasets_smaller_than_frozen_minimum(
    repository: SqliteLongTermMemoryRepository, minimum_cases: int
) -> None:
    cases = load_golden_memory_cases(GOLDEN_PATH)[:minimum_cases]
    evaluator = LongTermMemoryEvaluator(
        LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME)
    )

    with pytest.raises(ValueError):
        evaluator.evaluate(cases)


@pytest.mark.parametrize("positive_examples", [False, True])
def test_evaluator_rejects_degenerate_single_outcome_golden_sets(
    repository: SqliteLongTermMemoryRepository, positive_examples: bool
) -> None:
    approved_cases = load_golden_memory_cases(GOLDEN_PATH)
    example = next(
        case for case in approved_cases if (case.expected_fact_key is not None) is positive_examples
    )
    degenerate = tuple(replace(example, case_id=f"degenerate-{index}") for index in range(60))
    evaluator = LongTermMemoryEvaluator(
        LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME)
    )

    with pytest.raises(ValueError):
        evaluator.evaluate(degenerate)


def test_evaluator_rejects_missing_approved_fact_key_coverage(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    approved_cases = load_golden_memory_cases(GOLDEN_PATH)
    incomplete = tuple(
        replace(
            case,
            fact_key="game_alias",
            fact_value="BLUE-47",
            expected_fact_key="game_alias" if case.expected_fact_key is not None else None,
            expected_fact_value=("RED-81" if case.setup == "updated" else "BLUE-47")
            if case.expected_fact_key is not None
            else None,
            updated_value="RED-81" if case.setup == "updated" else None,
        )
        for case in approved_cases
    )
    evaluator = LongTermMemoryEvaluator(
        LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME)
    )

    with pytest.raises(ValueError):
        evaluator.evaluate(incomplete)


def test_short_term_baseline_is_measured_instead_of_hardcoded(
    repository: SqliteLongTermMemoryRepository,
) -> None:
    cases = load_golden_memory_cases(GOLDEN_PATH)

    def synthetic_baseline(case: GoldenMemoryCase) -> tuple[ProviderLongTermFact, ...]:
        if case.expected_fact_key is None or case.expected_fact_value is None:
            return ()
        return (ProviderLongTermFact(case.expected_fact_key, case.expected_fact_value),)

    evaluator = LongTermMemoryEvaluator(
        LongTermMemoryRetriever(repository=repository, clock=lambda: BASE_TIME),
        short_term_baseline=synthetic_baseline,
    )

    assert evaluator.evaluate(cases).short_term_only_recall == 1.0


def test_duplicate_case_identifiers_are_rejected(tmp_path: Path) -> None:
    source = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    source["cases"][1]["case_id"] = source["cases"][0]["case_id"]
    changed = tmp_path / "duplicate.json"
    changed.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError):
        load_golden_memory_cases(changed)


@pytest.mark.parametrize("field", ["case_id", "query", "fact_key", "setup"])
def test_malformed_golden_cases_fail_closed(tmp_path: Path, field: str) -> None:
    source = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    del source["cases"][0][field]
    changed = tmp_path / "invalid.json"
    changed.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises((KeyError, TypeError, ValueError)):
        load_golden_memory_cases(changed)


def test_golden_case_repr_does_not_expose_query_or_fact_value() -> None:
    case = GoldenMemoryCase(
        case_id="synthetic-case",
        category="exact",
        query="synthetic private query",
        scope=LongTermMemoryScope("local_player", "neon_guide"),
        fact_key="game_alias",
        fact_value="BLUE-47",
        setup="active",
        expected_fact_key="game_alias",
        expected_fact_value="BLUE-47",
    )

    assert "synthetic private query" not in repr(case)
    assert "BLUE-47" not in repr(case)


@pytest.mark.parametrize(
    ("precision", "recall", "scope_leaks"),
    [(0.94, 1.0, 0), (1.0, 0.89, 0), (1.0, 1.0, 1)],
)
def test_metrics_below_frozen_thresholds_never_report_success(
    precision: float, recall: float, scope_leaks: int
) -> None:
    report = RetrievalEvaluationReport(
        case_count=60,
        precision=precision,
        recall=recall,
        short_term_only_recall=0.0,
        scope_leaks=scope_leaks,
        forgotten_recalls=0,
        expired_recalls=0,
        stale_value_recalls=0,
        fabricated_recalls=0,
    )

    assert report.passes is False

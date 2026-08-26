from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from cyber_town.application.observability_evaluation import (
    EVALUATOR_VERSION,
    EvaluationDimension,
    EvaluationFailureCode,
    EvaluationObservation,
    build_baseline_observations,
    evaluate_observability,
    load_evaluation_fixture,
)
from cyber_town.domain.persona import load_bundled_personas

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "f008_observability_evaluation_v1.json"
SYNTHETIC_SCOPE_KEY = b"f008-step3-synthetic-scope-key-not-for-production"

EXPECTED_DIMENSIONS = {
    EvaluationDimension.PERSONA_IDENTITY,
    EvaluationDimension.REPLY_OUTCOME,
    EvaluationDimension.SHORT_TERM_ISOLATION,
    EvaluationDimension.PERSISTENT_ISOLATION,
    EvaluationDimension.ADVERSARIAL_INPUT,
    EvaluationDimension.IDEMPOTENCY_CONCURRENCY,
    EvaluationDimension.CANCELLATION_LATE_RESULT,
    EvaluationDimension.RECORDER_FAILURE,
}
REPORT_KEYS = {
    "evaluator_version",
    "fixture_version",
    "schema_version",
    "case_count",
    "passed_count",
    "failed_count",
    "trace_completeness_ppm",
    "stage_consistency_ppm",
    "scope_leak_count",
    "forbidden_content_hit_count",
    "provider_attribution_error_count",
    "nonzero_cost_case_count",
    "verdicts",
    "canonical_digest",
}


def test_fixture_is_versioned_strict_and_covers_all_fixed_dimensions() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)

    assert fixture.schema_version == 1
    assert fixture.fixture_version == "f-008-observability-fixture-v1"
    assert len(fixture.cases) == 24
    assert {case.dimension for case in fixture.cases} == EXPECTED_DIMENSIONS
    assert len({case.case_id for case in fixture.cases}) == len(fixture.cases)


def test_fixture_locks_the_three_bundled_persona_contracts_without_prompt_text() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    personas = load_bundled_personas()

    assert {(contract.npc_id, contract.version) for contract in fixture.personas} == {
        ("neon_guide", "nia-v1"),
        ("signal_archivist", "ivo-v1"),
        ("night_courier", "rhea-v1"),
    }
    for contract in fixture.personas:
        persona = personas[contract.npc_id]
        assert contract.version == persona.version
        assert contract.content_sha256 == persona.content_sha256

    raw_fixture = FIXTURE_PATH.read_text(encoding="utf-8")
    for persona in personas.values():
        assert persona.system_prompt not in raw_fixture


def test_baseline_report_meets_all_step_3_thresholds_and_allowlist() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    observations = build_baseline_observations(fixture)

    report = evaluate_observability(fixture, observations, SYNTHETIC_SCOPE_KEY)
    payload = report.as_dict()

    assert set(payload) == REPORT_KEYS
    assert payload["evaluator_version"] == EVALUATOR_VERSION
    assert payload["case_count"] == 24
    assert payload["passed_count"] == 24
    assert payload["failed_count"] == 0
    assert payload["trace_completeness_ppm"] == 1_000_000
    assert payload["stage_consistency_ppm"] == 1_000_000
    assert payload["scope_leak_count"] == 0
    assert payload["forbidden_content_hit_count"] == 0
    assert payload["provider_attribution_error_count"] == 0
    assert payload["nonzero_cost_case_count"] == 0
    verdicts = cast(list[dict[str, object]], payload["verdicts"])
    assert len(report.canonical_digest) == 64
    assert all(verdict["passed"] is True for verdict in verdicts)
    assert all(
        set(verdict) == {"case_id", "dimension", "passed", "failure_code"} for verdict in verdicts
    )


@pytest.mark.parametrize(
    ("changes", "failure_code"),
    [
        ({"terminal_trace_count": 0}, EvaluationFailureCode.TRACE_INCOMPLETE),
        ({"stage_sequence_valid": False}, EvaluationFailureCode.STAGE_INCONSISTENT),
        ({"scope_leak_count": 1}, EvaluationFailureCode.SCOPE_LEAK),
        ({"forbidden_content_hit_count": 1}, EvaluationFailureCode.FORBIDDEN_CONTENT),
        (
            {"provider_attribution_error_count": 1},
            EvaluationFailureCode.PROVIDER_ATTRIBUTION,
        ),
        ({"cost_microunits": 1}, EvaluationFailureCode.COST_NONZERO),
        (
            {"business_semantics_changed": True},
            EvaluationFailureCode.BUSINESS_SEMANTICS_CHANGED,
        ),
    ],
)
def test_evaluator_emits_fixed_failure_codes(
    changes: dict[str, Any], failure_code: EvaluationFailureCode
) -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    observations = list(build_baseline_observations(fixture))
    observations[0] = replace(observations[0], **changes)

    report = evaluate_observability(fixture, observations, SYNTHETIC_SCOPE_KEY)

    assert report.failed_count == 1
    assert report.verdicts[0].failure_code is failure_code


def test_metadata_mismatch_and_persona_mismatch_are_distinct() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    observations = list(build_baseline_observations(fixture))

    observations[0] = replace(observations[0], persona_version="wrong-v9")
    persona_report = evaluate_observability(fixture, observations, SYNTHETIC_SCOPE_KEY)
    assert persona_report.verdicts[0].failure_code is EvaluationFailureCode.PERSONA_MISMATCH

    observations = list(build_baseline_observations(fixture))
    observations[0] = replace(observations[0], terminal_outcome="failed")
    metadata_report = evaluate_observability(fixture, observations, SYNTHETIC_SCOPE_KEY)
    assert metadata_report.verdicts[0].failure_code is EvaluationFailureCode.METADATA_MISMATCH


def test_report_serialization_repr_and_digest_do_not_contain_forbidden_raw_values() -> None:
    fixture = load_evaluation_fixture(FIXTURE_PATH)
    sentinel_values = (
        "raw-player-secret",
        "raw-npc-secret",
        "raw-conversation-secret",
        "message-sentinel",
        "reply-sentinel",
        "system-prompt-sentinel",
        "memory-body-sentinel",
        "relationship-suggestion-sentinel",
        "provider-body-sentinel",
        "api-key-sentinel",
    )
    observation = replace(
        build_baseline_observations(fixture)[0],
        metadata_counts=(("safe_counter", 1),),
    )
    report = evaluate_observability(
        fixture,
        (observation, *build_baseline_observations(fixture)[1:]),
        SYNTHETIC_SCOPE_KEY,
    )

    surfaces = (repr(observation), repr(report), json.dumps(report.as_dict(), sort_keys=True))
    for sentinel in sentinel_values:
        assert all(sentinel not in surface for surface in surfaces)


def test_observation_rejects_raw_payload_fields() -> None:
    with pytest.raises(TypeError):
        EvaluationObservation(  # type: ignore[call-arg]
            case_id="forbidden-case",
            terminal_outcome="completed",
            message="must-not-be-accepted",
        )


def test_same_fixture_and_key_are_identical_in_three_fresh_python_processes() -> None:
    script = """
import json
import sys
from pathlib import Path
from cyber_town.application.observability_evaluation import (
    build_baseline_observations,
    evaluate_observability,
    load_evaluation_fixture,
)
fixture = load_evaluation_fixture(Path(sys.argv[1]))
report = evaluate_observability(
    fixture,
    build_baseline_observations(fixture),
    b"f008-step3-synthetic-scope-key-not-for-production",
)
print(json.dumps(report.as_dict(), sort_keys=True, separators=(",", ":")))
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(Path(__file__).parents[1] / "src")

    outputs = [
        subprocess.run(
            [sys.executable, "-c", script, str(FIXTURE_PATH)],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        for _ in range(3)
    ]

    assert outputs[0] == outputs[1] == outputs[2]
    reports = [json.loads(output) for output in outputs]
    assert len({report["canonical_digest"] for report in reports}) == 1

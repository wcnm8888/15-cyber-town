"""Deterministic, metadata-only evaluation for F-008 synthetic fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from cyber_town.application.observability import (
    AttemptKind,
    ProviderKind,
    ScopeDimension,
    TerminalOutcome,
    TraceErrorCode,
    derive_scope_tag,
)
from cyber_town.domain.persona import load_bundled_personas

EVALUATOR_VERSION = "f-008-evaluator-v1"
FIXTURE_VERSION = "f-008-observability-fixture-v1"
EVALUATION_SCHEMA_VERSION = 1
_CASE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$")
_VERSION_PATTERN = re.compile(r"^[a-z0-9]+(?:[a-z0-9.-]*[a-z0-9])?$")
_METADATA_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EvaluationDimension(StrEnum):
    PERSONA_IDENTITY = "persona_identity"
    REPLY_OUTCOME = "reply_outcome"
    SHORT_TERM_ISOLATION = "short_term_isolation"
    PERSISTENT_ISOLATION = "persistent_isolation"
    ADVERSARIAL_INPUT = "adversarial_input"
    IDEMPOTENCY_CONCURRENCY = "idempotency_concurrency"
    CANCELLATION_LATE_RESULT = "cancellation_late_result"
    RECORDER_FAILURE = "recorder_failure"


class EvaluationFailureCode(StrEnum):
    NONE = "none"
    PERSONA_MISMATCH = "persona_mismatch"
    METADATA_MISMATCH = "metadata_mismatch"
    TRACE_INCOMPLETE = "trace_incomplete"
    STAGE_INCONSISTENT = "stage_inconsistent"
    SCOPE_LEAK = "scope_leak"
    FORBIDDEN_CONTENT = "forbidden_content"
    PROVIDER_ATTRIBUTION = "provider_attribution"
    COST_NONZERO = "cost_nonzero"
    BUSINESS_SEMANTICS_CHANGED = "business_semantics_changed"


def _require_nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Invalid {field_name}")
    return value


def _require_exact_keys(payload: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(payload) != expected:
        raise ValueError(f"Invalid {label} members")


@dataclass(frozen=True, slots=True)
class PersonaContract:
    npc_id: str
    version: str
    content_sha256: str

    def __post_init__(self) -> None:
        if _CASE_ID_PATTERN.fullmatch(self.npc_id) is None:
            raise ValueError("Invalid persona identifier")
        if _VERSION_PATTERN.fullmatch(self.version) is None:
            raise ValueError("Invalid persona version")
        if _DIGEST_PATTERN.fullmatch(self.content_sha256) is None:
            raise ValueError("Invalid persona digest")


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    case_id: str
    persona_version: str | None
    terminal_outcome: str
    error_code: str
    provider_kind: str
    attempt_kind: str
    trace_count: int
    terminal_trace_count: int
    stage_count: int
    stage_sequence_valid: bool
    scope_leak_count: int
    forbidden_content_hit_count: int
    provider_dispatch_count: int
    execution_count: int
    provider_attribution_error_count: int
    cost_microunits: int
    business_semantics_changed: bool
    metadata_counts: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if _CASE_ID_PATTERN.fullmatch(self.case_id) is None or len(self.case_id) > 64:
            raise ValueError("Invalid evaluation case identifier")
        if self.persona_version is not None and (
            _VERSION_PATTERN.fullmatch(self.persona_version) is None
            or len(self.persona_version) > 64
        ):
            raise ValueError("Invalid evaluation persona version")
        if self.terminal_outcome not in TerminalOutcome:
            raise ValueError("Invalid terminal outcome")
        if self.error_code not in TraceErrorCode:
            raise ValueError("Invalid trace error code")
        if self.provider_kind not in ProviderKind:
            raise ValueError("Invalid provider kind")
        if self.attempt_kind not in AttemptKind:
            raise ValueError("Invalid attempt kind")
        for field_name in (
            "trace_count",
            "terminal_trace_count",
            "stage_count",
            "scope_leak_count",
            "forbidden_content_hit_count",
            "provider_dispatch_count",
            "execution_count",
            "provider_attribution_error_count",
            "cost_microunits",
        ):
            _require_nonnegative_integer(getattr(self, field_name), field_name)
        if not isinstance(self.stage_sequence_valid, bool):
            raise TypeError("Invalid stage sequence flag")
        if not isinstance(self.business_semantics_changed, bool):
            raise TypeError("Invalid business semantics flag")
        metadata_keys: set[str] = set()
        for key, value in self.metadata_counts:
            if _METADATA_KEY_PATTERN.fullmatch(key) is None or key in metadata_keys:
                raise ValueError("Invalid metadata count key")
            metadata_keys.add(key)
            _require_nonnegative_integer(value, "metadata count")
        if tuple(sorted(self.metadata_counts)) != self.metadata_counts:
            raise ValueError("Metadata counts must use canonical order")


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    dimension: EvaluationDimension
    expected: EvaluationObservation

    def __post_init__(self) -> None:
        if self.case_id != self.expected.case_id:
            raise ValueError("Evaluation case identity mismatch")


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    schema_version: int
    fixture_version: str
    personas: tuple[PersonaContract, ...]
    cases: tuple[EvaluationCase, ...]


@dataclass(frozen=True, slots=True)
class CaseVerdict:
    case_id: str
    dimension: EvaluationDimension
    passed: bool
    failure_code: EvaluationFailureCode

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "dimension": self.dimension.value,
            "passed": self.passed,
            "failure_code": self.failure_code.value,
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    evaluator_version: str
    fixture_version: str
    schema_version: int
    case_count: int
    passed_count: int
    failed_count: int
    trace_completeness_ppm: int
    stage_consistency_ppm: int
    scope_leak_count: int
    forbidden_content_hit_count: int
    provider_attribution_error_count: int
    nonzero_cost_case_count: int
    verdicts: tuple[CaseVerdict, ...]
    canonical_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "evaluator_version": self.evaluator_version,
            "fixture_version": self.fixture_version,
            "schema_version": self.schema_version,
            "case_count": self.case_count,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "trace_completeness_ppm": self.trace_completeness_ppm,
            "stage_consistency_ppm": self.stage_consistency_ppm,
            "scope_leak_count": self.scope_leak_count,
            "forbidden_content_hit_count": self.forbidden_content_hit_count,
            "provider_attribution_error_count": self.provider_attribution_error_count,
            "nonzero_cost_case_count": self.nonzero_cost_case_count,
            "verdicts": [verdict.as_dict() for verdict in self.verdicts],
            "canonical_digest": self.canonical_digest,
        }


@dataclass(frozen=True, slots=True)
class SyntheticReplayResult:
    evaluator_version: str
    fixture_version: str
    schema_version: int
    case_id: str
    dimension: EvaluationDimension
    passed: bool
    failure_code: EvaluationFailureCode
    canonical_digest: str

    def as_dict(self) -> dict[str, object]:
        return {
            "evaluator_version": self.evaluator_version,
            "fixture_version": self.fixture_version,
            "schema_version": self.schema_version,
            "case_id": self.case_id,
            "dimension": self.dimension.value,
            "passed": self.passed,
            "failure_code": self.failure_code.value,
            "canonical_digest": self.canonical_digest,
        }


_TOP_LEVEL_KEYS = {"schema_version", "fixture_version", "personas", "cases"}
_PERSONA_KEYS = {"npc_id", "version", "content_sha256"}
_CASE_KEYS = {
    "case_id",
    "dimension",
    "persona_version",
    "terminal_outcome",
    "error_code",
    "provider_kind",
    "attempt_kind",
    "trace_count",
    "terminal_trace_count",
    "stage_count",
    "stage_sequence_valid",
    "scope_leak_count",
    "forbidden_content_hit_count",
    "provider_dispatch_count",
    "execution_count",
    "provider_attribution_error_count",
    "cost_microunits",
    "business_semantics_changed",
    "metadata_counts",
}


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate fixture member")
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {label}")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise ValueError(f"Invalid {label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Invalid {label}")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"Invalid {label}")
    return value


def _parse_metadata_counts(value: object) -> tuple[tuple[str, int], ...]:
    payload = _mapping(value, "metadata counts")
    counts = tuple(
        sorted(
            (
                _text(key, "metadata count key"),
                _require_nonnegative_integer(count, "metadata count"),
            )
            for key, count in payload.items()
        )
    )
    return counts


def _parse_persona(value: object) -> PersonaContract:
    payload = _mapping(value, "persona contract")
    _require_exact_keys(payload, _PERSONA_KEYS, "persona contract")
    return PersonaContract(
        npc_id=_text(payload["npc_id"], "persona identifier"),
        version=_text(payload["version"], "persona version"),
        content_sha256=_text(payload["content_sha256"], "persona digest"),
    )


def _parse_case(value: object) -> EvaluationCase:
    payload = _mapping(value, "evaluation case")
    _require_exact_keys(payload, _CASE_KEYS, "evaluation case")
    case_id = _text(payload["case_id"], "case identifier")
    try:
        dimension = EvaluationDimension(_text(payload["dimension"], "dimension"))
    except ValueError as error:
        raise ValueError("Invalid evaluation dimension") from error
    persona_version_raw = payload["persona_version"]
    if persona_version_raw is not None and not isinstance(persona_version_raw, str):
        raise ValueError("Invalid expected persona version")
    observation = EvaluationObservation(
        case_id=case_id,
        persona_version=persona_version_raw,
        terminal_outcome=_text(payload["terminal_outcome"], "terminal outcome"),
        error_code=_text(payload["error_code"], "error code"),
        provider_kind=_text(payload["provider_kind"], "provider kind"),
        attempt_kind=_text(payload["attempt_kind"], "attempt kind"),
        trace_count=_require_nonnegative_integer(payload["trace_count"], "trace count"),
        terminal_trace_count=_require_nonnegative_integer(
            payload["terminal_trace_count"], "terminal trace count"
        ),
        stage_count=_require_nonnegative_integer(payload["stage_count"], "stage count"),
        stage_sequence_valid=_boolean(payload["stage_sequence_valid"], "stage sequence"),
        scope_leak_count=_require_nonnegative_integer(
            payload["scope_leak_count"], "scope leak count"
        ),
        forbidden_content_hit_count=_require_nonnegative_integer(
            payload["forbidden_content_hit_count"], "forbidden content hit count"
        ),
        provider_dispatch_count=_require_nonnegative_integer(
            payload["provider_dispatch_count"], "provider dispatch count"
        ),
        execution_count=_require_nonnegative_integer(payload["execution_count"], "execution count"),
        provider_attribution_error_count=_require_nonnegative_integer(
            payload["provider_attribution_error_count"], "provider attribution error count"
        ),
        cost_microunits=_require_nonnegative_integer(payload["cost_microunits"], "cost microunits"),
        business_semantics_changed=_boolean(
            payload["business_semantics_changed"], "business semantics flag"
        ),
        metadata_counts=_parse_metadata_counts(payload["metadata_counts"]),
    )
    return EvaluationCase(case_id=case_id, dimension=dimension, expected=observation)


def load_evaluation_fixture(path: Path) -> EvaluationFixture:
    """Load one strict checked-in fixture and verify its persona digests."""

    if not isinstance(path, Path):
        raise TypeError("Fixture path type is invalid")
    raw = path.read_text(encoding="utf-8")
    payload = json.loads(raw, object_pairs_hook=_reject_duplicate_members)
    root = _mapping(payload, "evaluation fixture")
    _require_exact_keys(root, _TOP_LEVEL_KEYS, "evaluation fixture")
    schema_version = _require_nonnegative_integer(root["schema_version"], "schema version")
    if schema_version != EVALUATION_SCHEMA_VERSION:
        raise ValueError("Unsupported evaluation schema version")
    fixture_version = _text(root["fixture_version"], "fixture version")
    if fixture_version != FIXTURE_VERSION:
        raise ValueError("Unsupported evaluation fixture version")
    personas = tuple(_parse_persona(item) for item in _sequence(root["personas"], "personas"))
    cases = tuple(_parse_case(item) for item in _sequence(root["cases"], "cases"))
    if not personas or len({persona.npc_id for persona in personas}) != len(personas):
        raise ValueError("Invalid persona contract set")
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Invalid evaluation case set")
    if {case.dimension for case in cases} != set(EvaluationDimension):
        raise ValueError("Incomplete evaluation dimension set")

    bundled = load_bundled_personas()
    expected_personas = {
        (persona.npc_id, persona.version, persona.content_sha256) for persona in personas
    }
    actual_personas = {
        (persona.npc_id, persona.version, persona.content_sha256) for persona in bundled.values()
    }
    if expected_personas != actual_personas:
        raise ValueError("Persona contract does not match the bundled registry")
    return EvaluationFixture(
        schema_version=schema_version,
        fixture_version=fixture_version,
        personas=personas,
        cases=cases,
    )


def build_baseline_observations(
    fixture: EvaluationFixture,
) -> tuple[EvaluationObservation, ...]:
    """Build immutable synthetic observations for deterministic framework checks."""

    if not isinstance(fixture, EvaluationFixture):
        raise TypeError("Evaluation fixture type is invalid")
    return tuple(case.expected for case in fixture.cases)


def _failure_for(case: EvaluationCase, observation: EvaluationObservation) -> EvaluationFailureCode:
    expected = case.expected
    if observation.persona_version != expected.persona_version:
        return EvaluationFailureCode.PERSONA_MISMATCH
    metadata_fields = (
        "terminal_outcome",
        "error_code",
        "provider_kind",
        "attempt_kind",
        "provider_dispatch_count",
        "execution_count",
        "metadata_counts",
    )
    if any(getattr(observation, field) != getattr(expected, field) for field in metadata_fields):
        return EvaluationFailureCode.METADATA_MISMATCH
    if (
        observation.trace_count != expected.trace_count
        or observation.terminal_trace_count != observation.trace_count
    ):
        return EvaluationFailureCode.TRACE_INCOMPLETE
    if observation.stage_count != expected.stage_count or not observation.stage_sequence_valid:
        return EvaluationFailureCode.STAGE_INCONSISTENT
    if observation.scope_leak_count != 0:
        return EvaluationFailureCode.SCOPE_LEAK
    if observation.forbidden_content_hit_count != 0:
        return EvaluationFailureCode.FORBIDDEN_CONTENT
    if observation.provider_attribution_error_count != 0:
        return EvaluationFailureCode.PROVIDER_ATTRIBUTION
    if observation.cost_microunits != 0:
        return EvaluationFailureCode.COST_NONZERO
    if observation.business_semantics_changed:
        return EvaluationFailureCode.BUSINESS_SEMANTICS_CHANGED
    return EvaluationFailureCode.NONE


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def evaluate_observability(
    fixture: EvaluationFixture,
    observations: Sequence[EvaluationObservation],
    scope_key: bytes,
) -> EvaluationReport:
    """Evaluate safe metadata and return a deterministic allowlisted report."""

    if not isinstance(fixture, EvaluationFixture):
        raise TypeError("Evaluation fixture type is invalid")
    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise TypeError("Evaluation observations type is invalid")
    observed_by_case: dict[str, EvaluationObservation] = {}
    for observation in observations:
        if not isinstance(observation, EvaluationObservation):
            raise TypeError("Evaluation observation type is invalid")
        if observation.case_id in observed_by_case:
            raise ValueError("Duplicate evaluation observation")
        observed_by_case[observation.case_id] = observation
    expected_case_ids = {case.case_id for case in fixture.cases}
    if set(observed_by_case) != expected_case_ids:
        raise ValueError("Evaluation observation set mismatch")

    verdicts = tuple(
        CaseVerdict(
            case_id=case.case_id,
            dimension=case.dimension,
            passed=(failure := _failure_for(case, observed_by_case[case.case_id]))
            is EvaluationFailureCode.NONE,
            failure_code=failure,
        )
        for case in fixture.cases
    )
    trace_count = sum(observed_by_case[case.case_id].trace_count for case in fixture.cases)
    terminal_trace_count = sum(
        min(
            observed_by_case[case.case_id].terminal_trace_count,
            observed_by_case[case.case_id].trace_count,
        )
        for case in fixture.cases
    )
    consistent_stage_count = sum(
        observed_by_case[case.case_id].stage_count == case.expected.stage_count
        and observed_by_case[case.case_id].stage_sequence_valid
        for case in fixture.cases
    )
    passed_count = sum(verdict.passed for verdict in verdicts)
    trace_completeness_ppm = terminal_trace_count * 1_000_000 // trace_count if trace_count else 0
    stage_consistency_ppm = consistent_stage_count * 1_000_000 // len(fixture.cases)
    scope_leak_count = sum(
        observed_by_case[case.case_id].scope_leak_count for case in fixture.cases
    )
    forbidden_content_hit_count = sum(
        observed_by_case[case.case_id].forbidden_content_hit_count for case in fixture.cases
    )
    provider_attribution_error_count = sum(
        observed_by_case[case.case_id].provider_attribution_error_count for case in fixture.cases
    )
    nonzero_cost_case_count = sum(
        observed_by_case[case.case_id].cost_microunits != 0 for case in fixture.cases
    )
    report_without_digest: dict[str, object] = {
        "evaluator_version": EVALUATOR_VERSION,
        "fixture_version": fixture.fixture_version,
        "schema_version": fixture.schema_version,
        "case_count": len(fixture.cases),
        "passed_count": passed_count,
        "failed_count": len(fixture.cases) - passed_count,
        "trace_completeness_ppm": trace_completeness_ppm,
        "stage_consistency_ppm": stage_consistency_ppm,
        "scope_leak_count": scope_leak_count,
        "forbidden_content_hit_count": forbidden_content_hit_count,
        "provider_attribution_error_count": provider_attribution_error_count,
        "nonzero_cost_case_count": nonzero_cost_case_count,
        "verdicts": [verdict.as_dict() for verdict in verdicts],
    }
    scope_tags = tuple(
        derive_scope_tag(key=scope_key, dimension=dimension, identifier=case.case_id)
        for case in fixture.cases
        for dimension in ScopeDimension
    )
    digest_preimage = {
        "report": report_without_digest,
        "synthetic_scope_tag_set": hashlib.sha256("".join(scope_tags).encode()).hexdigest(),
    }
    canonical_digest = hashlib.sha256(_canonical_json(digest_preimage)).hexdigest()
    return EvaluationReport(
        evaluator_version=EVALUATOR_VERSION,
        fixture_version=fixture.fixture_version,
        schema_version=fixture.schema_version,
        case_count=len(fixture.cases),
        passed_count=passed_count,
        failed_count=len(fixture.cases) - passed_count,
        trace_completeness_ppm=trace_completeness_ppm,
        stage_consistency_ppm=stage_consistency_ppm,
        scope_leak_count=scope_leak_count,
        forbidden_content_hit_count=forbidden_content_hit_count,
        provider_attribution_error_count=provider_attribution_error_count,
        nonzero_cost_case_count=nonzero_cost_case_count,
        verdicts=verdicts,
        canonical_digest=canonical_digest,
    )


def replay_synthetic_case(
    *,
    fixture: EvaluationFixture,
    case_id: str,
    scope_key: bytes,
) -> SyntheticReplayResult:
    """Replay exactly one checked-in synthetic case without payload materialization."""

    if not isinstance(fixture, EvaluationFixture):
        raise TypeError("Synthetic replay fixture type is invalid")
    if not isinstance(case_id, str):
        raise TypeError("Synthetic replay case type is invalid")
    case = next((candidate for candidate in fixture.cases if candidate.case_id == case_id), None)
    if case is None:
        raise ValueError("Synthetic replay case is unavailable")
    failure_code = _failure_for(case, case.expected)
    result_without_digest: dict[str, object] = {
        "evaluator_version": EVALUATOR_VERSION,
        "fixture_version": fixture.fixture_version,
        "schema_version": fixture.schema_version,
        "case_id": case.case_id,
        "dimension": case.dimension.value,
        "passed": failure_code is EvaluationFailureCode.NONE,
        "failure_code": failure_code.value,
    }
    scope_tags = tuple(
        derive_scope_tag(key=scope_key, dimension=dimension, identifier=case.case_id)
        for dimension in ScopeDimension
    )
    canonical_digest = hashlib.sha256(
        _canonical_json(
            {
                "result": result_without_digest,
                "synthetic_scope_tag_set": hashlib.sha256("".join(scope_tags).encode()).hexdigest(),
            }
        )
    ).hexdigest()
    return SyntheticReplayResult(
        evaluator_version=EVALUATOR_VERSION,
        fixture_version=fixture.fixture_version,
        schema_version=fixture.schema_version,
        case_id=case.case_id,
        dimension=case.dimension,
        passed=failure_code is EvaluationFailureCode.NONE,
        failure_code=failure_code,
        canonical_digest=canonical_digest,
    )

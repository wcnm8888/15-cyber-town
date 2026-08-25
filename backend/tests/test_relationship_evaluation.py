from __future__ import annotations

from cyber_town.application.relationship_evaluation import evaluate_relationship_policy


def test_relationship_policy_evaluation_is_exhaustive_and_has_no_violations() -> None:
    report = evaluate_relationship_policy()

    assert report.decision_cases == 2020
    assert report.cooldown_cases == 2020
    assert report.adversarial_cases == 24
    assert report.utc_boundary_cases == 2
    assert report.violations == ()

from __future__ import annotations

from cyber_town.application.multi_npc_evaluation import evaluate_multi_npc_isolation


def test_multi_npc_scope_property_evaluation_has_no_violations() -> None:
    report = evaluate_multi_npc_isolation()

    assert report.npc_cases == 3
    assert report.short_scope_cases == 60
    assert report.short_scope_pair_cases == 1770
    assert report.persistent_scope_cases == 12
    assert report.persistent_scope_pair_cases == 66
    assert report.cross_conversation_cases == 12
    assert report.adversarial_npc_id_cases == 20
    assert report.violations == ()

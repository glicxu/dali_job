from __future__ import annotations

import pytest

from app.modules.evaluation.phase5_evaluation import _pairwise_accuracy, evaluate_phase5_fixture


def test_phase5_evaluation_fixture_reproduces_scores_and_policy_boundaries() -> None:
    report = evaluate_phase5_fixture()

    assert report["passed"] is True
    assert report["case_count"] == 13
    assert report["case_pass_count"] == 13
    assert report["deterministic_reproduction_failures"] == []
    assert all(
        counts["passed"] == counts["total"]
        for counts in report["category_results"].values()
    )


def test_phase5_evaluation_measures_ordering_and_calibration_without_claiming_human_gate() -> None:
    report = evaluate_phase5_fixture()

    ranking = report["ranking_metrics"]
    assert ranking["pairwise_accuracy"] == 1.0
    assert ranking["mean_spearman_rank_correlation"] == pytest.approx(1.0)
    assert report["calibration_metrics"]["mean_absolute_error"] == pytest.approx(4.8)
    assert report["architecture_gates"] == {
        "deterministic_reproduction": True,
        "policy_conformance": True,
        "spearman_rank_correlation": True,
        "pairwise_accuracy": True,
        "calibration_mae": True,
    }
    assert report["human_adjudicated_set_count"] == 0
    assert report["rollout_decision_eligible"] is False


def test_pairwise_metric_does_not_credit_a_predicted_tie_as_correct_order() -> None:
    entries = [
        {"case_id": "better", "adjudicated_rank": 1, "predicted_score": 70},
        {"case_id": "worse", "adjudicated_rank": 2, "predicted_score": 70},
    ]
    assert _pairwise_accuracy(entries) == (0, 1)

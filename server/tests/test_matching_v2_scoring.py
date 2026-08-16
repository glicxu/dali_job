from __future__ import annotations

import pytest

from app.modules.matching_v2.scoring import (
    GateResult,
    PreferenceScoreItem,
    QualificationScoreItem,
    score_match,
)


def _reference_qualification_items() -> list[QualificationScoreItem]:
    return [
        QualificationScoreItem(
            requirement_id="shipping",
            importance="required",
            scoring_dimension="production_delivery",
            status="partially_met",
        ),
        QualificationScoreItem(
            requirement_id="language",
            importance="required",
            scoring_dimension="technical_skill",
            status="met_by_alternative",
        ),
        QualificationScoreItem(
            requirement_id="python",
            importance="optional",
            scoring_dimension="technical_skill",
            status="met",
        ),
    ]


def test_architecture_reference_fixture_returns_68_and_63() -> None:
    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=_reference_qualification_items(),
        preference_items=[
            PreferenceScoreItem(
                preference_key="compensation.minimum_base",
                importance="high",
                status="met",
            ),
            PreferenceScoreItem(
                preference_key="workplace_types",
                importance="high",
                status="conflict",
            ),
        ],
    )

    assert result.qualification_score == 68
    assert result.qualification_coverage == 1.0
    assert result.preference_score == 50
    assert result.preference_coverage == 1.0
    assert result.overall_score == 63
    assert result.recommendation == "consider"


def test_unsupported_role_track_pair_cannot_publish_scores() -> None:
    result = score_match(
        role_family="hardware_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=_reference_qualification_items(),
    )

    assert result.qualification_score is None
    assert result.overall_score is None
    assert result.recommendation == "needs_more_information"
    assert result.reason_codes == ["SCORING_POLICY_NOT_APPROVED"]


def test_unknown_job_level_uses_mid_policy_and_marks_result_provisional() -> None:
    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="unknown",
        level_confidence=0.2,
        qualification_items=_reference_qualification_items(),
    )

    assert result.qualification_score is not None
    assert result.level_policy_provisional is True
    assert "JOB_LEVEL_POLICY_PROVISIONAL" in result.reason_codes
    assert result.questions


def test_low_qualification_coverage_hides_public_scores() -> None:
    items = _reference_qualification_items()
    items[0] = items[0].model_copy(update={"status": "needs_clarification"})

    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=items,
    )

    assert result.qualification_coverage == pytest.approx(3.0 / 6.9)
    assert result.diagnostic_qualification_score == 40
    assert result.qualification_score is None
    assert result.overall_score is None
    assert result.recommendation == "needs_more_information"


def test_incomplete_preferences_do_not_change_overall_score() -> None:
    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=_reference_qualification_items(),
        preference_items=[
            PreferenceScoreItem(preference_key="known", importance="low", status="met"),
            PreferenceScoreItem(preference_key="unknown", importance="high", status="unknown"),
        ],
    )

    assert result.preference_score == 100
    assert result.preference_coverage == 0.25
    assert result.preference_state == "incomplete"
    assert result.overall_score == result.qualification_score == 68


def test_gate_precedence_does_not_rewrite_scores() -> None:
    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=_reference_qualification_items(),
        gates=[
            GateResult(
                constraint_key="work_authorization.US",
                owner="employer",
                status="violated",
                reason_code="USER_NOT_AUTHORIZED",
            ),
            GateResult(
                constraint_key="employment_type",
                owner="user",
                status="violated",
                reason_code="EMPLOYMENT_TYPE_NOT_ALLOWED",
            ),
        ],
    )

    assert result.qualification_score == 68
    assert result.overall_score == 68
    assert result.recommendation == "does_not_match_preferences"
    assert "USER_CONSTRAINT_VIOLATED" in result.reason_codes


def test_unknown_user_gate_keeps_qualification_score_but_disables_preference_blending() -> None:
    result = score_match(
        role_family="software_engineering",
        track="individual_contributor",
        target_level="senior",
        level_confidence=0.95,
        qualification_items=_reference_qualification_items(),
        preference_items=[
            PreferenceScoreItem(preference_key="workplace", importance="high", status="met")
        ],
        gates=[
            GateResult(
                constraint_key="employment_type",
                owner="user",
                status="unknown",
                reason_code="USER_CONSTRAINT_JOB_VALUE_UNKNOWN",
            )
        ],
    )

    assert result.preference_score == 100
    assert result.preference_state == "incomplete"
    assert result.overall_score == result.qualification_score == 68
    assert "USER_CONSTRAINT_UNKNOWN" in result.reason_codes
    assert result.questions

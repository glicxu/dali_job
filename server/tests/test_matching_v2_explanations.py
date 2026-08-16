from __future__ import annotations

from app.modules.matching_v2.explanations import render_match_explanation
from app.modules.matching_v2.preferences import PreferenceAssessmentItem
from app.modules.matching_v2.scoring import GateResult, score_match
from app.modules.matching_v2.schemas import QualificationItemResponse


def test_explanation_uses_only_validated_assessment_content() -> None:
    qualification = [
        QualificationItemResponse(
            requirement_id="req_python",
            status="met",
            confidence=0.98,
            evidence_refs=["resume:skills:1"],
            alternative_group_refs=[],
            alternative_policy_ref=None,
            reason="Python is demonstrated in production work.",
            missing=[],
        ),
        QualificationItemResponse(
            requirement_id="req_architecture",
            status="not_demonstrated",
            confidence=0.9,
            evidence_refs=[],
            alternative_group_refs=[],
            alternative_policy_ref=None,
            reason="Architecture scope is not demonstrated.",
            missing=["Evidence of system architecture ownership"],
        ),
    ]
    gate = GateResult(
        constraint_key="travel_percent",
        owner="employer",
        status="unknown",
        reason_code="USER_TRAVEL_AVAILABILITY_UNKNOWN",
    )
    preference = PreferenceAssessmentItem(
        preference_key="workplace_types",
        importance="high",
        status="conflict",
        reason_code="WORKPLACE_TYPES_CONFLICT",
    )
    score = score_match(
        role_family="unknown",
        track="unknown",
        target_level="unknown",
        level_confidence=0,
        qualification_items=[],
        gates=[gate],
    )

    explanation = render_match_explanation(
        qualification_items=qualification,
        requirement_statements={
            "req_python": "Python",
            "req_architecture": "Own distributed-system architecture",
        },
        preference_items=[preference],
        gates=[gate],
        score=score,
    )

    assert explanation.summary.startswith("More information")
    assert explanation.strengths[0].evidence_refs == ["resume:skills:1"]
    assert explanation.gaps[0].label == "Own distributed-system architecture"
    assert explanation.unknowns[0].detail == "USER_TRAVEL_AVAILABILITY_UNKNOWN"
    assert explanation.preference_conflicts[0].detail == "WORKPLACE_TYPES_CONFLICT"

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.modules.matching_v2.preferences import PreferenceAssessmentItem
from app.modules.matching_v2.scoring import DeterministicScoreResult, GateResult
from app.modules.matching_v2.schemas import QualificationItemResponse, StrictModel


class ExplanationItem(StrictModel):
    key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=1_000)
    detail: str = Field(min_length=1, max_length=1_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)


class MatchExplanation(StrictModel):
    summary: str = Field(min_length=1, max_length=1_000)
    strengths: list[ExplanationItem]
    gaps: list[ExplanationItem]
    unknowns: list[ExplanationItem]
    preference_conflicts: list[ExplanationItem]
    questions: list[str]
    renderer_version: Literal["match-explanation.v1"] = "match-explanation.v1"


_RECOMMENDATION_LABELS = {
    "strong_match": "This looks like a strong match based on the available evidence.",
    "good_match": "This looks like a good match based on the available evidence.",
    "consider": "This role is worth considering, with some meaningful gaps to review.",
    "stretch": "This appears to be a stretch role based on the available evidence.",
    "unlikely_fit": "This role is unlikely to fit the current profile.",
    "does_not_match_preferences": "This role conflicts with a confirmed job preference.",
    "needs_more_information": "More information is needed before a reliable recommendation can be made.",
}


def _requirement_label(requirement_id: str, statements: dict[str, str]) -> str:
    return statements.get(requirement_id, requirement_id)


def _gate_unknown(gate: GateResult) -> ExplanationItem:
    return ExplanationItem(
        key=gate.constraint_key,
        label=gate.constraint_key.replace("_", " ").replace(".", ": ").title(),
        detail=gate.reason_code,
        evidence_refs=[],
    )


def render_match_explanation(
    *,
    qualification_items: list[QualificationItemResponse],
    requirement_statements: dict[str, str],
    preference_items: list[PreferenceAssessmentItem],
    gates: list[GateResult],
    score: DeterministicScoreResult,
) -> MatchExplanation:
    """Render only validated statuses and reason codes; never invent evidence or scores."""

    strengths: list[ExplanationItem] = []
    gaps: list[ExplanationItem] = []
    for item in qualification_items:
        rendered = ExplanationItem(
            key=item.requirement_id,
            label=_requirement_label(item.requirement_id, requirement_statements),
            detail=item.reason,
            evidence_refs=item.evidence_refs,
        )
        if item.status in {"met", "met_by_alternative"}:
            strengths.append(rendered)
        else:
            gaps.append(rendered)

    conflicts = [
        ExplanationItem(
            key=item.preference_key,
            label=item.preference_key.replace("_", " ").replace(".", ": ").title(),
            detail=item.reason_code,
            evidence_refs=[],
        )
        for item in preference_items
        if item.status == "conflict"
    ]
    unknowns = [_gate_unknown(gate) for gate in gates if gate.status == "unknown"]
    return MatchExplanation(
        summary=_RECOMMENDATION_LABELS[score.recommendation],
        strengths=strengths,
        gaps=gaps,
        unknowns=unknowns,
        preference_conflicts=conflicts,
        questions=score.questions,
    )

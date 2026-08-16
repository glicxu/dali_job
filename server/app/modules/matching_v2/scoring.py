from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field

from app.modules.matching_v2.registry import ROLE_TRACK_POLICIES
from app.modules.matching_v2.schemas import RequirementDimension, StrictModel


QualificationScoreStatus = Literal[
    "met",
    "met_by_alternative",
    "partially_met",
    "not_demonstrated",
    "not_met",
    "needs_clarification",
    "not_applicable",
]
PreferenceScoreStatus = Literal["met", "partially_met", "conflict", "unknown", "not_applicable"]
GateOwner = Literal["employer", "user"]
GateStatus = Literal["satisfied", "violated", "unknown", "not_applicable"]
Recommendation = Literal[
    "strong_match",
    "good_match",
    "consider",
    "stretch",
    "unlikely_fit",
    "does_not_match_preferences",
    "needs_more_information",
]


class QualificationScoreItem(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    importance: Literal["required", "optional", "preferred", "informational"]
    scoring_dimension: RequirementDimension
    status: QualificationScoreStatus


class PreferenceScoreItem(StrictModel):
    preference_key: str = Field(min_length=1, max_length=200)
    importance: Literal["low", "medium", "high"]
    status: PreferenceScoreStatus


class GateResult(StrictModel):
    constraint_key: str = Field(min_length=1, max_length=200)
    owner: GateOwner
    status: GateStatus
    reason_code: str = Field(min_length=1, max_length=120)


class DeterministicScoreResult(StrictModel):
    qualification_score: int | None
    diagnostic_qualification_score: int | None
    qualification_coverage: float
    preference_score: int | None
    preference_coverage: float | None
    preference_state: Literal["configured", "incomplete", "not_configured"]
    overall_score: int | None
    recommendation: Recommendation
    gates: list[GateResult]
    reason_codes: list[str]
    questions: list[str]
    role_track_policy_version: str | None
    scoring_policy_version: Literal["score.v1"] = "score.v1"
    level_policy_provisional: bool


_QUALIFICATION_VALUES = {
    "met": Decimal("1.0"),
    "met_by_alternative": Decimal("0.9"),
    "partially_met": Decimal("0.5"),
    "not_demonstrated": Decimal("0.0"),
    "not_met": Decimal("0.0"),
}
_PREFERENCE_VALUES = {
    "met": Decimal("1.0"),
    "partially_met": Decimal("0.5"),
    "conflict": Decimal("0.0"),
}
_IMPORTANCE_WEIGHTS = {
    "required": Decimal("3"),
    "optional": Decimal("1"),
    "preferred": Decimal("1"),
    "informational": Decimal("0"),
}
_PREFERENCE_IMPORTANCE_WEIGHTS = {
    "low": Decimal("1"),
    "medium": Decimal("2"),
    "high": Decimal("3"),
}


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def recommendation_for_score(score: int) -> Recommendation:
    if score < 0 or score > 100:
        raise ValueError("score must be between 0 and 100")
    if score >= 85:
        return "strong_match"
    if score >= 70:
        return "good_match"
    if score >= 55:
        return "consider"
    if score >= 40:
        return "stretch"
    return "unlikely_fit"


def _score_preferences(
    items: list[PreferenceScoreItem],
) -> tuple[int | None, float | None, Literal["configured", "incomplete", "not_configured"]]:
    applicable = [item for item in items if item.status != "not_applicable"]
    if not applicable:
        return None, None, "not_configured"

    total_weight = sum((_PREFERENCE_IMPORTANCE_WEIGHTS[item.importance] for item in applicable), Decimal(0))
    known = [item for item in applicable if item.status in _PREFERENCE_VALUES]
    known_weight = sum((_PREFERENCE_IMPORTANCE_WEIGHTS[item.importance] for item in known), Decimal(0))
    coverage = known_weight / total_weight if total_weight else Decimal(0)
    if not known_weight:
        return None, float(coverage), "incomplete"

    numerator = sum(
        (
            _PREFERENCE_IMPORTANCE_WEIGHTS[item.importance] * _PREFERENCE_VALUES[item.status]
            for item in known
        ),
        Decimal(0),
    )
    score = _round_half_up(Decimal(100) * numerator / known_weight)
    state: Literal["configured", "incomplete", "not_configured"] = (
        "configured" if coverage >= Decimal("0.60") else "incomplete"
    )
    return score, float(coverage), state


def score_match(
    *,
    role_family: str,
    track: str,
    target_level: str,
    level_confidence: float,
    qualification_items: list[QualificationScoreItem],
    preference_items: list[PreferenceScoreItem] | None = None,
    gates: list[GateResult] | None = None,
) -> DeterministicScoreResult:
    """Apply score.v1 without model calls or mutable external state."""

    reasons: list[str] = []
    questions: list[str] = []
    gate_items = gates or []
    policy = ROLE_TRACK_POLICIES.resolve_public(role_family, track)
    level_policy_provisional = target_level == "unknown" or level_confidence < 0.70
    scoring_level = "mid" if level_policy_provisional else target_level

    diagnostic_score: int | None = None
    diagnostic_score_decimal: Decimal | None = None
    coverage = Decimal(0)
    if policy is None:
        reasons.append("SCORING_POLICY_NOT_APPROVED")
    else:
        multipliers = policy.content["multipliers"]
        if scoring_level not in multipliers:
            scoring_level = "mid"
            level_policy_provisional = True
        if level_policy_provisional:
            reasons.append("JOB_LEVEL_POLICY_PROVISIONAL")
            questions.append("What career level does this job actually target?")

        denominator = Decimal(0)
        assessed_weight = Decimal(0)
        numerator = Decimal(0)
        for item in qualification_items:
            if item.status == "not_applicable":
                continue
            base_weight = _IMPORTANCE_WEIGHTS[item.importance]
            if not base_weight:
                continue
            multiplier = Decimal(str(multipliers[scoring_level][item.scoring_dimension]))
            weight = base_weight * multiplier
            denominator += weight
            status_value = _QUALIFICATION_VALUES.get(item.status)
            if status_value is not None:
                assessed_weight += weight
                numerator += weight * status_value

        if denominator:
            coverage = assessed_weight / denominator
            diagnostic_score_decimal = Decimal(100) * numerator / denominator
            diagnostic_score = _round_half_up(diagnostic_score_decimal)
        else:
            reasons.append("NO_RELEVANT_REQUIREMENTS")

    qualification_score = diagnostic_score
    if policy is None or diagnostic_score is None or coverage < Decimal("0.80"):
        qualification_score = None
        if diagnostic_score is not None and coverage < Decimal("0.80"):
            reasons.append("QUALIFICATION_COVERAGE_BELOW_THRESHOLD")

    preference_score, preference_coverage, preference_state = _score_preferences(preference_items or [])
    user_constraint_unknown = any(
        item.owner == "user" and item.status == "unknown" for item in gate_items
    )
    if user_constraint_unknown:
        preference_state = "incomplete"
        reasons.append("USER_CONSTRAINT_UNKNOWN")
        questions.append("Can you confirm the job preference needed for this role?")
    if preference_state == "incomplete":
        reasons.append("PREFERENCES_INCOMPLETE")

    overall_score: int | None = qualification_score
    if (
        qualification_score is not None
        and preference_score is not None
        and preference_coverage is not None
        and preference_coverage >= 0.60
        and preference_state == "configured"
    ):
        overall_score = _round_half_up(
            Decimal("0.70") * diagnostic_score_decimal
            + Decimal("0.30") * Decimal(preference_score)
        )

    recommendation: Recommendation = (
        recommendation_for_score(overall_score)
        if overall_score is not None
        else "needs_more_information"
    )

    if any(item.owner == "user" and item.status == "violated" for item in gate_items):
        recommendation = "does_not_match_preferences"
        reasons.append("USER_CONSTRAINT_VIOLATED")
    elif any(item.owner == "employer" and item.status == "violated" for item in gate_items):
        if recommendation not in {"needs_more_information", "unlikely_fit"}:
            recommendation = "unlikely_fit"
        reasons.append("EMPLOYER_CONSTRAINT_VIOLATED")
    elif (
        recommendation in {"strong_match", "good_match", "consider"}
        and any(item.owner == "employer" and item.status == "unknown" for item in gate_items)
    ):
        recommendation = "needs_more_information"
        reasons.append("EMPLOYER_CONSTRAINT_UNKNOWN")

    return DeterministicScoreResult(
        qualification_score=qualification_score,
        diagnostic_qualification_score=diagnostic_score,
        qualification_coverage=float(coverage),
        preference_score=preference_score,
        preference_coverage=preference_coverage,
        preference_state=preference_state,
        overall_score=overall_score,
        recommendation=recommendation,
        gates=gate_items,
        reason_codes=list(dict.fromkeys(reasons)),
        questions=questions,
        role_track_policy_version=policy.version if policy is not None else None,
        level_policy_provisional=level_policy_provisional,
    )

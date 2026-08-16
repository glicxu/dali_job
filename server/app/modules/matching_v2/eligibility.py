from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.modules.matching_v2.scoring import GateResult
from app.modules.matching_v2.schemas import JobApplicationConstraintsResponse, StrictModel


class WorkAuthorizationFact(StrictModel):
    country: str = Field(min_length=2, max_length=2)
    status: Literal["authorized", "not_authorized", "unknown"]
    requires_sponsorship: bool | None


class CandidateEligibilityFacts(StrictModel):
    work_authorizations: list[WorkAuthorizationFact] = Field(default_factory=list, max_length=50)
    clearances: list[str] | None = Field(default=None, max_length=30)
    licenses: list[str] | None = Field(default=None, max_length=30)
    travel_availability_percent: float | None = Field(default=None, ge=0, le=100)
    relocation: Literal["yes", "maybe", "no", "unknown"] = "unknown"


class EligibilityAssessmentResult(StrictModel):
    items: list[GateResult]
    policy_version: Literal["eligibility-policy.v1"] = "eligibility-policy.v1"


def evaluate_eligibility(
    constraints: JobApplicationConstraintsResponse,
    facts: CandidateEligibilityFacts | None,
    *,
    job_country: str | None,
) -> EligibilityAssessmentResult:
    """Evaluate only employer-stated application constraints; absence stays unknown."""

    items: list[GateResult] = []
    normalized_country = job_country.upper() if job_country else None

    if constraints.work_authorization != "unknown":
        fact = None
        if facts is not None and normalized_country is not None:
            fact = next(
                (item for item in facts.work_authorizations if item.country.upper() == normalized_country),
                None,
            )
        if constraints.work_authorization == "not_required":
            status = "satisfied"
            reason = "EMPLOYER_AUTHORIZATION_NOT_REQUIRED"
        elif fact is None or fact.status == "unknown":
            status = "unknown"
            reason = "USER_WORK_AUTHORIZATION_UNKNOWN"
        elif fact.status == "authorized":
            status = "satisfied"
            reason = "USER_WORK_AUTHORIZED"
        else:
            status = "violated"
            reason = "USER_NOT_WORK_AUTHORIZED"
        items.append(
            GateResult(
                constraint_key=f"work_authorization.{normalized_country or 'unknown'}",
                owner="employer",
                status=status,
                reason_code=reason,
            )
        )

    if constraints.sponsorship_available != "unknown":
        fact = None
        if facts is not None and normalized_country is not None:
            fact = next(
                (item for item in facts.work_authorizations if item.country.upper() == normalized_country),
                None,
            )
        if fact is None or fact.requires_sponsorship is None:
            status = "unknown"
            reason = "USER_SPONSORSHIP_NEED_UNKNOWN"
        elif not fact.requires_sponsorship:
            status = "satisfied"
            reason = "USER_SPONSORSHIP_NOT_REQUIRED"
        elif constraints.sponsorship_available == "available":
            status = "satisfied"
            reason = "EMPLOYER_SPONSORSHIP_AVAILABLE"
        else:
            status = "violated"
            reason = "SPONSORSHIP_REQUIRED_BUT_UNAVAILABLE"
        items.append(
            GateResult(
                constraint_key="sponsorship",
                owner="employer",
                status=status,
                reason_code=reason,
            )
        )

    if constraints.travel_percent is not None:
        availability = facts.travel_availability_percent if facts is not None else None
        if availability is None:
            status = "unknown"
            reason = "USER_TRAVEL_AVAILABILITY_UNKNOWN"
        elif availability >= constraints.travel_percent:
            status = "satisfied"
            reason = "USER_TRAVEL_AVAILABILITY_SUFFICIENT"
        else:
            status = "violated"
            reason = "USER_TRAVEL_AVAILABILITY_INSUFFICIENT"
        items.append(
            GateResult(
                constraint_key="travel_percent",
                owner="employer",
                status=status,
                reason_code=reason,
            )
        )

    if constraints.clearance is not None:
        if facts is None:
            status = "unknown"
            reason = "USER_CLEARANCE_UNKNOWN"
        elif facts.clearances is None:
            status = "unknown"
            reason = "USER_CLEARANCE_UNKNOWN"
        elif constraints.clearance.casefold().strip() in {
            clearance.casefold().strip() for clearance in facts.clearances
        }:
            status = "satisfied"
            reason = "USER_CLEARANCE_CONFIRMED"
        else:
            status = "violated"
            reason = "REQUIRED_CLEARANCE_NOT_CONFIRMED"
        items.append(
            GateResult(
                constraint_key="clearance",
                owner="employer",
                status=status,
                reason_code=reason,
            )
        )

    return EligibilityAssessmentResult(items=items)

from __future__ import annotations

from app.modules.matching_v2.eligibility import (
    CandidateEligibilityFacts,
    WorkAuthorizationFact,
    evaluate_eligibility,
)
from app.modules.matching_v2.schemas import JobApplicationConstraintsResponse


def _constraints() -> JobApplicationConstraintsResponse:
    return JobApplicationConstraintsResponse(
        work_authorization="required",
        sponsorship_available="unavailable",
        travel_percent=25,
        clearance="Secret",
    )


def test_eligibility_evaluator_emits_one_gate_per_material_constraint() -> None:
    facts = CandidateEligibilityFacts(
        work_authorizations=[
            WorkAuthorizationFact(country="US", status="authorized", requires_sponsorship=False)
        ],
        clearances=["Secret"],
        travel_availability_percent=30,
    )

    result = evaluate_eligibility(_constraints(), facts, job_country="US")

    assert [item.constraint_key for item in result.items] == [
        "work_authorization.US",
        "sponsorship",
        "travel_percent",
        "clearance",
    ]
    assert all(item.status == "satisfied" for item in result.items)


def test_missing_user_facts_stay_unknown() -> None:
    result = evaluate_eligibility(_constraints(), None, job_country="US")

    assert all(item.status == "unknown" for item in result.items)


def test_confirmed_ineligibility_is_a_violation() -> None:
    facts = CandidateEligibilityFacts(
        work_authorizations=[
            WorkAuthorizationFact(country="US", status="not_authorized", requires_sponsorship=True)
        ],
        clearances=[],
        travel_availability_percent=10,
    )

    result = evaluate_eligibility(_constraints(), facts, job_country="US")

    assert {item.constraint_key for item in result.items if item.status == "violated"} == {
        "work_authorization.US",
        "sponsorship",
        "travel_percent",
        "clearance",
    }

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.matching_v2.preferences import (
    CompensationPreferences,
    DesiredValue,
    EmploymentTypePreferences,
    JobPreferenceFacts,
    LocationPreferences,
    UserHardConstraint,
    UserPreferences,
    WorkplacePreference,
    evaluate_preferences,
)


def test_preference_categories_are_deterministic_and_do_not_double_count_lists() -> None:
    preferences = UserPreferences(
        desired_roles=[DesiredValue(value="software_engineering", importance="high")],
        locations=LocationPreferences(
            allowed=["Remote-US"], relocation="no", maximum_commute_minutes=45, importance="high"
        ),
        workplace_types=[
            WorkplacePreference(value="remote", preference="strongly_prefer", importance="high"),
            WorkplacePreference(value="onsite", preference="avoid", importance="high"),
        ],
        compensation=CompensationPreferences(
            minimum_base=100_000,
            target_base=130_000,
            currency="USD",
            period="year",
            importance="high",
        ),
        employment_types=EmploymentTypePreferences(allowed=["full_time"], importance="high"),
        desired_skills=[DesiredValue(value="Python", importance="medium")],
        avoided_industries=[
            DesiredValue(value="tobacco", importance="high"),
            DesiredValue(value="gambling", importance="medium"),
        ],
        hard_constraints=[
            UserHardConstraint(field="employment_type", operator="in", value=["full_time"])
        ],
    )
    job = JobPreferenceFacts(
        role_family="software_engineering",
        title="Senior Software Engineer",
        canonical_location="US",
        workplace_type="remote",
        remote_regions=["Remote-US"],
        compensation_currency="USD",
        compensation_period="year",
        compensation_minimum=105_000,
        compensation_maximum=120_000,
        employment_type="full_time",
        skills=["Python", "FastAPI"],
        industry="cloud computing",
    )

    result = evaluate_preferences(preferences, job)
    statuses = {item.preference_key: item.status for item in result.items}

    assert statuses == {
        "desired_roles": "met",
        "locations": "met",
        "workplace_types": "met",
        "compensation.minimum_base": "partially_met",
        "employment_types": "met",
        "desired_skills.python": "met",
        "avoided_industries": "met",
    }
    assert result.hard_constraint_results[0].status == "satisfied"


def test_missing_job_values_are_unknown_not_conflicts() -> None:
    preferences = UserPreferences(
        compensation=CompensationPreferences(
            minimum_base=100_000,
            target_base=120_000,
            currency="USD",
            period="year",
            importance="high",
        ),
        desired_skills=[DesiredValue(value="Rust", importance="high")],
    )
    job = JobPreferenceFacts(
        role_family="software_engineering",
        title="Engineer",
        workplace_type="unknown",
        relevant_skills_complete=False,
    )

    result = evaluate_preferences(preferences, job)

    assert [item.status for item in result.items] == ["unknown", "unknown"]


def test_duplicate_canonical_preferences_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate canonical values"):
        UserPreferences(
            desired_skills=[
                DesiredValue(value="Python", importance="high"),
                DesiredValue(value=" python ", importance="low"),
            ]
        )

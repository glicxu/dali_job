from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from app.modules.matching_v2.scoring import GateResult, PreferenceScoreItem
from app.modules.matching_v2.schemas import StrictModel


Importance = Literal["low", "medium", "high"]


class DesiredValue(StrictModel):
    value: str = Field(min_length=1, max_length=300)
    importance: Importance


class LocationPreferences(StrictModel):
    allowed: list[str] = Field(min_length=1, max_length=20)
    relocation: Literal["yes", "maybe", "no"]
    maximum_commute_minutes: int | None = Field(default=None, ge=0, le=300)
    importance: Importance


class WorkplacePreference(StrictModel):
    value: Literal["remote", "hybrid", "onsite"]
    preference: Literal["strongly_prefer", "accept", "avoid"]
    importance: Importance


class CompensationPreferences(StrictModel):
    minimum_base: float = Field(ge=0)
    target_base: float = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    period: Literal["hour", "day", "week", "month", "year"]
    importance: Importance

    @model_validator(mode="after")
    def validate_range(self) -> CompensationPreferences:
        if self.minimum_base > self.target_base:
            raise ValueError("minimum_base cannot exceed target_base")
        return self


class EmploymentTypePreferences(StrictModel):
    allowed: list[str] = Field(min_length=1, max_length=10)
    importance: Importance


class UserHardConstraint(StrictModel):
    field: Literal["employment_type", "workplace_type"]
    operator: Literal["in", "not_in"]
    value: list[str] = Field(min_length=1, max_length=10)


class UserPreferences(StrictModel):
    desired_roles: list[DesiredValue] = Field(default_factory=list, max_length=20)
    locations: LocationPreferences | None = None
    workplace_types: list[WorkplacePreference] = Field(default_factory=list, max_length=3)
    compensation: CompensationPreferences | None = None
    employment_types: EmploymentTypePreferences | None = None
    desired_skills: list[DesiredValue] = Field(default_factory=list, max_length=50)
    avoided_industries: list[DesiredValue] = Field(default_factory=list, max_length=30)
    hard_constraints: list[UserHardConstraint] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_unique_values(self) -> UserPreferences:
        collections = {
            "desired_roles": [item.value for item in self.desired_roles],
            "workplace_types": [item.value for item in self.workplace_types],
            "desired_skills": [item.value for item in self.desired_skills],
            "avoided_industries": [item.value for item in self.avoided_industries],
        }
        for name, values in collections.items():
            normalized = [value.casefold().strip() for value in values]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{name} cannot contain duplicate canonical values")
        return self


class JobPreferenceFacts(StrictModel):
    role_family: str
    title: str
    canonical_location: str | None = None
    workplace_type: Literal["remote", "hybrid", "onsite", "unknown"]
    remote_regions: list[str] = Field(default_factory=list)
    commute_minutes: dict[str, int] = Field(default_factory=dict)
    compensation_currency: str | None = None
    compensation_period: str | None = None
    compensation_minimum: float | None = None
    compensation_maximum: float | None = None
    employment_type: str = "unknown"
    skills: list[str] = Field(default_factory=list)
    industry: str | None = None
    relevant_skills_complete: bool = True


class PreferenceAssessmentItem(PreferenceScoreItem):
    reason_code: str = Field(min_length=1, max_length=120)


class PreferenceAssessmentResult(StrictModel):
    items: list[PreferenceAssessmentItem]
    hard_constraint_results: list[GateResult]
    policy_version: Literal["preference-policy.v2"] = "preference-policy.v2"


def _norm(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_term(term: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _item(key: str, importance: Importance, status: str) -> PreferenceAssessmentItem:
    normalized_key = re.sub(r"[^A-Z0-9]+", "_", key.upper()).strip("_")
    return PreferenceAssessmentItem(
        preference_key=key,
        importance=importance,
        status=status,
        reason_code=f"{normalized_key}_{status.upper()}",
    )


def evaluate_preferences(
    preferences: UserPreferences,
    job: JobPreferenceFacts,
    *,
    adjacent_role_families: set[tuple[str, str]] | None = None,
    related_skills: set[tuple[str, str]] | None = None,
) -> PreferenceAssessmentResult:
    items: list[PreferenceAssessmentItem] = []
    adjacent = {(_norm(left), _norm(right)) for left, right in (adjacent_role_families or set())}
    related = {(_norm(left), _norm(right)) for left, right in (related_skills or set())}

    if preferences.desired_roles:
        job_roles = {_norm(job.role_family), _norm(job.title)}
        candidates: list[tuple[int, int, str, DesiredValue, str]] = []
        rank = {"conflict": 0, "partially_met": 1, "met": 2}
        for desired in preferences.desired_roles:
            canonical = _norm(desired.value)
            if canonical in job_roles:
                status = "met"
            elif any((canonical, job_role) in adjacent or (job_role, canonical) in adjacent for job_role in job_roles):
                status = "partially_met"
            else:
                status = "conflict" if job.role_family != "unknown" else "unknown"
            importance_rank = {"low": 1, "medium": 2, "high": 3}[desired.importance]
            candidates.append((rank.get(status, -1), importance_rank, canonical, desired, status))
        _, _, _, selected, status = sorted(candidates, key=lambda row: (-row[0], -row[1], row[2]))[0]
        items.append(_item("desired_roles", selected.importance, status))

    if preferences.locations is not None:
        location = preferences.locations
        allowed = {_norm(value) for value in location.allowed}
        job_remote_regions = {_norm(value) for value in job.remote_regions}
        remote_match = job.workplace_type == "remote" and (
            "remote" in allowed or bool(allowed & job_remote_regions)
        )
        exact_match = job.canonical_location is not None and any(
            region in _norm(job.canonical_location) or _norm(job.canonical_location) in region
            for region in allowed
        )
        trusted_commutes = [job.commute_minutes[value] for value in job.commute_minutes if _norm(value) in allowed]
        if remote_match or exact_match:
            status = "met"
        elif trusted_commutes and location.maximum_commute_minutes is not None:
            if min(trusted_commutes) <= location.maximum_commute_minutes:
                status = "met"
            else:
                status = "partially_met" if location.relocation in {"yes", "maybe"} else "conflict"
        else:
            status = "unknown"
        items.append(_item("locations", location.importance, status))

    if preferences.workplace_types:
        configured = {item.value: item for item in preferences.workplace_types}
        selected = configured.get(job.workplace_type)  # type: ignore[arg-type]
        if selected is None:
            importance = max(
                preferences.workplace_types,
                key=lambda item: {"low": 1, "medium": 2, "high": 3}[item.importance],
            ).importance
            status = "unknown"
        else:
            importance = selected.importance
            status = "conflict" if selected.preference == "avoid" else "met"
        items.append(_item("workplace_types", importance, status))

    if preferences.compensation is not None:
        preference = preferences.compensation
        comparable = (
            job.compensation_maximum is not None
            and job.compensation_currency == preference.currency
            and job.compensation_period == preference.period
        )
        if not comparable:
            status = "unknown"
        elif job.compensation_maximum < preference.minimum_base:
            status = "conflict"
        elif job.compensation_maximum < preference.target_base:
            status = "partially_met"
        else:
            status = "met"
        items.append(_item("compensation.minimum_base", preference.importance, status))

    if preferences.employment_types is not None:
        preference = preferences.employment_types
        if job.employment_type == "unknown":
            status = "unknown"
        else:
            status = "met" if _norm(job.employment_type) in {_norm(value) for value in preference.allowed} else "conflict"
        items.append(_item("employment_types", preference.importance, status))

    job_skills = {_norm(skill) for skill in job.skills}
    for desired in preferences.desired_skills:
        skill = _norm(desired.value)
        if skill in job_skills or any(_contains_term(skill, job_skill) for job_skill in job_skills):
            status = "met"
        elif any((skill, job_skill) in related or (job_skill, skill) in related for job_skill in job_skills):
            status = "partially_met"
        else:
            status = "conflict" if job.relevant_skills_complete else "unknown"
        items.append(_item(f"desired_skills.{skill}", desired.importance, status))

    if preferences.avoided_industries:
        importance = max(
            preferences.avoided_industries,
            key=lambda item: {"low": 1, "medium": 2, "high": 3}[item.importance],
        ).importance
        if job.industry is None:
            status = "unknown"
        else:
            avoided = {_norm(item.value) for item in preferences.avoided_industries}
            status = "conflict" if _norm(job.industry) in avoided else "met"
        items.append(_item("avoided_industries", importance, status))

    gates: list[GateResult] = []
    job_values = {"employment_type": job.employment_type, "workplace_type": job.workplace_type}
    for constraint in preferences.hard_constraints:
        actual = _norm(job_values[constraint.field])
        expected = {_norm(value) for value in constraint.value}
        if actual == "unknown":
            status = "unknown"
            reason = "USER_CONSTRAINT_JOB_VALUE_UNKNOWN"
        else:
            allowed = actual in expected
            satisfied = allowed if constraint.operator == "in" else not allowed
            status = "satisfied" if satisfied else "violated"
            reason = "USER_CONSTRAINT_SATISFIED" if satisfied else "USER_CONSTRAINT_VIOLATED"
        gates.append(
            GateResult(
                constraint_key=constraint.field,
                owner="user",
                status=status,
                reason_code=reason,
            )
        )

    return PreferenceAssessmentResult(items=items, hard_constraint_results=gates)

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

CareerLevel = Literal[
    "unknown",
    "student_or_intern",
    "entry",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
]
CareerTrack = Literal[
    "individual_contributor",
    "architect",
    "engineering_management",
    "research",
    "technical_program",
    "technical_education",
    "unknown",
]
RoleFamily = Literal[
    "software_engineering",
    "data_science",
    "financial_technology",
    "technical_education",
    "product_management",
    "unknown",
]
EvidenceStrength = Literal["claimed", "demonstrated"]
EvidenceContext = Literal["professional", "academic", "personal", "open_source", "volunteer", "unknown"]
DimensionSignal = Literal["not_applicable", "not_demonstrated", "limited", "developing", "demonstrated", "advanced"]
RequirementDimension = Literal[
    "technical_skill",
    "applied_experience",
    "production_delivery",
    "system_design_architecture",
    "mentoring_leadership",
    "organizational_influence",
    "education_credential",
    "domain_knowledge",
]
QualificationStatus = Literal[
    "met",
    "met_by_alternative",
    "partially_met",
    "not_demonstrated",
    "not_met",
    "needs_clarification",
    "not_applicable",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidateSkillResponse(StrictModel):
    observed_name: str = Field(min_length=1, max_length=200)
    canonical_name: str | None = Field(max_length=200)
    evidence_strength: EvidenceStrength
    last_used: str | None = Field(max_length=10)
    months_experience: int | None = Field(ge=0, le=1_200)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CandidateExperienceResponse(StrictModel):
    organization: str | None = Field(max_length=300)
    title: str = Field(min_length=1, max_length=300)
    start_date: str | None = Field(max_length=10)
    end_date: str | None = Field(max_length=10)
    is_current: bool
    context: EvidenceContext
    highlights: list[str] = Field(max_length=20)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CandidateProjectResponse(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=1_000)
    technologies: list[str] = Field(max_length=30)
    context: EvidenceContext
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CandidateEducationResponse(StrictModel):
    institution: str | None = Field(max_length=300)
    credential: str = Field(min_length=1, max_length=300)
    field: str | None = Field(max_length=300)
    start_date: str | None = Field(max_length=10)
    end_date: str | None = Field(max_length=10)
    completed: bool | None
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CandidateCertificationResponse(StrictModel):
    name: str = Field(min_length=1, max_length=300)
    issuer: str | None = Field(max_length=300)
    issued_date: str | None = Field(max_length=10)
    expiration_date: str | None = Field(max_length=10)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CandidatePublicationResponse(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    venue: str | None = Field(max_length=300)
    publication_date: str | None = Field(max_length=10)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class CareerDimensionSignalsResponse(StrictModel):
    technical_depth: DimensionSignal
    production_delivery: DimensionSignal
    scope_and_complexity: DimensionSignal
    system_design: DimensionSignal
    ownership: DimensionSignal
    mentoring: DimensionSignal
    cross_team_influence: DimensionSignal


class CandidateCareerProfileResponse(StrictModel):
    local_ref: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    role_family: RoleFamily
    track: CareerTrack
    level: CareerLevel
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)
    dimension_signals: CareerDimensionSignalsResponse


class CandidateDerivedResponse(StrictModel):
    headline: str | None = Field(max_length=200)
    summary: str | None = Field(max_length=1_000)
    suggested_target_roles: list[str] = Field(max_length=5)


class ExtractionQualityResponse(StrictModel):
    warnings: list[str] = Field(max_length=20)
    completeness: float = Field(ge=0, le=1)


class CandidateExtractionResponse(StrictModel):
    skills: list[CandidateSkillResponse] = Field(max_length=100)
    experience: list[CandidateExperienceResponse] = Field(max_length=50)
    projects: list[CandidateProjectResponse] = Field(max_length=50)
    education: list[CandidateEducationResponse] = Field(max_length=30)
    certifications: list[CandidateCertificationResponse] = Field(max_length=30)
    publications: list[CandidatePublicationResponse] = Field(max_length=30)
    career_profiles: list[CandidateCareerProfileResponse] = Field(min_length=1, max_length=8)
    recommended_primary_career_profile_ref: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    derived: CandidateDerivedResponse
    quality: ExtractionQualityResponse

    @model_validator(mode="after")
    def validate_local_references(self) -> CandidateExtractionResponse:
        refs = [item.local_ref for item in self.career_profiles]
        if len(refs) != len(set(refs)):
            raise ValueError("Candidate career-profile local_ref values must be unique.")
        if self.recommended_primary_career_profile_ref not in refs:
            raise ValueError("The recommended primary career profile must reference a returned profile.")
        return self


class JobLocationResponse(StrictModel):
    display: str | None = Field(max_length=300)
    country: str | None = Field(max_length=2, pattern=r"^[A-Z]{2}$")
    region: str | None = Field(max_length=100)
    city: str | None = Field(max_length=200)
    workplace_type: Literal["remote", "hybrid", "onsite", "unknown"]
    remote_regions: list[str] = Field(max_length=20)


class CareerLevelRangeResponse(StrictModel):
    minimum: CareerLevel
    maximum: CareerLevel


class JobCareerContextResponse(StrictModel):
    primary_role_family: RoleFamily
    adjacent_role_families: list[RoleFamily] = Field(max_length=5)
    track: CareerTrack
    target_level: CareerLevel
    acceptable_level_range: CareerLevelRangeResponse | None
    level_source: Literal["explicit", "inferred_from_requirements", "unknown"]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1, max_length=10)


class JobCompensationResponse(StrictModel):
    currency: str | None = Field(max_length=3, pattern=r"^[A-Z]{3}$")
    period: Literal["hour", "day", "week", "month", "year", "unknown"]
    minimum: float | None = Field(ge=0)
    maximum: float | None = Field(ge=0)
    is_employer_provided: bool

    @model_validator(mode="after")
    def validate_range(self) -> JobCompensationResponse:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Compensation minimum cannot exceed maximum.")
        return self


class JobRequirementResponse(StrictModel):
    local_ref: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    category: Literal["skill", "experience", "education", "certification", "domain", "other"]
    scoring_dimension: RequirementDimension
    statement: str = Field(min_length=1, max_length=1_000)
    importance: Literal["required", "preferred", "informational"]
    hard_constraint: bool
    acceptable_evidence_contexts: list[EvidenceContext] = Field(max_length=6)
    minimum_years: float | None = Field(ge=0, le=100)
    explicit_alternatives: list[str] = Field(max_length=20)
    policy_alternative_group: str | None = Field(max_length=120)
    source_refs: list[str] = Field(min_length=1, max_length=10)


class JobResponsibilityResponse(StrictModel):
    statement: str = Field(min_length=1, max_length=1_000)
    source_refs: list[str] = Field(min_length=1, max_length=10)


class JobApplicationConstraintsResponse(StrictModel):
    work_authorization: Literal["required", "not_required", "unknown"]
    sponsorship_available: Literal["available", "unavailable", "unknown"]
    travel_percent: float | None = Field(ge=0, le=100)
    clearance: str | None = Field(max_length=200)


class JobCleanupResponse(StrictModel):
    duplicate_spans_removed: int = Field(ge=0)
    boilerplate_spans_ignored: int = Field(ge=0)
    warnings: list[str] = Field(max_length=20)


class JobExtractionResponse(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    company: str | None = Field(max_length=300)
    location: JobLocationResponse
    employment_type: Literal[
        "full_time",
        "part_time",
        "contract",
        "temporary",
        "internship",
        "unknown",
    ]
    career_context: JobCareerContextResponse
    compensation: JobCompensationResponse
    requirements: list[JobRequirementResponse] = Field(max_length=50)
    responsibilities: list[JobResponsibilityResponse] = Field(max_length=50)
    application_constraints: JobApplicationConstraintsResponse
    cleanup: JobCleanupResponse

    @model_validator(mode="after")
    def validate_requirement_references(self) -> JobExtractionResponse:
        refs = [item.local_ref for item in self.requirements]
        if len(refs) != len(set(refs)):
            raise ValueError("Job requirement local_ref values must be unique.")
        return self


class QualificationItemResponse(StrictModel):
    requirement_id: str = Field(min_length=1, max_length=100)
    status: QualificationStatus
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(max_length=10)
    alternative_policy_ref: str | None = Field(max_length=120)
    reason: str = Field(min_length=1, max_length=1_000)
    missing: list[str] = Field(max_length=10)


class QualificationAssessmentResponse(StrictModel):
    requirement_assessments: list[QualificationItemResponse] = Field(max_length=50)
    hard_constraint_assessments: list[QualificationItemResponse] = Field(max_length=50)


def normalized_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return deterministic JSON Schema generated from the Pydantic source of truth."""
    return _normalize_schema(model.model_json_schema(mode="validation"))


def strict_response_format(
    model: type[BaseModel],
    *,
    name: str,
    enum_restrictions: dict[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Build the provider JSON-schema envelope and optionally restrict request-scoped IDs."""
    schema = deepcopy(normalized_json_schema(model))
    for property_name, values in (enum_restrictions or {}).items():
        if not values:
            raise ValueError(f"Enum restriction for {property_name} cannot be empty.")
        replacements = _restrict_property(schema, property_name, sorted(set(values)))
        if replacements == 0:
            raise ValueError(f"Schema property not found for enum restriction: {property_name}")
    return {"name": name, "strict": True, "schema": schema}


def candidate_response_format(allowed_evidence_refs: Sequence[str]) -> dict[str, Any]:
    return strict_response_format(
        CandidateExtractionResponse,
        name="dalijob_candidate_extract_v1",
        enum_restrictions={"evidence_refs": allowed_evidence_refs},
    )


def job_response_format(allowed_source_refs: Sequence[str]) -> dict[str, Any]:
    return strict_response_format(
        JobExtractionResponse,
        name="dalijob_job_extract_v1",
        enum_restrictions={"source_refs": allowed_source_refs, "evidence_refs": allowed_source_refs},
    )


def qualification_response_format(
    *,
    allowed_requirement_ids: Sequence[str],
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    return strict_response_format(
        QualificationAssessmentResponse,
        name="dalijob_qualification_assessment_v1",
        enum_restrictions={
            "requirement_id": allowed_requirement_ids,
            "evidence_refs": allowed_evidence_refs,
        },
    )


def _normalize_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_schema(value[key]) for key in sorted(value) if key != "default"}
    if isinstance(value, list):
        return [_normalize_schema(item) for item in value]
    return value


def _restrict_property(value: Any, property_name: str, allowed_values: list[str]) -> int:
    replacements = 0
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict) and property_name in properties:
            target = properties[property_name]
            if target.get("type") == "array":
                target.setdefault("items", {})["enum"] = allowed_values
            else:
                target["enum"] = allowed_values
            replacements += 1
        for nested in value.values():
            replacements += _restrict_property(nested, property_name, allowed_values)
    elif isinstance(value, list):
        for nested in value:
            replacements += _restrict_property(nested, property_name, allowed_values)
    return replacements

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.matching_v2.schemas import (
    CandidateExtractionResponse,
    JobExtractionResponse,
    LegacyQualificationAssessmentResponse,
    QualificationAssessmentResponse,
)
from app.modules.matching_v2.eligibility import CandidateEligibilityFacts
from app.modules.matching_v2.preferences import UserPreferences


class CandidateProfileSourceResponse(BaseModel):
    source_id: str
    source_hash: str
    text_extraction_version: str
    canonicalization_version: str
    language: str


class CandidateCareerProfileView(BaseModel):
    career_profile_id: str
    local_ref: str
    role_family: str
    track: str
    level: str
    confidence: float
    evidence_refs: list[str]
    dimension_signals: dict[str, str]


class CandidateCareerSelectionView(BaseModel):
    revision: int
    primary_career_profile_id: str | None
    selection_source: str


class CandidateProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    candidate_profile_id: str
    resume_profile_id: int | None
    source: CandidateProfileSourceResponse
    extracted: CandidateExtractionResponse
    career_profiles: list[CandidateCareerProfileView]
    selection: CandidateCareerSelectionView
    generation: dict[str, str | None]
    created_at: datetime


class CandidateCareerSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    primary_career_profile_id: str | None = Field(max_length=64)


class JobProfileSourceResponse(BaseModel):
    source_id: str
    source_hash: str
    text_extraction_version: str
    canonicalization_version: str
    language: str


class JobRequirementView(BaseModel):
    requirement_id: str
    local_ref: str
    category: str
    scoring_dimension: str
    statement: str
    importance: str
    acceptable_evidence_contexts: list[str]
    minimum_years: float | None
    alternative_groups: list[dict[str, object]]
    policy_alternative_group: str | None
    source_refs: list[str]


class JobProfileView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_profile_id: str
    jobs_cache_id: int | None
    source: JobProfileSourceResponse
    extracted: JobExtractionResponse
    requirements: list[JobRequirementView]
    generation: dict[str, str | None]
    created_at: datetime


class QualificationAssessmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_profile_id: str = Field(min_length=1, max_length=64)
    candidate_career_selection_revision: int = Field(ge=1)
    job_profile_id: str = Field(min_length=1, max_length=64)


class QualificationCareerContextView(BaseModel):
    selection_revision: int
    selected_career_profile_id: str | None
    selection_policy_version: str
    selection_reason_code: str


class QualificationAssessmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    qualification_assessment_id: str
    candidate_profile_id: str
    job_profile_id: str
    career_context: QualificationCareerContextView
    assessment: QualificationAssessmentResponse | LegacyQualificationAssessmentResponse
    input_quality: dict
    generation: dict[str, str | dict | None]
    created_at: datetime


class PreferenceRevisionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    preferences: UserPreferences


class PreferenceRevisionView(BaseModel):
    revision: int
    preferences: UserPreferences
    created_at: datetime


class EligibilityRevisionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    facts: CandidateEligibilityFacts


class EligibilityRevisionView(BaseModel):
    revision: int
    facts: CandidateEligibilityFacts
    created_at: datetime


class MatchResultCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    qualification_assessment_id: str = Field(min_length=1, max_length=64)
    preference_revision: int | None = Field(default=None, ge=1)
    eligibility_revision: int | None = Field(default=None, ge=1)


class MatchResultView(BaseModel):
    match_id: str
    qualification_assessment_id: str
    preference_assessment_id: str | None
    eligibility_assessment_id: str | None
    scores: dict
    explanation: dict
    policy: dict
    legacy_score: int | None
    created_at: datetime


class MatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_profile_id: str = Field(min_length=1, max_length=64)
    candidate_career_selection_revision: int = Field(ge=1)
    job_profile_id: str = Field(min_length=1, max_length=64)
    preference_revision: int | None = Field(default=None, ge=1)
    eligibility_revision: int | None = Field(default=None, ge=1)
    mode: Literal["immediate", "asynchronous"] = "immediate"
    idempotency_key: str = Field(min_length=8, max_length=128)


class MatchRerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_profile_id: str | None = Field(default=None, min_length=1, max_length=64)
    candidate_career_selection_revision: int | None = Field(default=None, ge=1)
    preference_revision: int | None = Field(default=None, ge=1)
    eligibility_revision: int | None = Field(default=None, ge=1)
    mode: Literal["immediate", "asynchronous"] = "immediate"
    idempotency_key: str = Field(min_length=8, max_length=128)


class MatchingOperationStageView(BaseModel):
    stage: str
    status: str
    attempt_count: int
    max_attempts: int
    input_artifact_ids: dict
    output_artifact_id: str | None = None
    cache_hit: bool | None = None
    provider_usage: dict
    policy_versions: dict
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    completed_at: datetime | None = None


class MatchingOperationView(BaseModel):
    operation_id: str
    status: str
    current_stage: str | None = None
    correlation_id: str
    mode: Literal["immediate", "asynchronous"]
    match: MatchResultView | None = None
    stages: list[MatchingOperationStageView]
    error_code: str | None = None
    error_message: str | None = None
    poll_after_seconds: int | None = None
    created_at: datetime
    updated_at: datetime

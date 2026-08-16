from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.profiles.schemas import ProfileReadinessResponse, ResumeData


class GuestTrialCreateResponse(BaseModel):
    public_id: str
    guest_secret: str
    guest_credential: str
    status: str
    expires_at: datetime


class GuestProfileUpdateRequest(BaseModel):
    resume_data: ResumeData


class GuestProfileResponse(BaseModel):
    resume_data: ResumeData
    readiness: ProfileReadinessResponse
    created_at: datetime
    updated_at: datetime


class GuestResumeImportResponse(BaseModel):
    document_id: int
    file_name: str
    content_type: str
    size_bytes: int
    extracted_text_preview: str
    parse_status: str
    suggestions: ResumeData = Field(default_factory=ResumeData)
    requires_profile_confirmation: bool = True
    parse_warning: str | None = None


class GuestCriteriaUpdateRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)

    @field_validator("keyword", "location")
    @classmethod
    def normalize_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class GuestCriteriaResponse(BaseModel):
    keyword: str
    location: str
    created_at: datetime
    updated_at: datetime


class GuestTrialCurrentResponse(BaseModel):
    public_id: str
    status: str
    provider_search_state: str
    expires_at: datetime
    profile: GuestProfileResponse | None = None
    criteria: GuestCriteriaResponse | None = None
    resume_import: GuestResumeImportResponse | None = None


class GuestBestMatchResponse(BaseModel):
    title: str
    company: str
    location: str = ""
    source_url: str | None = None
    match_score: int | None = Field(default=None, ge=0, le=10)
    score_scale: str = "0-10"
    summary: str
    job_description: str = ""
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    supported_requirements: list[dict] = Field(default_factory=list)
    unsupported_requirements: list[dict] = Field(default_factory=list)
    recommended_resume_updates: list[str] = Field(default_factory=list)
    result_context: str = "Best usable match from this guest search"


class GuestMatchStatusResponse(BaseModel):
    operation_id: int | None = None
    status: str
    provider_search_state: str
    retryable: bool = False
    error_code: str | None = None
    result: GuestBestMatchResponse | None = None


class GuestClaimRequest(BaseModel):
    guest_credential: str = Field(min_length=20, max_length=512)


class GuestClaimResponse(BaseModel):
    status: str
    resume_profile_id: int
    search_criterion_id: int
    candidate_profile_id: str
    qualification_assessment_id: str

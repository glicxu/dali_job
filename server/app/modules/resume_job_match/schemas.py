from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.modules.jobs.schemas import JobDescriptionData


class ResumeJobMatchRequest(BaseModel):
    resume_text: str | None = Field(default=None)
    resume_profile_id: int | None = Field(default=None)
    resume_document_id: int | None = Field(default=None)
    job_description_text: str | None = Field(default=None)
    job_url: HttpUrl | None = Field(default=None)
    resume_data: dict[str, Any] | None = Field(default=None)
    job_data: dict[str, Any] | None = Field(default=None)

    @model_validator(mode="after")
    def require_resume_and_job_sources(self) -> ResumeJobMatchRequest:
        resume_sources = [
            bool(self.resume_profile_id),
            bool(self.resume_document_id),
            bool(self.resume_text and self.resume_text.strip()),
        ]
        if not any(resume_sources):
            raise ValueError("Provide resume_profile_id, resume_text, or resume_document_id.")
        if sum(resume_sources) > 1:
            raise ValueError("Provide only one resume source.")
        has_job_text = bool(self.job_description_text and self.job_description_text.strip())
        has_job_url = bool(self.job_url)
        if not has_job_text and not has_job_url and not self.job_data:
            raise ValueError("Provide job_description_text or job_url.")
        if has_job_text and has_job_url:
            raise ValueError("Provide either job_description_text or job_url, not both.")
        return self


class SupportedRequirement(BaseModel):
    requirement: str
    resume_evidence: str
    confidence: float = Field(..., ge=0, le=1)


class UnsupportedRequirement(BaseModel):
    requirement: str
    reason: str


class PendingMatchedJob(BaseModel):
    title: str
    company: str
    source_url: str | None = None
    raw_description_text: str
    job_data: JobDescriptionData
    notes: str | None = None
    match_score: int = Field(..., ge=0, le=10)
    matched_resume_profile_id: int | None = None
    matched_resume_document_id: int | None = None
    matched_resume_source: str
    match_data: dict[str, Any] = Field(default_factory=dict)


class ResumeJobMatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    saved_job_id: int | None = None
    saved_match_id: int | None = None
    job_saved: bool = False
    pending_job: PendingMatchedJob | None = None
    match_score: int = Field(..., ge=0, le=10)
    score_scale: str = "0-10"
    summary: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    supported_requirements: list[SupportedRequirement] = Field(default_factory=list)
    unsupported_requirements: list[UnsupportedRequirement] = Field(default_factory=list)
    recommended_resume_updates: list[str] = Field(default_factory=list)


class JobUrlExtractRequest(BaseModel):
    job_url: HttpUrl


class JobUrlExtractResponse(BaseModel):
    job_url: str
    extracted_text: str
    character_count: int


class SavePendingMatchedJobResponse(BaseModel):
    saved_job_id: int
    saved_match_id: int


class BulkSavedJobMatchRequest(BaseModel):
    user_job_ids: list[int] = Field(..., min_length=1, max_length=25)
    resume_text: str | None = Field(default=None)
    resume_profile_id: int | None = Field(default=None)
    resume_document_id: int | None = Field(default=None)

    @model_validator(mode="after")
    def require_resume_source(self) -> BulkSavedJobMatchRequest:
        resume_sources = [
            bool(self.resume_profile_id),
            bool(self.resume_document_id),
            bool(self.resume_text and self.resume_text.strip()),
        ]
        if not any(resume_sources):
            raise ValueError("Provide resume_profile_id, resume_text, or resume_document_id.")
        if sum(resume_sources) > 1:
            raise ValueError("Provide only one resume source.")
        return self


class BulkSavedJobMatchItem(BaseModel):
    user_job_id: int
    jobs_cache_id: int | None = None
    title: str
    company: str
    saved_match_id: int
    match: ResumeJobMatchResponse


class BulkSavedJobMatchFailure(BaseModel):
    user_job_id: int
    reason: str


class BulkSavedJobMatchResponse(BaseModel):
    matched: list[BulkSavedJobMatchItem] = Field(default_factory=list)
    failed: list[BulkSavedJobMatchFailure] = Field(default_factory=list)

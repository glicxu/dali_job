from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class JobDescriptionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = ""
    company: str = ""
    summary: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    required_experience: list[str] = Field(default_factory=list)
    preferred_experience: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    tools_and_technologies: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    seniority_level: str = ""
    employment_type: str = ""
    security_clearance: str = ""
    work_location: str = ""
    salary_range: str = ""
    application_deadline: str = ""


class JobImportRequest(BaseModel):
    job_description_text: str | None = Field(default=None)
    job_url: HttpUrl | None = Field(default=None)

    @model_validator(mode="after")
    def require_job_source(self) -> JobImportRequest:
        has_text = bool(self.job_description_text and self.job_description_text.strip())
        has_url = bool(self.job_url)
        if not has_text and not has_url:
            raise ValueError("Provide job_description_text or job_url.")
        if has_text and has_url:
            raise ValueError("Provide either job_description_text or job_url, not both.")
        return self


class JobDraftResponse(BaseModel):
    source_url: str | None
    raw_description_text: str
    job_data: JobDescriptionData
    fields_missing: list[str] = Field(default_factory=list)


class JobSaveRequest(BaseModel):
    title: str = ""
    company: str = ""
    source_url: HttpUrl | None = None
    raw_description_text: str
    job_data: JobDescriptionData
    notes: str | None = None


class JobUpdateRequest(BaseModel):
    title: str | None = None
    company: str | None = None
    source_url: HttpUrl | None = None
    raw_description_text: str | None = None
    job_data: JobDescriptionData | None = None
    notes: str | None = None


class JobResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    jobs_cache_id: int | None = None
    title: str
    company: str
    source_url: str | None
    raw_description_text: str
    job_data: JobDescriptionData
    notes: str | None = None
    match_score: int | None = None
    matched_resume_profile_id: int | None = None
    matched_resume_document_id: int | None = None
    matched_resume_source: str | None = None
    created_at: datetime
    updated_at: datetime


class JobResumeMatchResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    user_job_id: int
    jobs_cache_id: int | None = None
    resume_profile_id: int | None = None
    resume_document_id: int | None = None
    resume_source: str
    match_score: int = Field(..., ge=0, le=10)
    match_data: dict
    created_at: datetime

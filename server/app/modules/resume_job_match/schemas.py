from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ResumeJobMatchRequest(BaseModel):
    resume_text: str | None = Field(default=None)
    resume_document_id: str | None = Field(default=None)
    job_description_text: str | None = Field(default=None)
    job_url: HttpUrl | None = Field(default=None)

    @model_validator(mode="after")
    def require_resume_and_job_sources(self) -> ResumeJobMatchRequest:
        if not (self.resume_text and self.resume_text.strip()) and not self.resume_document_id:
            raise ValueError("Provide resume_text or resume_document_id.")
        if not (self.job_description_text and self.job_description_text.strip()) and not self.job_url:
            raise ValueError("Provide job_description_text or job_url.")
        return self


class SupportedRequirement(BaseModel):
    requirement: str
    resume_evidence: str
    confidence: float = Field(..., ge=0, le=1)


class UnsupportedRequirement(BaseModel):
    requirement: str
    reason: str


class ResumeJobMatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
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

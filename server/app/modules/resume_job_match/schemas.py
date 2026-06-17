from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResumeJobMatchRequest(BaseModel):
    resume_text: str = Field(..., min_length=1)
    job_description_text: str = Field(..., min_length=1)


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

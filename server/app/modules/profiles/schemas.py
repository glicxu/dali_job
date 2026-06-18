from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResumeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str | None = None
    summary: str | None = None
    experience: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    volunteer: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProfileUpdateRequest(BaseModel):
    resume_data: ResumeData


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    resume_data: ResumeData
    created_at: datetime
    updated_at: datetime

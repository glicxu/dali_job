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


class ResumeProfileCreateRequest(BaseModel):
    title: str = Field(default="Master Resume", min_length=1, max_length=255)
    resume_data: ResumeData = Field(default_factory=ResumeData)
    source_document_id: int | None = None
    source_document_version_id: int | None = None
    is_default: bool = False


class ResumeImportApplyRequest(BaseModel):
    resume_data: ResumeData
    source_document_id: int | None = None
    source_document_version_id: int | None = None


class ResumeProfileUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    resume_data: ResumeData | None = None
    is_default: bool | None = None


class ResumeProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    user_id: int
    title: str
    resume_data: ResumeData
    source_document_id: int | None = None
    source_document_version_id: int | None = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ResumeProfileListResponse(BaseModel):
    resume_profiles: list[ResumeProfileResponse]


class ResumeProfileDependency(BaseModel):
    dependency_type: str
    dependency_count: int
    message: str


class ResumeProfileDependencyResponse(BaseModel):
    can_delete_without_warning: bool
    dependencies: list[ResumeProfileDependency] = Field(default_factory=list)

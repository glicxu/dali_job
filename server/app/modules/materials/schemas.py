from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MaterialType = Literal["tailored_resume", "cover_letter"]


class EvidenceBackedText(BaseModel):
    text: str = Field(..., min_length=1)
    source_evidence: str = Field(..., min_length=1)


class TailoredResumeOutput(BaseModel):
    headline: EvidenceBackedText | None = None
    summary: list[EvidenceBackedText] = Field(default_factory=list)
    skills: list[EvidenceBackedText] = Field(default_factory=list)
    experience: list[EvidenceBackedText] = Field(default_factory=list)
    education: list[EvidenceBackedText] = Field(default_factory=list)
    certifications: list[EvidenceBackedText] = Field(default_factory=list)
    projects: list[EvidenceBackedText] = Field(default_factory=list)
    unsupported_requirements: list[str] = Field(default_factory=list)
    tailoring_notes: list[str] = Field(default_factory=list)


class CoverLetterParagraph(BaseModel):
    text: str = Field(..., min_length=1)
    resume_evidence: list[str] = Field(default_factory=list)
    job_evidence: list[str] = Field(default_factory=list)


class CoverLetterOutput(BaseModel):
    salutation: str = "Dear Hiring Team,"
    paragraphs: list[CoverLetterParagraph] = Field(default_factory=list)
    closing: str = "Sincerely,"
    warnings: list[str] = Field(default_factory=list)


class TailoredResumeGenerationRequest(BaseModel):
    application_id: int = Field(..., gt=0)
    source_document_version_id: int = Field(..., gt=0)
    target_notes: str | None = Field(default=None, max_length=30_000)


class CoverLetterGenerationRequest(BaseModel):
    application_id: int = Field(..., gt=0)
    source_document_version_id: int = Field(..., gt=0)
    source_material_version_id: int | None = Field(default=None, gt=0)
    target_notes: str | None = Field(default=None, max_length=30_000)


class MaterialRevisionRequest(BaseModel):
    parent_version_id: int = Field(..., gt=0)
    content_data: dict


class MaterialVersionResponse(BaseModel):
    id: int
    material_id: int
    version_number: int
    parent_version_id: int | None = None
    operation_id: int | None = None
    source_document_version_id: int | None = None
    source_material_version_id: int | None = None
    source_document_title: str
    source_document_file_name: str
    source_document_version_number: int
    source_document_sha256: str
    content_data: dict | None = None
    version_source: str
    warnings: list[str] = Field(default_factory=list)
    provider: str
    model_name: str | None = None
    prompt_version: str
    schema_version: str
    provider_execution_reference: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class MaterialResponse(BaseModel):
    id: int
    application_id: int
    material_type: MaterialType
    application_label: str
    created_at: datetime
    updated_at: datetime
    versions: list[MaterialVersionResponse] = Field(default_factory=list)


class MaterialListResponse(BaseModel):
    materials: list[MaterialResponse] = Field(default_factory=list)


def validate_material_content(material_type: str, content_data: dict) -> dict:
    if material_type == "tailored_resume":
        return TailoredResumeOutput.model_validate(content_data).model_dump(mode="json")
    if material_type == "cover_letter":
        return CoverLetterOutput.model_validate(content_data).model_dump(mode="json")
    raise ValueError("Unsupported material type.")

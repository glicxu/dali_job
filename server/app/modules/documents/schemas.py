from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_number: int
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    extracted_text_available: bool
    created_at: datetime


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    user_id: int
    title: str
    document_type: str
    created_at: datetime
    updated_at: datetime
    latest_version: DocumentVersionResponse | None = None
    versions: list[DocumentVersionResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


class DocumentTextResponse(BaseModel):
    document_id: int
    version_id: int
    extracted_text: str


class DocumentDownloadTicketResponse(BaseModel):
    download_path: str
    expires_at: datetime


class DocumentDependency(BaseModel):
    dependency_type: str
    dependency_count: int
    message: str


class DocumentDependencyResponse(BaseModel):
    can_delete_without_warning: bool
    dependencies: list[DocumentDependency] = Field(default_factory=list)

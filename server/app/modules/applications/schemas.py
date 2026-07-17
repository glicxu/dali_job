from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ApplicationStatus = Literal[
    "interested",
    "applied",
    "interviewing",
    "offer",
    "accepted",
    "rejected",
    "withdrawn",
]
ApplicationStage = Literal[
    "recruiter_contact",
    "assessment",
    "phone_screen",
    "technical_interview",
    "final_interview",
]
ApplicationPriority = Literal["low", "normal", "high"]
ApplicationTaskType = Literal["follow_up", "interview_prep", "document", "deadline", "other"]
ApplicationTaskStatus = Literal["open", "completed"]
ApplicationDocumentPurpose = Literal["resume", "cover_letter", "supporting"]


class ApplicationCreateRequest(BaseModel):
    user_job_id: int
    status: ApplicationStatus = "interested"
    stage: ApplicationStage | None = None
    priority: ApplicationPriority = "normal"
    match_score: int | None = Field(default=None, ge=0, le=10)
    salary_notes: str | None = None
    applied_at: datetime | None = None
    next_action_at: datetime | None = None
    next_action_label: str | None = None
    notes: str | None = None
    confirm_duplicate: bool = False


class ApplicationUpdateRequest(BaseModel):
    stage: ApplicationStage | None = None
    priority: ApplicationPriority | None = None
    match_score: int | None = Field(default=None, ge=0, le=10)
    salary_notes: str | None = None
    applied_at: datetime | None = None
    next_action_at: datetime | None = None
    next_action_label: str | None = None
    notes: str | None = None


class ApplicationStatusChangeRequest(BaseModel):
    status: ApplicationStatus
    reason: str | None = None


class ApplicationArchiveRequest(BaseModel):
    confirm_duplicate: bool = False


class ApplicationNoteCreateRequest(BaseModel):
    body: str = Field(..., min_length=1)


class ApplicationTaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    task_type: ApplicationTaskType = "other"
    due_at: datetime | None = None
    reminder_at: datetime | None = None


class ApplicationTaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    task_type: ApplicationTaskType | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    dismiss_reminder: bool | None = None
    completed: bool | None = None

    @model_validator(mode="after")
    def require_any_update(self) -> ApplicationTaskUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Provide at least one task field to update.")
        return self


class ApplicationJobSummary(BaseModel):
    id: int | None = None
    title: str = ""
    company: str = ""
    source_url: str | None = None
    summary: str = ""
    work_location: str = ""
    application_deadline: str = ""


class ApplicationResponse(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    user_job_id: int | None
    status: str
    stage: str | None = None
    priority: str
    match_score: int | None = None
    salary_notes: str | None = None
    applied_at: datetime | None = None
    next_action_at: datetime | None = None
    next_action_label: str | None = None
    notes: str | None = None
    job: ApplicationJobSummary | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    allowed_status_transitions: list[str] = Field(default_factory=list)


class ApplicationStatusHistoryResponse(BaseModel):
    id: int
    application_id: int
    from_status: str | None = None
    to_status: str
    source: str
    reason: str | None = None
    created_at: datetime


class ApplicationEventResponse(BaseModel):
    id: int
    application_id: int
    event_type: str
    source: str
    payload: dict
    created_at: datetime


class ApplicationNoteResponse(BaseModel):
    id: int
    application_id: int
    body: str
    created_at: datetime


class ApplicationTaskResponse(BaseModel):
    id: int
    application_id: int
    title: str
    task_type: str
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    reminder_dismissed_at: datetime | None = None
    completed_at: datetime | None = None
    is_overdue: bool = False
    reminder_due: bool = False
    created_at: datetime
    updated_at: datetime


class ApplicationDocumentAttachRequest(BaseModel):
    document_version_id: int
    purpose: ApplicationDocumentPurpose


class ApplicationDocumentResponse(BaseModel):
    id: int
    application_id: int
    document_id: int
    document_version_id: int
    purpose: str
    document_title: str
    document_type: str
    version_number: int
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime


class ApplicationDetailResponse(ApplicationResponse):
    status_history: list[ApplicationStatusHistoryResponse] = Field(default_factory=list)
    events: list[ApplicationEventResponse] = Field(default_factory=list)
    notes_list: list[ApplicationNoteResponse] = Field(default_factory=list)
    tasks: list[ApplicationTaskResponse] = Field(default_factory=list)
    documents: list[ApplicationDocumentResponse] = Field(default_factory=list)

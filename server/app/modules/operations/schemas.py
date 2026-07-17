from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


OperationStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class ManagedOperationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operation_type: str
    status: OperationStatus
    progress_current: int
    progress_total: int | None = None
    progress_message: str | None = None
    attempt_count: int
    max_attempts: int
    result_payload: dict | list | None = None
    error_code: str | None = None
    error_message: str | None = None
    provider: str | None = None
    model_or_actor: str | None = None
    prompt_version: str | None = None
    usage: dict = Field(default_factory=dict)
    cancel_requested_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ManagedOperationListResponse(BaseModel):
    operations: list[ManagedOperationResponse]


class ManagedOperationSummaryResponse(BaseModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    cancelled: int = 0
    provider_failures: dict[str, int] = Field(default_factory=dict)


class ResumeParseRetryRequest(BaseModel):
    document_id: int = Field(..., gt=0)


class JobAnalyzeOperationRequest(BaseModel):
    job_id: int = Field(..., gt=0)

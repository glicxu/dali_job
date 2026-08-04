from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReportCategory = Literal["bug", "feedback", "account", "other"]
ReportStatus = Literal["new", "in_review", "resolved", "closed"]


class UserReportCreateRequest(BaseModel):
    category: ReportCategory = "bug"
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=20_000)


class UserReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: ReportCategory
    title: str
    description: str
    status: ReportStatus
    created_at: datetime
    updated_at: datetime


class AdminReportResponse(UserReportResponse):
    workspace_id: int
    user_id: int
    reporter_email: str
    reporter_display_name: str
    admin_notes: str | None = None
    resolved_at: datetime | None = None
    resolved_by_user_id: int | None = None


class AdminReportUpdateRequest(BaseModel):
    status: ReportStatus | None = None
    admin_notes: str | None = Field(default=None, max_length=20_000)

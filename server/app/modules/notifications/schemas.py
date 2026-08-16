from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NotificationPreferenceUpdateRequest(BaseModel):
    email_enabled: bool = True
    digest_mode: str = Field(default="daily", pattern="^(immediate|daily)$")
    minimum_match_score: int = Field(default=0, ge=0, le=10)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    @model_validator(mode="after")
    def require_complete_quiet_hours(self) -> NotificationPreferenceUpdateRequest:
        if (self.quiet_hours_start is None) != (self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end must be set together")
        return self


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    email_enabled: bool
    digest_mode: str
    minimum_match_score: int
    timezone: str
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    created_at: datetime
    updated_at: datetime


class MatchFeedbackResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    recommendation: str
    rationale: str
    created_at: datetime
    updated_at: datetime


class MatchFeedbackUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    rationale: str = Field(default="", max_length=4000)


class MatchInboxItemResponse(BaseModel):
    match_id: int
    delivery_id: int
    user_job_id: int
    search_schedule_id: int
    title: str
    company: str
    source_url: str | None = None
    match_score: int = Field(..., ge=0, le=10)
    match_data: dict
    resume_data: dict
    job_data: dict
    user_feedback: MatchFeedbackResponse | None = None
    status: str
    sent_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime


class MatchInboxListResponse(BaseModel):
    items: list[MatchInboxItemResponse] = Field(default_factory=list)
    next_cursor: int | None = None

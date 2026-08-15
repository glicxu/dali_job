from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntitlementResponse(BaseModel):
    tier_code: str
    status: str
    entitlement_version: str
    period_started_at: datetime
    period_ends_at: datetime
    searches_per_period: int | None
    searches_reserved: int
    searches_consumed: int
    searches_available: int | None
    unlimited_searches: bool
    maximum_active_criteria: int
    minimum_interval_minutes: int


class UsageLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    search_run_id: int | None = None
    usage_type: str
    units: int
    state: str
    entitlement_version: str
    tier_code_snapshot: str
    allowance_snapshot: int
    reason: str | None = None
    reserved_at: datetime
    consumed_at: datetime | None = None
    released_at: datetime | None = None


class AccountUsageResponse(BaseModel):
    tier_code: str
    entitlement_version: str
    period_started_at: datetime
    period_ends_at: datetime
    searches_per_period: int | None
    searches_reserved: int
    searches_consumed: int
    searches_available: int | None
    unlimited_searches: bool
    entries: list[UsageLedgerEntryResponse] = Field(default_factory=list)
    next_cursor: int | None = None


class SearchScheduleCreateRequest(BaseModel):
    criterion_id: int = Field(..., gt=0)
    resume_profile_id: int = Field(..., gt=0)
    interval_minutes: int = Field(..., ge=1)
    minimum_match_score: int | None = Field(default=None, ge=0, le=10)
    enabled: bool = True
    next_run_at: datetime | None = None


class SearchScheduleUpdateRequest(BaseModel):
    resume_profile_id: int | None = Field(default=None, gt=0)
    interval_minutes: int | None = Field(default=None, ge=1)
    minimum_match_score: int | None = Field(default=None, ge=0, le=10)
    enabled: bool | None = None
    next_run_at: datetime | None = None

    @model_validator(mode="after")
    def require_change(self) -> SearchScheduleUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one schedule field is required")
        return self


class SearchScheduleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    user_id: int
    criterion_id: int
    resume_profile_id: int
    enabled: bool
    interval_minutes: int
    minimum_match_score: int
    next_run_at: datetime
    last_claimed_at: datetime | None = None
    last_completed_at: datetime | None = None
    consecutive_failure_count: int
    paused_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class SearchScheduleListResponse(BaseModel):
    schedules: list[SearchScheduleResponse] = Field(default_factory=list)


class SearchRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_id: int
    managed_operation_id: int | None = None
    status: str
    attempt_count: int
    max_attempts: int
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    scheduled_for: datetime
    provider: str | None = None
    jobs_discovered: int
    jobs_new: int
    jobs_matched: int
    matches_notified: int
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SearchRunListResponse(BaseModel):
    runs: list[SearchRunResponse] = Field(default_factory=list)
    next_cursor: int | None = None

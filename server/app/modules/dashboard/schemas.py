from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DashboardAlert(BaseModel):
    kind: str
    message: str
    href: str


class DashboardNextStep(BaseModel):
    kind: str
    label: str
    href: str
    reason: str


class DashboardBestMatch(BaseModel):
    user_saved_job_id: int
    job_cache_id: int | None = None
    title: str
    company: str
    match_score: int
    resume_profile_id: int | None = None
    resume_label: str
    match_summary: str
    href: str


class DashboardRecentJob(BaseModel):
    user_saved_job_id: int
    job_cache_id: int | None = None
    title: str
    company: str
    source_url: str | None = None
    status: str
    created_at: datetime
    href: str


class DashboardApplicationAction(BaseModel):
    task_id: int
    application_id: int
    title: str
    task_type: str
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    is_overdue: bool
    reminder_due: bool
    job_title: str
    company: str
    href: str


class DashboardResponse(BaseModel):
    setup_alerts: list[DashboardAlert]
    recommended_next_step: DashboardNextStep
    best_matches: list[DashboardBestMatch]
    recently_saved_jobs: list[DashboardRecentJob]
    application_actions: list[DashboardApplicationAction]

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.applications.models import Application, ApplicationTask
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.dashboard.schemas import (
    DashboardAlert,
    DashboardApplicationAction,
    DashboardBestMatch,
    DashboardNextStep,
    DashboardRecentJob,
    DashboardResponse,
)
from app.modules.jobs import repository as jobs_repository
from app.modules.profiles import repository as profiles_repository
from app.modules.profiles.repository import ensure_account_for_identity


def _job_href(user_saved_job_id: int) -> str:
    return f"/jobs?job_id={user_saved_job_id}"


def _match_href(user_saved_job_id: int) -> str:
    return f"/jobs?job_id={user_saved_job_id}&view=match"


def _match_summary(match_data: dict[str, Any] | None) -> str:
    if not match_data:
        return ""
    summary = match_data.get("summary")
    return summary if isinstance(summary, str) else ""


def _resume_label(job: dict[str, Any], resume_titles: dict[int, str]) -> str:
    resume_profile_id = job.get("matched_resume_profile_id")
    if isinstance(resume_profile_id, int):
        return resume_titles.get(resume_profile_id, f"Resume profile #{resume_profile_id}")
    resume_document_id = job.get("matched_resume_document_id")
    if isinstance(resume_document_id, int):
        return f"Resume document #{resume_document_id}"
    if job.get("matched_resume_source") == "pasted_text":
        return "Pasted resume text"
    return "Resume source not saved"


def _job_state(job: dict[str, Any]) -> str:
    if job.get("job_data") is None:
        return "needs_analysis"
    if job.get("match_score") is None:
        return "ready_to_match"
    return "matched"


def _created_at(job: dict[str, Any]) -> datetime:
    value = job["created_at"]
    if isinstance(value, datetime):
        return value
    raise TypeError("Saved job created_at must be a datetime.")


def _build_alerts(resume_count: int, jobs: list[dict[str, Any]]) -> list[DashboardAlert]:
    alerts: list[DashboardAlert] = []
    if resume_count == 0:
        alerts.append(
            DashboardAlert(
                kind="missing_resume_profile",
                message="Create a resume profile before running reliable job matches.",
                href="/profile",
            )
        )
    if not jobs:
        alerts.append(
            DashboardAlert(
                kind="no_saved_jobs",
                message="Search or import jobs to start comparing opportunities.",
                href="/jobs/search",
            )
        )
    jobs_needing_analysis = sum(1 for job in jobs if job.get("job_data") is None)
    if jobs_needing_analysis:
        alerts.append(
            DashboardAlert(
                kind="jobs_need_analysis",
                message=f"{jobs_needing_analysis} saved job{'s' if jobs_needing_analysis != 1 else ''} need analysis before full matching details are available.",
                href="/jobs",
            )
        )
    jobs_needing_match = sum(1 for job in jobs if job.get("job_data") is not None and job.get("match_score") is None)
    if jobs_needing_match:
        alerts.append(
            DashboardAlert(
                kind="jobs_need_matching",
                message=f"{jobs_needing_match} analyzed job{'s' if jobs_needing_match != 1 else ''} are ready for resume matching.",
                href="/jobs",
            )
        )
    return alerts


def _build_next_step(
    resume_count: int,
    jobs: list[dict[str, Any]],
    best_matches: list[DashboardBestMatch],
    application_actions: list[DashboardApplicationAction],
) -> DashboardNextStep:
    if application_actions:
        action = application_actions[0]
        return DashboardNextStep(
            kind="application_action",
            label=action.title,
            href=action.href,
            reason=(
                "This application task is overdue."
                if action.is_overdue
                else "This application task is your next scheduled action."
            ),
        )
    if resume_count == 0:
        return DashboardNextStep(
            kind="create_resume_profile",
            label="Create resume profile",
            href="/profile",
            reason="Resume profiles are needed before DaliJob can compare jobs against your background.",
        )
    if not jobs:
        return DashboardNextStep(
            kind="search_jobs",
            label="Search jobs",
            href="/jobs/search",
            reason="Saved jobs give you opportunities to analyze, compare, and track.",
        )
    if any(job.get("job_data") is None for job in jobs):
        return DashboardNextStep(
            kind="analyze_saved_jobs",
            label="Analyze saved jobs",
            href="/jobs",
            reason="Some saved jobs need structured job data before full match details are available.",
        )
    if any(job.get("match_score") is None for job in jobs):
        return DashboardNextStep(
            kind="run_matching",
            label="Run matching",
            href="/jobs",
            reason="Analyzed jobs are ready to compare against one of your resume profiles.",
        )
    if best_matches:
        return DashboardNextStep(
            kind="review_best_matches",
            label="Review best matches",
            href=best_matches[0].href,
            reason="Your highest scoring jobs are ready for review.",
        )
    return DashboardNextStep(
        kind="review_jobs",
        label="Review saved jobs",
        href="/jobs",
        reason="Your saved jobs are available for review.",
    )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _application_actions(
    db: Session,
    identity: AuthenticatedIdentity,
    jobs_by_id: dict[int, dict[str, Any]],
) -> list[DashboardApplicationAction]:
    user, workspace = ensure_account_for_identity(db, identity)
    rows = db.execute(
        select(ApplicationTask, Application)
        .join(Application, Application.id == ApplicationTask.application_id)
        .where(
            Application.workspace_id == workspace.id,
            Application.user_id == user.id,
            Application.archived_at.is_(None),
            ApplicationTask.completed_at.is_(None),
        )
    ).all()
    now = datetime.now(timezone.utc)
    actions: list[tuple[datetime, DashboardApplicationAction]] = []
    for task, application in rows:
        due_at = _as_utc(task.due_at)
        reminder_at = _as_utc(task.reminder_at)
        active_reminder_at = reminder_at if task.reminder_dismissed_at is None else None
        if due_at is None and active_reminder_at is None:
            continue
        action_at = min(value for value in (due_at, active_reminder_at) if value is not None)
        job = jobs_by_id.get(application.user_job_id or -1, {})
        actions.append(
            (
                action_at,
                DashboardApplicationAction(
                    task_id=task.id,
                    application_id=application.id,
                    title=task.title,
                    task_type=task.task_type,
                    due_at=task.due_at,
                    reminder_at=task.reminder_at,
                    is_overdue=bool(due_at is not None and due_at < now),
                    reminder_due=bool(
                        reminder_at is not None
                        and reminder_at <= now
                        and task.reminder_dismissed_at is None
                    ),
                    job_title=job.get("title") or f"Application #{application.id}",
                    company=job.get("company") or "",
                    href=f"/applications?application_id={application.id}",
                ),
            )
        )
    actions.sort(key=lambda item: item[0])
    return [item[1] for item in actions[:8]]


def get_dashboard(db: Session, identity: AuthenticatedIdentity) -> DashboardResponse:
    resume_profiles = profiles_repository.list_resume_profiles(db, identity)
    resume_titles = {profile.id: profile.title for profile in resume_profiles}
    jobs = jobs_repository.list_jobs(db, identity)
    jobs_by_id = {job["id"]: job for job in jobs}

    matched_jobs = [job for job in jobs if isinstance(job.get("match_score"), int)]
    matched_jobs.sort(key=lambda job: (job["match_score"], _created_at(job)), reverse=True)
    best_matches = [
        DashboardBestMatch(
            user_saved_job_id=job["id"],
            job_cache_id=job.get("jobs_cache_id"),
            title=job.get("title") or "Untitled Job",
            company=job.get("company") or "Unknown company",
            match_score=job["match_score"],
            resume_profile_id=job.get("matched_resume_profile_id"),
            resume_label=_resume_label(job, resume_titles),
            match_summary=_match_summary(job.get("match_data")),
            href=_match_href(job["id"]),
        )
        for job in matched_jobs[:5]
    ]

    recent_jobs_source = sorted(jobs, key=_created_at, reverse=True)[:5]
    recently_saved_jobs = [
        DashboardRecentJob(
            user_saved_job_id=job["id"],
            job_cache_id=job.get("jobs_cache_id"),
            title=job.get("title") or "Untitled Job",
            company=job.get("company") or "Unknown company",
            source_url=job.get("source_url"),
            status=_job_state(job),
            created_at=_created_at(job),
            href=_job_href(job["id"]),
        )
        for job in recent_jobs_source
    ]
    application_actions = _application_actions(db, identity, jobs_by_id)

    return DashboardResponse(
        setup_alerts=_build_alerts(len(resume_profiles), jobs),
        recommended_next_step=_build_next_step(
            len(resume_profiles),
            jobs,
            best_matches,
            application_actions,
        ),
        best_matches=best_matches,
        recently_saved_jobs=recently_saved_jobs,
        application_actions=application_actions,
    )

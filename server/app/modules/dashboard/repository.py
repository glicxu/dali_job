from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.dashboard.schemas import (
    DashboardAlert,
    DashboardBestMatch,
    DashboardNextStep,
    DashboardRecentJob,
    DashboardResponse,
)
from app.modules.jobs import repository as jobs_repository
from app.modules.profiles import repository as profiles_repository


def _job_href(user_saved_job_id: int) -> str:
    return f"/jobs?job_id={user_saved_job_id}"


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


def _build_next_step(resume_count: int, jobs: list[dict[str, Any]], best_matches: list[DashboardBestMatch]) -> DashboardNextStep:
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


def get_dashboard(db: Session, identity: AuthenticatedIdentity) -> DashboardResponse:
    resume_profiles = profiles_repository.list_resume_profiles(db, identity)
    resume_titles = {profile.id: profile.title for profile in resume_profiles}
    jobs = jobs_repository.list_jobs(db, identity)

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
            href=_job_href(job["id"]),
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

    return DashboardResponse(
        setup_alerts=_build_alerts(len(resume_profiles), jobs),
        recommended_next_step=_build_next_step(len(resume_profiles), jobs, best_matches),
        best_matches=best_matches,
        recently_saved_jobs=recently_saved_jobs,
    )

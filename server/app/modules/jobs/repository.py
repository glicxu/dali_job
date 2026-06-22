from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.jobs.models import Job
from app.modules.jobs.schemas import JobDescriptionData, JobSaveRequest, JobUpdateRequest
from app.modules.profiles.repository import ensure_account_for_identity


def _job_response(job: Job) -> dict:
    return {
        "id": job.id,
        "workspace_id": job.workspace_id,
        "user_id": job.user_id,
        "title": job.title,
        "company": job.company,
        "source_url": job.source_url,
        "raw_description_text": job.raw_description_text,
        "job_data": job.job_data,
        "notes": job.notes,
        "match_score": job.match_score,
        "matched_resume_document_id": job.matched_resume_document_id,
        "matched_resume_source": job.matched_resume_source,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def list_jobs(db: Session, identity: AuthenticatedIdentity) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    jobs = db.scalars(
        select(Job)
        .where(
            Job.workspace_id == workspace.id,
            Job.user_id == user.id,
            Job.deleted_at.is_(None),
        )
        .order_by(desc(Job.updated_at))
    ).all()
    return [_job_response(job) for job in jobs]


def create_job_from_description(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData,
    match_score: int | None = None,
    matched_resume_document_id: str | None = None,
    matched_resume_source: str | None = None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    job = Job(
        workspace_id=workspace.id,
        user_id=user.id,
        title=job_data.title,
        company=job_data.company,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data.model_dump(),
        match_score=match_score,
        matched_resume_document_id=matched_resume_document_id,
        matched_resume_source=matched_resume_source,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return _job_response(job)


def get_job_for_identity(db: Session, identity: AuthenticatedIdentity, job_id: str) -> Job | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.workspace_id == workspace.id,
            Job.user_id == user.id,
            Job.deleted_at.is_(None),
        )
    )


def create_job(db: Session, identity: AuthenticatedIdentity, payload: JobSaveRequest) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    job = Job(
        workspace_id=workspace.id,
        user_id=user.id,
        title=payload.title.strip() or payload.job_data.title,
        company=payload.company.strip() or payload.job_data.company,
        source_url=str(payload.source_url) if payload.source_url else None,
        raw_description_text=payload.raw_description_text.strip(),
        job_data=payload.job_data.model_dump(),
        notes=payload.notes.strip() if payload.notes else None,
        match_score=payload.match_score,
        matched_resume_document_id=payload.matched_resume_document_id,
        matched_resume_source=payload.matched_resume_source,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return _job_response(job)


def update_job(db: Session, job: Job, payload: JobUpdateRequest) -> dict:
    if payload.job_data is not None:
        job.job_data = payload.job_data.model_dump()
        if payload.title is None:
            job.title = payload.job_data.title
        if payload.company is None:
            job.company = payload.job_data.company
    if payload.title is not None:
        job.title = payload.title.strip()
    if payload.company is not None:
        job.company = payload.company.strip()
    if "source_url" in payload.model_fields_set:
        job.source_url = str(payload.source_url) if payload.source_url else None
    if payload.raw_description_text is not None:
        job.raw_description_text = payload.raw_description_text.strip()
    if "notes" in payload.model_fields_set:
        job.notes = payload.notes.strip() if payload.notes else None
    if "match_score" in payload.model_fields_set:
        job.match_score = payload.match_score
    if "matched_resume_document_id" in payload.model_fields_set:
        job.matched_resume_document_id = payload.matched_resume_document_id
    if "matched_resume_source" in payload.model_fields_set:
        job.matched_resume_source = payload.matched_resume_source
    db.flush()
    db.refresh(job)
    return _job_response(job)

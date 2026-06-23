from __future__ import annotations

from hashlib import sha256

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.jobs.models import JobCache, JobResumeMatch, UserJob
from app.modules.jobs.schemas import JobDescriptionData, JobSaveRequest, JobUpdateRequest
from app.modules.profiles.repository import ensure_account_for_identity


def source_url_hash(source_url: str | None) -> str | None:
    if not source_url:
        return None
    return sha256(source_url.strip().encode("utf-8")).hexdigest()


def _latest_match_for_user_job(
    db: Session,
    identity: AuthenticatedIdentity,
    user_job_id: int,
) -> JobResumeMatch | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(JobResumeMatch)
        .where(
            JobResumeMatch.workspace_id == workspace.id,
            JobResumeMatch.user_id == user.id,
            JobResumeMatch.user_job_id == user_job_id,
        )
        .order_by(desc(JobResumeMatch.created_at))
        .limit(1)
    )


def _job_response(user_job: UserJob, latest_match: JobResumeMatch | None = None) -> dict:
    return {
        "id": user_job.id,
        "workspace_id": user_job.workspace_id,
        "user_id": user_job.user_id,
        "jobs_cache_id": user_job.jobs_cache_id,
        "title": user_job.title,
        "company": user_job.company,
        "source_url": user_job.source_url,
        "raw_description_text": user_job.raw_description_text,
        "job_data": user_job.job_data,
        "notes": user_job.notes,
        "match_score": latest_match.match_score if latest_match else None,
        "matched_resume_profile_id": latest_match.resume_profile_id if latest_match else None,
        "matched_resume_document_id": latest_match.resume_document_id if latest_match else None,
        "matched_resume_source": latest_match.resume_source if latest_match else None,
        "created_at": user_job.created_at,
        "updated_at": user_job.updated_at,
    }


def _match_response(match: JobResumeMatch) -> dict:
    return {
        "id": match.id,
        "workspace_id": match.workspace_id,
        "user_id": match.user_id,
        "user_job_id": match.user_job_id,
        "jobs_cache_id": match.jobs_cache_id,
        "resume_profile_id": match.resume_profile_id,
        "resume_document_id": match.resume_document_id,
        "resume_source": match.resume_source,
        "match_score": match.match_score,
        "match_data": match.match_data,
        "created_at": match.created_at,
    }


def list_jobs(db: Session, identity: AuthenticatedIdentity) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    user_jobs = db.scalars(
        select(UserJob)
        .where(
            UserJob.workspace_id == workspace.id,
            UserJob.user_id == user.id,
            UserJob.deleted_at.is_(None),
        )
        .order_by(desc(UserJob.updated_at))
    ).all()
    return [
        _job_response(user_job, _latest_match_for_user_job(db, identity, user_job.id))
        for user_job in user_jobs
    ]


def get_user_job_by_cache_id(db: Session, identity: AuthenticatedIdentity, jobs_cache_id: int) -> UserJob | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(UserJob).where(
            UserJob.workspace_id == workspace.id,
            UserJob.user_id == user.id,
            UserJob.jobs_cache_id == jobs_cache_id,
            UserJob.deleted_at.is_(None),
        )
    )


def get_cached_job_by_source_url(db: Session, source_url: str | None) -> JobCache | None:
    hashed_url = source_url_hash(source_url)
    if not hashed_url:
        return None
    return db.scalar(
        select(JobCache)
        .where(
            JobCache.source_url_hash == hashed_url,
            JobCache.source_url == source_url,
            JobCache.deleted_at.is_(None),
        )
        .order_by(desc(JobCache.updated_at))
        .limit(1)
    )


def get_user_job_by_source_url(db: Session, identity: AuthenticatedIdentity, source_url: str | None) -> UserJob | None:
    cached_job = get_cached_job_by_source_url(db, source_url)
    if cached_job is None:
        return None
    return get_user_job_by_cache_id(db, identity, cached_job.id)


def _create_cache_job(
    db: Session,
    *,
    source_url: str,
    raw_description_text: str,
    job_data: JobDescriptionData,
) -> JobCache:
    job_cache = JobCache(
        title=job_data.title,
        company=job_data.company,
        source_url=source_url,
        source_url_hash=source_url_hash(source_url),
        raw_description_text=raw_description_text,
        job_data=job_data.model_dump(),
    )
    db.add(job_cache)
    db.flush()
    db.refresh(job_cache)
    return job_cache


def get_or_create_cache_job(
    db: Session,
    *,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData,
    reuse_cached_url: bool = True,
) -> JobCache | None:
    if not source_url:
        return None
    if reuse_cached_url:
        cached_job = get_cached_job_by_source_url(db, source_url)
        if cached_job is not None:
            return cached_job
    return _create_cache_job(
        db,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data,
    )


def create_user_job(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    jobs_cache_id: int | None,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData,
    notes: str | None = None,
) -> UserJob:
    user, workspace = ensure_account_for_identity(db, identity)
    if jobs_cache_id is not None:
        existing = get_user_job_by_cache_id(db, identity, jobs_cache_id)
        if existing is not None:
            if notes is not None:
                existing.notes = notes.strip() or None
                db.flush()
                db.refresh(existing)
            return existing
    user_job = UserJob(
        workspace_id=workspace.id,
        user_id=user.id,
        jobs_cache_id=jobs_cache_id,
        title=job_data.title,
        company=job_data.company,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data.model_dump(),
        notes=notes.strip() if notes else None,
    )
    db.add(user_job)
    db.flush()
    db.refresh(user_job)
    return user_job


def create_job_from_description(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData,
    notes: str | None = None,
    reuse_cached_url: bool = True,
) -> dict:
    job_cache = get_or_create_cache_job(
        db,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data,
        reuse_cached_url=reuse_cached_url,
    )
    user_job = create_user_job(
        db,
        identity,
        jobs_cache_id=job_cache.id if job_cache else None,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data,
        notes=notes,
    )
    return _job_response(user_job, _latest_match_for_user_job(db, identity, user_job.id))


def get_user_job_for_identity(db: Session, identity: AuthenticatedIdentity, user_job_id: int) -> UserJob | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(UserJob).where(
            UserJob.id == user_job_id,
            UserJob.workspace_id == workspace.id,
            UserJob.user_id == user.id,
            UserJob.deleted_at.is_(None),
        )
    )


def job_response_for_identity(db: Session, identity: AuthenticatedIdentity, user_job: UserJob) -> dict:
    return _job_response(user_job, _latest_match_for_user_job(db, identity, user_job.id))


def create_job(db: Session, identity: AuthenticatedIdentity, payload: JobSaveRequest) -> dict:
    source_url = str(payload.source_url) if payload.source_url else None
    job_data = payload.job_data.model_copy(
        update={
            "title": payload.title.strip() or payload.job_data.title,
            "company": payload.company.strip() or payload.job_data.company,
        }
    )
    job_cache = get_or_create_cache_job(
        db,
        source_url=source_url,
        raw_description_text=payload.raw_description_text.strip(),
        job_data=job_data,
        reuse_cached_url=bool(source_url),
    )
    user_job = create_user_job(
        db,
        identity,
        jobs_cache_id=job_cache.id if job_cache else None,
        source_url=source_url,
        raw_description_text=payload.raw_description_text.strip(),
        job_data=job_data,
        notes=payload.notes,
    )
    return _job_response(user_job, _latest_match_for_user_job(db, identity, user_job.id))


def update_job(db: Session, identity: AuthenticatedIdentity, user_job: UserJob, payload: JobUpdateRequest) -> dict:
    if payload.job_data is not None:
        user_job.job_data = payload.job_data.model_dump()
        if payload.title is None:
            user_job.title = payload.job_data.title
        if payload.company is None:
            user_job.company = payload.job_data.company
    if payload.title is not None:
        user_job.title = payload.title.strip()
    if payload.company is not None:
        user_job.company = payload.company.strip()
    if "source_url" in payload.model_fields_set:
        user_job.source_url = str(payload.source_url) if payload.source_url else None
    if payload.raw_description_text is not None:
        user_job.raw_description_text = payload.raw_description_text.strip()
    if "notes" in payload.model_fields_set:
        user_job.notes = payload.notes.strip() if payload.notes else None
    db.flush()
    db.refresh(user_job)
    return _job_response(user_job, _latest_match_for_user_job(db, identity, user_job.id))


def create_job_resume_match(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    user_job_id: int,
    jobs_cache_id: int | None,
    resume_profile_id: int | None = None,
    resume_document_id: int | None = None,
    resume_source: str,
    match_score: int,
    match_data: dict,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    match = JobResumeMatch(
        workspace_id=workspace.id,
        user_id=user.id,
        user_job_id=user_job_id,
        jobs_cache_id=jobs_cache_id,
        resume_profile_id=resume_profile_id,
        resume_document_id=resume_document_id,
        resume_source=resume_source,
        match_score=match_score,
        match_data=match_data,
    )
    db.add(match)
    db.flush()
    db.refresh(match)
    return _match_response(match)

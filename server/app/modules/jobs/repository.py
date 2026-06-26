from __future__ import annotations

from hashlib import sha256

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.jobs.models import JobCache, JobResumeMatch, UserSavedJob
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


def _job_response(
    user_saved_job: UserSavedJob,
    job_cache: JobCache,
    latest_match: JobResumeMatch | None = None,
) -> dict:
    return {
        "id": user_saved_job.id,
        "workspace_id": user_saved_job.workspace_id,
        "user_id": user_saved_job.user_id,
        "jobs_cache_id": user_saved_job.jobs_cache_id,
        "title": job_cache.title,
        "company": job_cache.company,
        "source_url": job_cache.source_url,
        "raw_description_text": job_cache.raw_description_text,
        "job_data": job_cache.job_data,
        "notes": user_saved_job.notes,
        "match_score": latest_match.match_score if latest_match else None,
        "matched_resume_profile_id": latest_match.resume_profile_id if latest_match else None,
        "matched_resume_document_id": latest_match.resume_document_id if latest_match else None,
        "matched_resume_source": latest_match.resume_source if latest_match else None,
        "match_data": latest_match.match_data if latest_match else None,
        "created_at": user_saved_job.created_at,
        "updated_at": user_saved_job.updated_at,
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
    latest_match_ids = (
        select(
            JobResumeMatch.user_job_id.label("user_job_id"),
            func.max(JobResumeMatch.id).label("latest_match_id"),
        )
        .where(
            JobResumeMatch.workspace_id == workspace.id,
            JobResumeMatch.user_id == user.id,
        )
        .group_by(JobResumeMatch.user_job_id)
        .subquery()
    )
    rows = db.execute(
        select(UserSavedJob, JobCache, JobResumeMatch)
        .join(JobCache, UserSavedJob.jobs_cache_id == JobCache.id)
        .outerjoin(latest_match_ids, latest_match_ids.c.user_job_id == UserSavedJob.id)
        .outerjoin(JobResumeMatch, JobResumeMatch.id == latest_match_ids.c.latest_match_id)
        .where(
            UserSavedJob.workspace_id == workspace.id,
            UserSavedJob.user_id == user.id,
            UserSavedJob.deleted_at.is_(None),
            JobCache.deleted_at.is_(None),
        )
        .order_by(desc(UserSavedJob.updated_at))
    ).all()
    return [
        _job_response(user_saved_job, job_cache, latest_match)
        for user_saved_job, job_cache, latest_match in rows
    ]


def get_user_job_by_cache_id(db: Session, identity: AuthenticatedIdentity, jobs_cache_id: int) -> UserSavedJob | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(UserSavedJob).where(
            UserSavedJob.workspace_id == workspace.id,
            UserSavedJob.user_id == user.id,
            UserSavedJob.jobs_cache_id == jobs_cache_id,
            UserSavedJob.deleted_at.is_(None),
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


def get_user_job_by_source_url(
    db: Session,
    identity: AuthenticatedIdentity,
    source_url: str | None,
) -> tuple[UserSavedJob, JobCache] | None:
    cached_job = get_cached_job_by_source_url(db, source_url)
    if cached_job is None:
        return None
    user_saved_job = get_user_job_by_cache_id(db, identity, cached_job.id)
    if user_saved_job is None:
        return None
    return user_saved_job, cached_job


def _create_cache_job(
    db: Session,
    *,
    source_url: str | None,
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
) -> JobCache:
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
    jobs_cache_id: int,
    notes: str | None = None,
) -> UserSavedJob:
    user, workspace = ensure_account_for_identity(db, identity)
    existing = get_user_job_by_cache_id(db, identity, jobs_cache_id)
    if existing is not None:
        if notes is not None:
            existing.notes = notes.strip() or None
            db.flush()
            db.refresh(existing)
        return existing
    user_job = UserSavedJob(
        workspace_id=workspace.id,
        user_id=user.id,
        jobs_cache_id=jobs_cache_id,
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
        jobs_cache_id=job_cache.id,
        notes=notes,
    )
    return _job_response(user_job, job_cache, _latest_match_for_user_job(db, identity, user_job.id))


def get_user_job_for_identity(db: Session, identity: AuthenticatedIdentity, user_job_id: int) -> UserSavedJob | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(UserSavedJob).where(
            UserSavedJob.id == user_job_id,
            UserSavedJob.workspace_id == workspace.id,
            UserSavedJob.user_id == user.id,
            UserSavedJob.deleted_at.is_(None),
        )
    )


def get_job_cache_for_saved_job(db: Session, user_job: UserSavedJob) -> JobCache | None:
    return db.get(JobCache, user_job.jobs_cache_id)


def job_response_for_identity(db: Session, identity: AuthenticatedIdentity, user_job: UserSavedJob) -> dict:
    job_cache = get_job_cache_for_saved_job(db, user_job)
    if job_cache is None:
        raise ValueError("Saved job does not reference an existing jobs_cache row.")
    return _job_response(user_job, job_cache, _latest_match_for_user_job(db, identity, user_job.id))


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
        jobs_cache_id=job_cache.id,
        notes=payload.notes,
    )
    return _job_response(user_job, job_cache, _latest_match_for_user_job(db, identity, user_job.id))


def update_job(db: Session, identity: AuthenticatedIdentity, user_job: UserSavedJob, payload: JobUpdateRequest) -> dict:
    if "notes" in payload.model_fields_set:
        user_job.notes = payload.notes.strip() if payload.notes else None
    db.flush()
    db.refresh(user_job)
    job_cache = get_job_cache_for_saved_job(db, user_job)
    if job_cache is None:
        raise ValueError("Saved job does not reference an existing jobs_cache row.")
    return _job_response(user_job, job_cache, _latest_match_for_user_job(db, identity, user_job.id))


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

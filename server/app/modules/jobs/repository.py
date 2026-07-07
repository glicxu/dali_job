from __future__ import annotations

from hashlib import sha256

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.jobs.models import JobCache, JobResumeMatch, UserEditedJob, UserSavedJob
from app.modules.jobs.schemas import JobDescriptionData, JobSaveRequest, JobUpdateRequest
from app.modules.jobs.service import JobDescriptionParser
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


def _effective_job_fields(
    job_cache: JobCache | None,
    user_edited_job: UserEditedJob | None,
) -> tuple[str, str, str | None, str, dict | None]:
    title = user_edited_job.title if user_edited_job else (job_cache.title if job_cache else "")
    company = user_edited_job.company if user_edited_job else (job_cache.company if job_cache else "")
    source_url = user_edited_job.source_url if user_edited_job else (job_cache.source_url if job_cache else None)
    raw_description_text = (
        user_edited_job.raw_description_text
        if user_edited_job
        else (job_cache.raw_description_text if job_cache else "")
    )
    job_data = user_edited_job.job_data if user_edited_job else (job_cache.job_data if job_cache else None)
    return title, company, source_url, raw_description_text, job_data


def _job_response(
    user_saved_job: UserSavedJob,
    job_cache: JobCache | None,
    user_edited_job: UserEditedJob | None,
    latest_match: JobResumeMatch | None = None,
) -> dict:
    title, company, source_url, raw_description_text, job_data = _effective_job_fields(job_cache, user_edited_job)
    return {
        "id": user_saved_job.id,
        "workspace_id": user_saved_job.workspace_id,
        "user_id": user_saved_job.user_id,
        "jobs_cache_id": user_saved_job.jobs_cache_id,
        "user_edited_job_id": user_saved_job.user_edited_job_id,
        "title": title,
        "company": company,
        "source_url": source_url,
        "raw_description_text": raw_description_text,
        "job_data": job_data,
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
        select(UserSavedJob, JobCache, UserEditedJob, JobResumeMatch)
        .outerjoin(JobCache, UserSavedJob.jobs_cache_id == JobCache.id)
        .outerjoin(UserEditedJob, UserSavedJob.user_edited_job_id == UserEditedJob.id)
        .outerjoin(latest_match_ids, latest_match_ids.c.user_job_id == UserSavedJob.id)
        .outerjoin(JobResumeMatch, JobResumeMatch.id == latest_match_ids.c.latest_match_id)
        .where(
            UserSavedJob.workspace_id == workspace.id,
            UserSavedJob.user_id == user.id,
            UserSavedJob.deleted_at.is_(None),
            (UserSavedJob.jobs_cache_id.is_(None)) | (JobCache.deleted_at.is_(None)),
            (UserSavedJob.user_edited_job_id.is_(None)) | (UserEditedJob.deleted_at.is_(None)),
        )
        .order_by(desc(UserSavedJob.updated_at))
    ).all()
    return [
        _job_response(user_saved_job, job_cache, user_edited_job, latest_match)
        for user_saved_job, job_cache, user_edited_job, latest_match in rows
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


def get_cached_job_by_id(db: Session, jobs_cache_id: int | None) -> JobCache | None:
    if jobs_cache_id is None:
        return None
    return db.get(JobCache, jobs_cache_id)


def get_user_edited_job_by_id(db: Session, user_edited_job_id: int | None) -> UserEditedJob | None:
    if user_edited_job_id is None:
        return None
    return db.get(UserEditedJob, user_edited_job_id)


def get_job_cache_for_saved_job(db: Session, user_job: UserSavedJob) -> JobCache | None:
    return get_cached_job_by_id(db, user_job.jobs_cache_id)


def get_user_edited_job_for_saved_job(db: Session, user_job: UserSavedJob) -> UserEditedJob | None:
    return get_user_edited_job_by_id(db, user_job.user_edited_job_id)


def get_user_job_by_source_url(
    db: Session,
    identity: AuthenticatedIdentity,
    source_url: str | None,
) -> tuple[UserSavedJob, JobCache, UserEditedJob | None] | None:
    cached_job = get_cached_job_by_source_url(db, source_url)
    if cached_job is None:
        return None
    user_saved_job = get_user_job_by_cache_id(db, identity, cached_job.id)
    if user_saved_job is None:
        return None
    return user_saved_job, cached_job, get_user_edited_job_for_saved_job(db, user_saved_job)


def _create_cache_job(
    db: Session,
    *,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData | None = None,
    title: str = "",
    company: str = "",
) -> JobCache:
    stored_job_data = job_data.model_dump() if job_data is not None else None
    job_cache = JobCache(
        title=(job_data.title if job_data and job_data.title else title).strip(),
        company=(job_data.company if job_data and job_data.company else company).strip(),
        source_url=source_url,
        source_url_hash=source_url_hash(source_url),
        raw_description_text=raw_description_text,
        job_data=stored_job_data,
    )
    db.add(job_cache)
    db.flush()
    db.refresh(job_cache)
    return job_cache


def _fill_cache_job(
    db: Session,
    job_cache: JobCache,
    *,
    raw_description_text: str | None = None,
    job_data: JobDescriptionData | None = None,
    title: str = "",
    company: str = "",
) -> JobCache:
    changed = False
    if raw_description_text and not job_cache.raw_description_text:
        job_cache.raw_description_text = raw_description_text
        changed = True
    if title and not job_cache.title:
        job_cache.title = title.strip()
        changed = True
    if company and not job_cache.company:
        job_cache.company = company.strip()
        changed = True
    if job_data is not None and job_cache.job_data is None:
        job_cache.job_data = job_data.model_dump()
        if job_data.title and not job_cache.title:
            job_cache.title = job_data.title
        if job_data.company and not job_cache.company:
            job_cache.company = job_data.company
        changed = True
    if changed:
        db.flush()
        db.refresh(job_cache)
    return job_cache


def get_or_create_cache_job(
    db: Session,
    *,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData | None = None,
    title: str = "",
    company: str = "",
    reuse_cached_url: bool = True,
) -> JobCache:
    if reuse_cached_url:
        cached_job = get_cached_job_by_source_url(db, source_url)
        if cached_job is not None:
            return _fill_cache_job(
                db,
                cached_job,
                raw_description_text=raw_description_text,
                job_data=job_data,
                title=title,
                company=company,
            )
    return _create_cache_job(
        db,
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=job_data,
        title=title,
        company=company,
    )


def create_user_edited_job(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    title: str,
    company: str,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData | dict | None,
) -> UserEditedJob:
    user, workspace = ensure_account_for_identity(db, identity)
    stored_job_data = job_data.model_dump() if isinstance(job_data, JobDescriptionData) else job_data
    edited_job = UserEditedJob(
        workspace_id=workspace.id,
        user_id=user.id,
        title=title.strip(),
        company=company.strip(),
        source_url=source_url,
        raw_description_text=raw_description_text,
        job_data=stored_job_data,
    )
    db.add(edited_job)
    db.flush()
    db.refresh(edited_job)
    return edited_job


def update_user_edited_job(
    db: Session,
    edited_job: UserEditedJob,
    *,
    title: str,
    company: str,
    source_url: str | None,
    raw_description_text: str,
    job_data: JobDescriptionData | dict | None,
) -> UserEditedJob:
    stored_job_data = job_data.model_dump() if isinstance(job_data, JobDescriptionData) else job_data
    edited_job.title = title.strip()
    edited_job.company = company.strip()
    edited_job.source_url = source_url
    edited_job.raw_description_text = raw_description_text
    edited_job.job_data = stored_job_data
    db.flush()
    db.refresh(edited_job)
    return edited_job


def ensure_job_data(db: Session, job_cache: JobCache, parser: JobDescriptionParser) -> JobDescriptionData:
    if job_cache.job_data is not None:
        return JobDescriptionData.model_validate(job_cache.job_data)
    job_data = parser.parse(job_cache.raw_description_text)
    _fill_cache_job(db, job_cache, job_data=job_data)
    return job_data


def ensure_saved_job_data(
    db: Session,
    user_job: UserSavedJob,
    job_cache: JobCache | None,
    parser: JobDescriptionParser,
) -> JobDescriptionData:
    edited_job = get_user_edited_job_for_saved_job(db, user_job)
    if edited_job is not None:
        if edited_job.job_data is not None:
            return JobDescriptionData.model_validate(edited_job.job_data)
        job_data = parser.parse(edited_job.raw_description_text)
        edited_job.job_data = job_data.model_dump()
        if job_data.title and not edited_job.title:
            edited_job.title = job_data.title
        if job_data.company and not edited_job.company:
            edited_job.company = job_data.company
        db.flush()
        db.refresh(edited_job)
        return job_data

    if job_cache is None:
        raise ValueError("Saved job does not have cache data or a user-edited job.")
    return ensure_job_data(db, job_cache, parser)


def create_user_job(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    jobs_cache_id: int | None,
    user_edited_job_id: int | None = None,
    notes: str | None = None,
) -> UserSavedJob:
    user, workspace = ensure_account_for_identity(db, identity)
    existing = get_user_job_by_cache_id(db, identity, jobs_cache_id) if jobs_cache_id is not None else None
    if existing is not None:
        if notes is not None:
            existing.notes = notes.strip() or None
        if user_edited_job_id is not None:
            existing.user_edited_job_id = user_edited_job_id
        if notes is not None or user_edited_job_id is not None:
            db.flush()
            db.refresh(existing)
        return existing
    user_job = UserSavedJob(
        workspace_id=workspace.id,
        user_id=user.id,
        jobs_cache_id=jobs_cache_id,
        user_edited_job_id=user_edited_job_id,
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
    if source_url:
        job_cache = get_or_create_cache_job(
            db,
            source_url=source_url,
            raw_description_text=raw_description_text,
            job_data=job_data,
            reuse_cached_url=reuse_cached_url,
        )
        user_job = create_user_job(db, identity, jobs_cache_id=job_cache.id, notes=notes)
        return _job_response(user_job, job_cache, None, _latest_match_for_user_job(db, identity, user_job.id))

    edited_job = create_user_edited_job(
        db,
        identity,
        title=job_data.title,
        company=job_data.company,
        source_url=None,
        raw_description_text=raw_description_text,
        job_data=job_data,
    )
    user_job = create_user_job(db, identity, jobs_cache_id=None, user_edited_job_id=edited_job.id, notes=notes)
    return _job_response(user_job, None, edited_job, _latest_match_for_user_job(db, identity, user_job.id))


def create_job_from_source(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    source_url: str | None,
    raw_description_text: str,
    title: str = "",
    company: str = "",
    notes: str | None = None,
    reuse_cached_url: bool = True,
) -> dict:
    if source_url:
        job_cache = get_or_create_cache_job(
            db,
            source_url=source_url,
            raw_description_text=raw_description_text,
            title=title,
            company=company,
            job_data=None,
            reuse_cached_url=reuse_cached_url,
        )
        user_job = create_user_job(db, identity, jobs_cache_id=job_cache.id, notes=notes)
        return _job_response(user_job, job_cache, None, _latest_match_for_user_job(db, identity, user_job.id))

    edited_job = create_user_edited_job(
        db,
        identity,
        title=title,
        company=company,
        source_url=None,
        raw_description_text=raw_description_text,
        job_data=None,
    )
    user_job = create_user_job(db, identity, jobs_cache_id=None, user_edited_job_id=edited_job.id, notes=notes)
    return _job_response(user_job, None, edited_job, _latest_match_for_user_job(db, identity, user_job.id))


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


def job_response_for_identity(db: Session, identity: AuthenticatedIdentity, user_job: UserSavedJob) -> dict:
    job_cache = get_job_cache_for_saved_job(db, user_job)
    edited_job = get_user_edited_job_for_saved_job(db, user_job)
    return _job_response(user_job, job_cache, edited_job, _latest_match_for_user_job(db, identity, user_job.id))


def create_job(db: Session, identity: AuthenticatedIdentity, payload: JobSaveRequest) -> dict:
    source_url = str(payload.source_url) if payload.source_url else None
    job_data = payload.job_data.model_copy(
        update={
            "title": payload.title.strip() or payload.job_data.title,
            "company": payload.company.strip() or payload.job_data.company,
        }
    )
    job_cache = None
    if source_url:
        job_cache = get_or_create_cache_job(
            db,
            source_url=source_url,
            raw_description_text=payload.raw_description_text.strip(),
            job_data=None if payload.save_as_user_edit else job_data,
            title=payload.title.strip(),
            company=payload.company.strip(),
            reuse_cached_url=True,
        )

    if source_url and not payload.save_as_user_edit:
        user_job = create_user_job(db, identity, jobs_cache_id=job_cache.id if job_cache else None, notes=payload.notes)
        return _job_response(user_job, job_cache, None, _latest_match_for_user_job(db, identity, user_job.id))

    edited_job = create_user_edited_job(
        db,
        identity,
        title=job_data.title or payload.title.strip(),
        company=job_data.company or payload.company.strip(),
        source_url=source_url,
        raw_description_text=payload.raw_description_text.strip(),
        job_data=job_data,
    )
    user_job = create_user_job(
        db,
        identity,
        jobs_cache_id=job_cache.id if job_cache else None,
        user_edited_job_id=edited_job.id,
        notes=payload.notes,
    )
    return _job_response(user_job, job_cache, edited_job, _latest_match_for_user_job(db, identity, user_job.id))


def update_job(db: Session, identity: AuthenticatedIdentity, user_job: UserSavedJob, payload: JobUpdateRequest) -> dict:
    if "notes" in payload.model_fields_set:
        user_job.notes = payload.notes.strip() if payload.notes else None

    has_detail_update = any(
        field in payload.model_fields_set
        for field in ("title", "company", "source_url", "raw_description_text", "job_data")
    )
    if has_detail_update:
        job_cache = get_job_cache_for_saved_job(db, user_job)
        edited_job = get_user_edited_job_for_saved_job(db, user_job)
        title, company, source_url, raw_description_text, current_job_data = _effective_job_fields(job_cache, edited_job)
        next_source_url = str(payload.source_url) if "source_url" in payload.model_fields_set and payload.source_url else source_url
        next_job_data = payload.job_data if "job_data" in payload.model_fields_set and payload.job_data is not None else current_job_data
        if edited_job is None:
            edited_job = create_user_edited_job(
                db,
                identity,
                title=payload.title if payload.title is not None else title,
                company=payload.company if payload.company is not None else company,
                source_url=next_source_url,
                raw_description_text=(
                    payload.raw_description_text.strip()
                    if payload.raw_description_text is not None
                    else raw_description_text
                ),
                job_data=next_job_data,
            )
            user_job.user_edited_job_id = edited_job.id
        else:
            edited_job = update_user_edited_job(
                db,
                edited_job,
                title=payload.title if payload.title is not None else title,
                company=payload.company if payload.company is not None else company,
                source_url=next_source_url,
                raw_description_text=(
                    payload.raw_description_text.strip()
                    if payload.raw_description_text is not None
                    else raw_description_text
                ),
                job_data=next_job_data,
            )
    else:
        edited_job = get_user_edited_job_for_saved_job(db, user_job)
        job_cache = get_job_cache_for_saved_job(db, user_job)

    db.flush()
    db.refresh(user_job)
    return _job_response(user_job, job_cache, edited_job, _latest_match_for_user_job(db, identity, user_job.id))


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

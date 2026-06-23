from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.jobs import repository
from app.modules.jobs.schemas import (
    JobDescriptionData,
    JobDraftResponse,
    JobImportRequest,
    JobResponse,
    JobSaveRequest,
    JobUpdateRequest,
)
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.resume_job_match.job_url_import import fetch_job_page_text_from_url

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_description_parser(request: Request) -> JobDescriptionParser:
    runtime = request.app.state.runtime
    return OpenAIJobDescriptionParser(model=runtime.openai_model)


def resolve_raw_job_text(payload: JobImportRequest) -> str:
    if payload.job_url:
        return fetch_job_page_text_from_url(str(payload.job_url))
    return (payload.job_description_text or "").strip()


def build_job_draft(payload: JobImportRequest, parser: JobDescriptionParser, db: Session | None = None) -> JobDraftResponse:
    if db is not None and payload.job_url:
        cached_job = repository.get_cached_job_by_source_url(db, str(payload.job_url))
        if cached_job is not None:
            return JobDraftResponse(
                source_url=cached_job.source_url,
                raw_description_text=cached_job.raw_description_text,
                job_data=JobDescriptionData.model_validate(cached_job.job_data),
                fields_missing=[],
            )
    raw_text = resolve_raw_job_text(payload)
    job_data = parser.parse(raw_text)
    missing_fields = [
        field
        for field in ("title", "company", "summary")
        if not getattr(job_data, field).strip()
    ]
    return JobDraftResponse(
        source_url=str(payload.job_url) if payload.job_url else None,
        raw_description_text=raw_text,
        job_data=job_data,
        fields_missing=missing_fields,
    )


@router.get("", response_model=list[JobResponse])
def list_jobs(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    return repository.list_jobs(db, identity)


@router.post("/draft", response_model=JobDraftResponse)
def draft_job_description(
    payload: JobImportRequest,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
) -> JobDraftResponse:
    return build_job_draft(payload, parser, db)


@router.post("/import-description", response_model=JobResponse)
def import_job_description(
    payload: JobImportRequest,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    if payload.job_url:
        cached_job = repository.get_cached_job_by_source_url(db, str(payload.job_url))
        if cached_job is not None:
            return repository.create_job_from_description(
                db,
                identity,
                source_url=cached_job.source_url,
                raw_description_text=cached_job.raw_description_text,
                job_data=JobDescriptionData.model_validate(cached_job.job_data),
            )
    raw_text = resolve_raw_job_text(payload)
    job_data = parser.parse(raw_text)
    return repository.create_job_from_description(
        db,
        identity,
        source_url=str(payload.job_url) if payload.job_url else None,
        raw_description_text=raw_text,
        job_data=job_data,
    )


@router.post("", response_model=JobResponse)
def create_job(
    payload: JobSaveRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    return repository.create_job(db, identity, payload)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository.job_response_for_identity(db, identity, user_job)


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: int,
    payload: JobUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository.update_job(db, identity, user_job, payload)

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.jobs import repository
from app.modules.jobs.schemas import JobDraftResponse, JobImportRequest, JobResponse, JobSaveRequest, JobUpdateRequest
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


def build_job_draft(payload: JobImportRequest, parser: JobDescriptionParser) -> JobDraftResponse:
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
) -> JobDraftResponse:
    return build_job_draft(payload, parser)


@router.post("/import-description", response_model=JobResponse)
def import_job_description(
    payload: JobImportRequest,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
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
    job_id: str,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    job = repository.get_job_for_identity(db, identity, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository._job_response(job)


@router.patch("/{job_id}", response_model=JobResponse)
def update_job(
    job_id: str,
    payload: JobUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    job = repository.get_job_for_identity(db, identity, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return repository.update_job(db, job, payload)

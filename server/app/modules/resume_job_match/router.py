from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository as document_repository
from app.modules.resume_job_match.job_url_import import fetch_job_description_from_url
from app.modules.resume_job_match.schemas import (
    JobUrlExtractRequest,
    JobUrlExtractResponse,
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
)
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher

router = APIRouter(prefix="/resume-job-matches", tags=["resume-job-matches"])


def get_resume_job_matcher(request: Request) -> ResumeJobMatcher:
    runtime = request.app.state.runtime
    return OpenAIResumeJobMatcher(model=runtime.openai_model)


def resolve_resume_text(
    payload: ResumeJobMatchRequest,
    db: Session,
    identity: AuthenticatedIdentity,
) -> str:
    if payload.resume_document_id:
        document = document_repository.get_document_for_identity(db, identity, payload.resume_document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume document not found.")
        latest = document_repository.get_latest_version(db, document)
        if latest is None or not latest.extracted_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Resume document does not have extracted text available.",
            )
        return latest.extracted_text
    return (payload.resume_text or "").strip()


def resolve_job_description_text(payload: ResumeJobMatchRequest) -> str:
    if payload.job_url:
        return fetch_job_description_from_url(str(payload.job_url))
    return (payload.job_description_text or "").strip()


@router.post("/job-url-extract", response_model=JobUrlExtractResponse)
def extract_job_url(payload: JobUrlExtractRequest) -> JobUrlExtractResponse:
    extracted_text = fetch_job_description_from_url(str(payload.job_url))
    return JobUrlExtractResponse(
        job_url=str(payload.job_url),
        extracted_text=extracted_text,
        character_count=len(extracted_text),
    )


@router.post("", response_model=ResumeJobMatchResponse)
def create_resume_job_match(
    payload: ResumeJobMatchRequest,
    matcher: ResumeJobMatcher = Depends(get_resume_job_matcher),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeJobMatchResponse:
    resolved_payload = ResumeJobMatchRequest(
        resume_text=resolve_resume_text(payload, db, identity),
        job_description_text=resolve_job_description_text(payload),
    )
    return matcher.compare(resolved_payload)

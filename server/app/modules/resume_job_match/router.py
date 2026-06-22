from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository as document_repository
from app.modules.jobs import repository as job_repository
from app.modules.jobs.schemas import JobDescriptionData
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.profiles import repository as profile_repository
from app.modules.resume_job_match.job_url_import import fetch_job_description_from_url
from app.modules.resume_job_match.job_url_import import fetch_job_page_text_from_url
from app.modules.resume_job_match.schemas import (
    JobUrlExtractRequest,
    JobUrlExtractResponse,
    PendingMatchedJob,
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
)
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher

router = APIRouter(prefix="/resume-job-matches", tags=["resume-job-matches"])


def get_resume_job_matcher(request: Request) -> ResumeJobMatcher:
    runtime = request.app.state.runtime
    return OpenAIResumeJobMatcher(model=runtime.openai_model)


def get_match_job_description_parser(request: Request) -> JobDescriptionParser:
    runtime = request.app.state.runtime
    return OpenAIJobDescriptionParser(model=runtime.openai_model)


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


def _has_resume_facts(resume_data: dict) -> bool:
    for value in resume_data.values():
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, list) and value:
            return True
    return False


def resolve_resume_data_for_match(
    payload: ResumeJobMatchRequest,
    db: Session,
    identity: AuthenticatedIdentity,
) -> dict:
    profile = profile_repository.get_or_create_profile(db, identity)
    if _has_resume_facts(profile.resume_data):
        return profile.resume_data
    fallback_text = resolve_resume_text(payload, db, identity)
    return {"raw_resume_text": fallback_text}


def resolve_job_description_text(payload: ResumeJobMatchRequest) -> str:
    if payload.job_url:
        return fetch_job_description_from_url(str(payload.job_url))
    return (payload.job_description_text or "").strip()


def import_job_for_match(
    payload: ResumeJobMatchRequest,
    parser: JobDescriptionParser,
) -> tuple[str | None, str, JobDescriptionData]:
    if payload.job_url:
        source_url = str(payload.job_url)
        raw_text = fetch_job_page_text_from_url(source_url)
    else:
        source_url = None
        raw_text = (payload.job_description_text or "").strip()
    job_data = parser.parse(raw_text)
    return source_url, raw_text, job_data


def resume_match_reference(payload: ResumeJobMatchRequest) -> tuple[str | None, str]:
    if payload.resume_document_id:
        return payload.resume_document_id, "document"
    return None, "pasted_text"


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
    parser: JobDescriptionParser = Depends(get_match_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeJobMatchResponse:
    resume_data = resolve_resume_data_for_match(payload, db, identity)
    source_url, raw_text, job_data_model = import_job_for_match(payload, parser)
    job_data = job_data_model.model_dump()
    resolved_payload = ResumeJobMatchRequest(
        resume_text=json.dumps(resume_data, ensure_ascii=False, indent=2),
        job_description_text=json.dumps(job_data, ensure_ascii=False, indent=2),
        resume_data=resume_data,
        job_data=job_data,
    )
    result = matcher.compare(resolved_payload)
    resume_document_id, resume_source = resume_match_reference(payload)
    pending_job = PendingMatchedJob(
        title=job_data_model.title,
        company=job_data_model.company,
        source_url=source_url,
        raw_description_text=raw_text,
        job_data=job_data_model,
        notes=None,
        match_score=result.match_score,
        matched_resume_document_id=resume_document_id,
        matched_resume_source=resume_source,
    )
    if result.match_score >= 5:
        saved_job = job_repository.create_job_from_description(
            db,
            identity,
            source_url=source_url,
            raw_description_text=raw_text,
            job_data=job_data_model,
            match_score=result.match_score,
            matched_resume_document_id=resume_document_id,
            matched_resume_source=resume_source,
        )
        result.saved_job_id = saved_job["id"]
        result.job_saved = True
        result.pending_job = None
    else:
        result.saved_job_id = None
        result.job_saved = False
        result.pending_job = pending_job
    return result

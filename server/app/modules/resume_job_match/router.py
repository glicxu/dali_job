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
    SavePendingMatchedJobResponse,
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
    if payload.resume_profile_id:
        resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
        if resume_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
        return json.dumps(resume_profile.resume_data, ensure_ascii=False, indent=2)
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


def resolve_resume_data_for_match(
    payload: ResumeJobMatchRequest,
    db: Session,
    identity: AuthenticatedIdentity,
) -> dict:
    if payload.resume_profile_id:
        resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
        if resume_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
        return resume_profile.resume_data
    fallback_text = resolve_resume_text(payload, db, identity)
    return {"raw_resume_text": fallback_text}


def resolve_job_description_text(payload: ResumeJobMatchRequest) -> str:
    if payload.job_url:
        return fetch_job_description_from_url(str(payload.job_url))
    return (payload.job_description_text or "").strip()


def import_job_for_match(
    payload: ResumeJobMatchRequest,
    parser: JobDescriptionParser,
    db: Session,
    identity: AuthenticatedIdentity,
) -> tuple[str | None, str, JobDescriptionData]:
    if payload.job_url:
        source_url = str(payload.job_url)
        user_job = job_repository.get_user_job_by_source_url(db, identity, source_url)
        if user_job is not None:
            return user_job.source_url, user_job.raw_description_text, JobDescriptionData.model_validate(
                user_job.job_data
            )
        cached_job = job_repository.get_cached_job_by_source_url(db, source_url)
        if cached_job is not None:
            return cached_job.source_url, cached_job.raw_description_text, JobDescriptionData.model_validate(
                cached_job.job_data
            )
        raw_text = fetch_job_page_text_from_url(source_url)
    else:
        source_url = None
        raw_text = (payload.job_description_text or "").strip()
    job_data = parser.parse(raw_text)
    return source_url, raw_text, job_data


def resume_match_reference(payload: ResumeJobMatchRequest) -> tuple[int | None, int | None, str]:
    if payload.resume_profile_id:
        return payload.resume_profile_id, None, "resume_profile"
    if payload.resume_document_id:
        return None, payload.resume_document_id, "document"
    return None, None, "pasted_text"


def match_data_from_result(result: ResumeJobMatchResponse) -> dict:
    return result.model_dump(
        exclude={
            "id",
            "saved_job_id",
            "saved_match_id",
            "job_saved",
            "pending_job",
        }
    )


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
    source_url, raw_text, job_data_model = import_job_for_match(payload, parser, db, identity)
    job_data = job_data_model.model_dump()
    resolved_payload = ResumeJobMatchRequest(
        resume_text=json.dumps(resume_data, ensure_ascii=False, indent=2),
        job_description_text=json.dumps(job_data, ensure_ascii=False, indent=2),
        resume_data=resume_data,
        job_data=job_data,
    )
    result = matcher.compare(resolved_payload)
    resume_profile_id, resume_document_id, resume_source = resume_match_reference(payload)
    pending_job = PendingMatchedJob(
        title=job_data_model.title,
        company=job_data_model.company,
        source_url=source_url,
        raw_description_text=raw_text,
        job_data=job_data_model,
        notes=None,
        match_score=result.match_score,
        matched_resume_profile_id=resume_profile_id,
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
        )
        saved_match = job_repository.create_job_resume_match(
            db,
            identity,
            user_job_id=saved_job["id"],
            jobs_cache_id=saved_job["jobs_cache_id"],
            resume_profile_id=resume_profile_id,
            resume_document_id=resume_document_id,
            resume_source=resume_source,
            match_score=result.match_score,
            match_data=match_data_from_result(result),
        )
        result.saved_job_id = saved_job["id"]
        result.saved_match_id = saved_match["id"]
        result.job_saved = True
        result.pending_job = None
    else:
        result.saved_job_id = None
        result.job_saved = False
        result.pending_job = pending_job
    return result


@router.post("/pending-job", response_model=SavePendingMatchedJobResponse)
def save_pending_matched_job(
    payload: PendingMatchedJob,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> SavePendingMatchedJobResponse:
    saved_job = job_repository.create_job_from_description(
        db,
        identity,
        source_url=payload.source_url,
        raw_description_text=payload.raw_description_text,
        job_data=payload.job_data,
    )
    saved_match = job_repository.create_job_resume_match(
        db,
        identity,
        user_job_id=saved_job["id"],
        jobs_cache_id=saved_job["jobs_cache_id"],
        resume_profile_id=payload.matched_resume_profile_id,
        resume_document_id=payload.matched_resume_document_id,
        resume_source=payload.matched_resume_source,
        match_score=payload.match_score,
        match_data={"match_score": payload.match_score},
    )
    return SavePendingMatchedJobResponse(
        saved_job_id=saved_job["id"],
        saved_match_id=saved_match["id"],
    )

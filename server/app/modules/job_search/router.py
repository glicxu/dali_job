from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.core.provider_ops import GuardedProviderProxy, run_provider_call
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.job_search.apify_indeed import ApifyIndeedClient, get_apify_indeed_client
from app.modules.jobs import repository
from app.modules.jobs.schemas import (
    IndeedJobSearchImportRequest,
    IndeedJobSearchRequest,
    IndeedJobSearchResponse,
    IndeedJobSearchResult,
    JobDescriptionData,
    JobListImportResponse,
)
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.profiles import repository as profile_repository
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher

router = APIRouter(prefix="/job-search", tags=["job-search"])


def get_job_search_description_parser(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobDescriptionParser:
    runtime = request.app.state.runtime
    return cast(
        JobDescriptionParser,
        GuardedProviderProxy(
            factory=lambda: OpenAIJobDescriptionParser(model=runtime.openai_model),
            method_name="parse",
            request=request,
            identity=identity,
            provider="openai",
            feature="job_search_import_parse",
        ),
    )


def get_job_search_resume_matcher(
    request: Request,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ResumeJobMatcher:
    runtime = request.app.state.runtime
    return cast(
        ResumeJobMatcher,
        GuardedProviderProxy(
            factory=lambda: OpenAIResumeJobMatcher(model=runtime.openai_model),
            method_name="compare",
            request=request,
            identity=identity,
            provider="openai",
            feature="job_search_resume_match",
        ),
    )


def _match_data_from_result(result: ResumeJobMatchResponse) -> dict:
    return result.model_dump(
        exclude={
            "id",
            "saved_job_id",
            "saved_match_id",
            "job_saved",
            "pending_job",
        }
    )


def _raw_text_from_result(result: IndeedJobSearchResult) -> str:
    parts = [
        result.title,
        result.company,
        result.location,
        result.salary_range,
        result.employment_type,
        result.posted_at,
        result.summary,
        result.raw_description_text,
    ]
    return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip()


def _job_data_from_result(result: IndeedJobSearchResult, parsed: JobDescriptionData) -> JobDescriptionData:
    return parsed.model_copy(
        update={
            "title": parsed.title or result.title,
            "company": parsed.company or result.company,
            "summary": parsed.summary or result.summary,
            "employment_type": parsed.employment_type or result.employment_type,
            "work_location": parsed.work_location or result.location,
            "salary_range": parsed.salary_range or result.salary_range,
        }
    )


def _create_resume_profile_match(
    db: Session,
    identity: AuthenticatedIdentity,
    matcher: ResumeJobMatcher,
    *,
    resume_profile_id: int,
    saved_job: dict,
    job_data: JobDescriptionData,
) -> dict:
    resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    result = matcher.compare(
        ResumeJobMatchRequest(
            resume_text=json.dumps(resume_profile.resume_data, ensure_ascii=False, indent=2),
            job_description_text=json.dumps(job_data.model_dump(), ensure_ascii=False, indent=2),
            resume_data=resume_profile.resume_data,
            job_data=job_data.model_dump(),
        )
    )
    return repository.create_job_resume_match(
        db,
        identity,
        user_job_id=saved_job["id"],
        jobs_cache_id=saved_job["jobs_cache_id"],
        resume_profile_id=resume_profile_id,
        resume_document_id=None,
        resume_source="resume_profile",
        match_score=result.match_score,
        match_data=_match_data_from_result(result),
        model_name=result.provider_model_name,
        provider_execution_reference=result.provider_execution_reference,
    )


@router.post("/indeed", response_model=IndeedJobSearchResponse)
def search_indeed_jobs(
    payload: IndeedJobSearchRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    client: ApifyIndeedClient = Depends(get_apify_indeed_client),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> IndeedJobSearchResponse:
    results = run_provider_call(
        request,
        identity,
        provider="apify",
        feature="job_search",
        operation=lambda: client.search(
            keyword=payload.keyword.strip(),
            location=payload.location.strip(),
            max_results=payload.max_results,
        ),
        usage_units=len,
    )
    for result in results:
        cached_job = repository.get_cached_job_by_source_url(db, result.source_url)
        if cached_job is not None:
            result.status = "already_cached"
            result.jobs_cache_id = cached_job.id
    return IndeedJobSearchResponse(
        keyword=payload.keyword.strip(),
        location=payload.location.strip(),
        results=results,
    )


@router.post("/indeed/import", response_model=JobListImportResponse)
def import_indeed_search_results(
    payload: IndeedJobSearchImportRequest,
    parser: JobDescriptionParser = Depends(get_job_search_description_parser),
    matcher: ResumeJobMatcher = Depends(get_job_search_resume_matcher),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobListImportResponse:
    if payload.run_matching and payload.resume_profile_id:
        resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
        if resume_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")

    imported = []
    failed = []
    for result in payload.selected_results:
        response_source_url = result.source_url or f"apify-indeed:{result.external_id}"
        try:
            cached_job = repository.get_cached_job_by_source_url(db, result.source_url)
            if cached_job is not None:
                raw_text = cached_job.raw_description_text
            else:
                raw_text = _raw_text_from_result(result)
                if not raw_text:
                    raise ValueError("Apify result did not include a job description or summary.")
            saved_job = repository.create_job_from_source(
                db,
                identity,
                source_url=result.source_url,
                raw_description_text=raw_text,
                title=result.title,
                company=result.company,
                cache_write_source="provider_normalization",
            )
            match_score = None
            match_id = None
            if payload.run_matching and payload.resume_profile_id:
                user_job_for_match = repository.get_user_job_for_identity(db, identity, saved_job["id"])
                if user_job_for_match is None:
                    raise ValueError("Saved job could not be found for matching.")
                cached_for_match = repository.get_cached_job_by_id(db, saved_job["jobs_cache_id"])
                parsed_job_data = repository.ensure_saved_job_data(db, user_job_for_match, cached_for_match, parser)
                job_data = _job_data_from_result(result, parsed_job_data)
                edited_for_match = repository.get_user_edited_job_for_saved_job(db, user_job_for_match)
                if edited_for_match is not None:
                    edited_for_match.job_data = job_data.model_dump()
                    if job_data.title and not edited_for_match.title:
                        edited_for_match.title = job_data.title
                    if job_data.company and not edited_for_match.company:
                        edited_for_match.company = job_data.company
                elif cached_for_match is not None and cached_for_match.job_data is None:
                    cached_for_match.job_data = job_data.model_dump()
                    if job_data.title and not cached_for_match.title:
                        cached_for_match.title = job_data.title
                    if job_data.company and not cached_for_match.company:
                        cached_for_match.company = job_data.company
                db.flush()
                saved_match = _create_resume_profile_match(
                    db,
                    identity,
                    matcher,
                    resume_profile_id=payload.resume_profile_id,
                    saved_job=saved_job,
                    job_data=job_data,
                )
                match_score = saved_match["match_score"]
                match_id = saved_match["id"]
            imported.append(
                {
                    "user_job_id": saved_job["id"],
                    "jobs_cache_id": saved_job["jobs_cache_id"],
                    "source_url": response_source_url,
                    "title": job_data.title if payload.run_matching and payload.resume_profile_id else saved_job["title"],
                    "company": job_data.company if payload.run_matching and payload.resume_profile_id else saved_job["company"],
                    "match_score": match_score,
                    "match_id": match_id,
                }
            )
        except HTTPException as exc:
            failed.append({"source_url": response_source_url, "reason": str(exc.detail)})
        except Exception:
            failed.append(
                {
                    "source_url": response_source_url,
                    "reason": "This job could not be imported. Retry or add it manually.",
                }
            )
    return JobListImportResponse(imported=imported, failed=failed)

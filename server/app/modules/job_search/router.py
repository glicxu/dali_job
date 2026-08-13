from __future__ import annotations

import json
from typing import Callable, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.core.provider_ops import GuardedProviderProxy, run_provider_call
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.job_search.apify_indeed import ApifyIndeedClient, get_apify_indeed_client
from app.modules.job_search import criteria_repository
from app.modules.jobs import repository
from app.modules.jobs.schemas import (
    IndeedJobSearchImportRequest,
    IndeedJobSearchRequest,
    IndeedJobSearchResponse,
    IndeedJobSearchResult,
    JobDescriptionData,
    JobSearchCriterionCreateRequest,
    JobSearchCriterionListResponse,
    JobSearchCriterionResponse,
    JobSearchCriterionUpdateRequest,
    JobListImportResponse,
    QuickFindRequest,
    QuickFindResponse,
    QuickFindSaveRequest,
)
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.operations import repository as operation_repository
from app.modules.profiles import repository as profile_repository
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher
from app.modules.job_search.service import JobSearchProvider, JobSearchQuery, search_jobs

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


def recommended_keyword(resume_data: dict) -> str:
    keyword = criteria_repository.keyword_from_resume_data(resume_data)
    if keyword:
        return keyword
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="The default resume needs a target role, headline, or skills before DaliJob can recommend jobs.",
    )


def build_quick_find_recommendations(
    payload: QuickFindRequest,
    *,
    operation_id: int,
    provider: JobSearchProvider,
    parser: JobDescriptionParser,
    matcher: ResumeJobMatcher,
    db: Session,
    identity: AuthenticatedIdentity,
    progress: Callable[[int, int, str], None] | None = None,
) -> QuickFindResponse:
    resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
    if resume_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    if not resume_profile.is_default:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Select a default resume before finding recommendations.")

    criterion = None
    if payload.search_criterion_id is not None:
        criterion = criteria_repository.get_criterion(db, identity, payload.search_criterion_id)
        if criterion is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search criterion not found.")
        if criterion.resume_profile_id is not None and criterion.resume_profile_id != resume_profile.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="This saved search belongs to a different resume profile.",
            )

    keyword = criterion.keyword if criterion else (payload.keyword or "").strip() or recommended_keyword(resume_profile.resume_data)
    location = criterion.location.strip() if criterion and criterion.location else payload.location.strip()
    search_results = search_jobs(
        provider,
        JobSearchQuery(keyword=keyword, location=location, max_results=payload.max_results),
    )
    candidates = []
    warnings = []
    total = len(search_results)

    for index, result in enumerate(search_results, start=1):
        if progress:
            progress(index - 1, total, f"Preparing recommendation {index} of {total}")
        if not result.source_url:
            warnings.append(f"{result.title or 'One result'} was skipped because the provider did not return a source URL.")
            continue
        try:
            raw_text = _raw_text_from_result(result)
            cached_job = repository.get_cached_job_by_source_url(db, result.source_url)
            if cached_job is not None and cached_job.job_data is not None:
                job_data = JobDescriptionData.model_validate(cached_job.job_data)
            else:
                source_text = cached_job.raw_description_text if cached_job is not None else raw_text
                if not source_text:
                    raise ValueError("The provider did not return a job description.")
                parsed = parser.parse(source_text)
                job_data = _job_data_from_result(result, parsed)
                cached_job = repository.get_or_create_cache_job(
                    db,
                    source_url=result.source_url,
                    raw_description_text=source_text,
                    job_data=job_data,
                    title=job_data.title or result.title,
                    company=job_data.company or result.company,
                    cache_write_source="provider_normalization",
                )

            match_result = matcher.compare(
                ResumeJobMatchRequest(
                    resume_text=json.dumps(resume_profile.resume_data, ensure_ascii=False, indent=2),
                    job_description_text=json.dumps(job_data.model_dump(), ensure_ascii=False, indent=2),
                    resume_data=resume_profile.resume_data,
                    job_data=job_data.model_dump(),
                )
            )
            candidates.append(
                {
                    "jobs_cache_id": cached_job.id,
                    "source_url": cached_job.source_url,
                    "title": job_data.title or cached_job.title or result.title or "Untitled Job",
                    "company": job_data.company or cached_job.company or result.company or "Unknown company",
                    "location": job_data.work_location or result.location,
                    "summary": job_data.summary or result.summary,
                    "match_score": match_result.match_score,
                    "match_data": _match_data_from_result(match_result),
                    "resume_data_snapshot": resume_profile.resume_data,
                    "job_data_snapshot": job_data.model_dump(),
                    "model_name": match_result.provider_model_name,
                    "provider_execution_reference": match_result.provider_execution_reference,
                }
            )
        except HTTPException:
            raise
        except Exception:
            warnings.append(f"{result.title or 'One result'} could not be prepared for matching.")

    if progress:
        progress(total, total, "Recommendations ready")
    if criterion is not None:
        criteria_repository.mark_criterion_used(db, criterion, location=location)
    return QuickFindResponse(
        operation_id=operation_id,
        resume_profile_id=resume_profile.id,
        search_criterion_id=criterion.id if criterion else None,
        resume_title=resume_profile.title,
        keyword=keyword,
        location=location,
        candidates=candidates,
        warnings=warnings,
    )


@router.get("/criteria", response_model=JobSearchCriterionListResponse)
def list_search_criteria(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobSearchCriterionListResponse:
    return JobSearchCriterionListResponse(criteria=criteria_repository.list_criteria(db, identity))


@router.post("/criteria", response_model=JobSearchCriterionResponse)
def create_search_criterion(
    payload: JobSearchCriterionCreateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    if payload.resume_profile_id is not None:
        profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
        if profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")
    return criteria_repository.create_criterion(
        db,
        identity,
        keyword=payload.keyword,
        location=payload.location,
        resume_profile_id=payload.resume_profile_id,
    )


@router.patch("/criteria/{criterion_id}", response_model=JobSearchCriterionResponse)
def update_search_criterion(
    criterion_id: int,
    payload: JobSearchCriterionUpdateRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    criterion = criteria_repository.get_criterion(db, identity, criterion_id)
    if criterion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search criterion not found.")
    return criteria_repository.update_criterion(
        db,
        criterion,
        keyword=payload.keyword,
        location=payload.location,
    )


@router.delete("/criteria/{criterion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search_criterion(
    criterion_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    criterion = criteria_repository.get_criterion(db, identity, criterion_id)
    if criterion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search criterion not found.")
    criteria_repository.soft_delete_criterion(db, criterion)


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
    criterion = None
    if payload.search_criterion_id is not None:
        criterion = criteria_repository.get_criterion(db, identity, payload.search_criterion_id)
        if criterion is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search criterion not found.")

    keyword = criterion.keyword if criterion else payload.keyword.strip()
    location = criterion.location.strip() if criterion and criterion.location else payload.location.strip()
    results = run_provider_call(
        request,
        identity,
        provider="apify",
        feature="job_search",
        operation=lambda: client.search(
            keyword=keyword,
            location=location,
            max_results=payload.max_results,
        ),
        usage_units=len,
    )
    for result in results:
        cached_job = repository.get_cached_job_by_source_url(db, result.source_url)
        if cached_job is not None:
            result.status = "already_cached"
            result.jobs_cache_id = cached_job.id
    if criterion is not None:
        criteria_repository.mark_criterion_used(db, criterion, location=location)
    return IndeedJobSearchResponse(
        keyword=keyword,
        location=location,
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


@router.post("/quick-find/save", response_model=JobListImportResponse)
def save_quick_find_recommendations(
    payload: QuickFindSaveRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobListImportResponse:
    operation = operation_repository.get_operation_for_identity(db, identity, payload.operation_id)
    if operation is None or operation.operation_type != "quick_find_jobs":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick Find result not found.")
    if operation.status != "succeeded" or not isinstance(operation.result_payload, dict):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Quick Find recommendations are not ready to save.")

    recommendation = QuickFindResponse.model_validate(operation.result_payload)
    candidates = {candidate.jobs_cache_id: candidate for candidate in recommendation.candidates}
    imported = []
    failed = []
    for jobs_cache_id in payload.jobs_cache_ids:
        candidate = candidates.get(jobs_cache_id)
        if candidate is None:
            failed.append({"source_url": "", "reason": "The selected recommendation does not belong to this Quick Find result."})
            continue
        cached_job = repository.get_cached_job_by_id(db, jobs_cache_id)
        if cached_job is None or cached_job.deleted_at is not None:
            failed.append({"source_url": candidate.source_url, "reason": "The cached job is no longer available."})
            continue

        job_data = JobDescriptionData.model_validate(candidate.job_data_snapshot)
        saved_job = repository.create_job_from_description(
            db,
            identity,
            source_url=cached_job.source_url,
            raw_description_text=cached_job.raw_description_text,
            job_data=job_data,
        )
        user_job = repository.get_user_job_for_identity(db, identity, saved_job["id"])
        if user_job is None:
            failed.append({"source_url": candidate.source_url, "reason": "The saved job could not be created."})
            continue

        existing_match = next(
            (
                item
                for item in repository.list_job_resume_matches(db, identity, user_job)
                if candidate.provider_execution_reference
                and item["provider_execution_reference"] == candidate.provider_execution_reference
            ),
            None,
        )
        saved_match = existing_match or repository.create_job_resume_match(
            db,
            identity,
            user_job_id=user_job.id,
            jobs_cache_id=cached_job.id,
            resume_profile_id=recommendation.resume_profile_id,
            resume_document_id=None,
            resume_source="resume_profile",
            match_score=candidate.match_score,
            match_data=candidate.match_data,
            resume_data_snapshot=candidate.resume_data_snapshot,
            job_data_snapshot=candidate.job_data_snapshot,
            model_name=candidate.model_name,
            provider_execution_reference=candidate.provider_execution_reference,
        )
        imported.append(
            {
                "user_job_id": user_job.id,
                "jobs_cache_id": cached_job.id,
                "source_url": cached_job.source_url,
                "title": candidate.title,
                "company": candidate.company,
                "match_score": candidate.match_score,
                "match_id": saved_match["id"],
            }
        )

    return JobListImportResponse(imported=imported, failed=failed)

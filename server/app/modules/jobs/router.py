from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.core.provider_ops import GuardedProviderProxy, run_provider_call
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.jobs import repository
from app.modules.jobs.schemas import (
    JobDescriptionData,
    JobBulkDeleteRequest,
    JobBulkDeleteResponse,
    JobDraftResponse,
    JobImportRequest,
    JobListDiscoverRequest,
    JobListDiscoverResponse,
    JobListImportRequest,
    JobListImportResponse,
    JobResumeMatchListResponse,
    JobResponse,
    RecordDependencyResponse,
    JobSaveRequest,
    JobUpdateRequest,
)
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.profiles import repository as profile_repository
from app.modules.resume_job_match.job_url_import import discover_job_list_from_url, fetch_job_page_text_from_url
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_description_parser(
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
            feature="job_description_parse",
        ),
    )


def get_resume_job_matcher(
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
            feature="resume_job_match",
        ),
    )


def resolve_raw_job_text(payload: JobImportRequest) -> str:
    if payload.job_url:
        return fetch_job_page_text_from_url(str(payload.job_url))
    return (payload.job_description_text or "").strip()


def build_job_draft(
    payload: JobImportRequest,
    parser: JobDescriptionParser,
    db: Session | None = None,
    *,
    raw_text_override: str | None = None,
) -> JobDraftResponse:
    if db is not None and payload.job_url:
        cached_job = repository.get_cached_job_by_source_url(db, str(payload.job_url))
        if cached_job is not None:
            job_data = repository.ensure_job_data(db, cached_job, parser)
            return JobDraftResponse(
                source_url=cached_job.source_url,
                raw_description_text=cached_job.raw_description_text,
                job_data=job_data,
                fields_missing=[],
            )
    raw_text = raw_text_override if raw_text_override is not None else resolve_raw_job_text(payload)
    job_data = parser.parse(raw_text)
    if db is not None and payload.job_url:
        cached_job = repository.get_or_create_cache_job(
            db,
            source_url=str(payload.job_url),
            raw_description_text=raw_text,
            job_data=job_data,
            cache_write_source="source_extraction",
        )
        raw_text = cached_job.raw_description_text
        job_data = JobDescriptionData.model_validate(cached_job.job_data)
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


@router.get("", response_model=list[JobResponse])
def list_jobs(
    include_archived: bool = False,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> list[dict]:
    return repository.list_jobs(db, identity, include_archived=include_archived)


@router.post("/draft", response_model=JobDraftResponse)
def draft_job_description(
    payload: JobImportRequest,
    request: Request,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobDraftResponse:
    raw_text = None
    if payload.job_url and repository.get_cached_job_by_source_url(db, str(payload.job_url)) is None:
        raw_text = run_provider_call(
            request,
            identity,
            provider="web_extraction",
            feature="job_url_extract",
            operation=lambda: fetch_job_page_text_from_url(str(payload.job_url)),
            usage_units=lambda text: len(text),
        )
    return build_job_draft(payload, parser, db, raw_text_override=raw_text)


@router.post("/import-description", response_model=JobResponse)
def import_job_description(
    payload: JobImportRequest,
    request: Request,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    if payload.job_url:
        cached_job = repository.get_cached_job_by_source_url(db, str(payload.job_url))
        if cached_job is not None:
            job_data = repository.ensure_job_data(db, cached_job, parser)
            return repository.create_job_from_description(
                db,
                identity,
                source_url=cached_job.source_url,
                raw_description_text=cached_job.raw_description_text,
                job_data=job_data,
            )
    raw_text = (
        run_provider_call(
            request,
            identity,
            provider="web_extraction",
            feature="job_url_extract",
            operation=lambda: fetch_job_page_text_from_url(str(payload.job_url)),
            usage_units=lambda text: len(text),
        )
        if payload.job_url
        else resolve_raw_job_text(payload)
    )
    job_data = parser.parse(raw_text)
    return repository.create_job_from_description(
        db,
        identity,
        source_url=str(payload.job_url) if payload.job_url else None,
        raw_description_text=raw_text,
        job_data=job_data,
        cache_write_source="source_extraction" if payload.job_url else None,
    )


@router.post("/import-list/discover", response_model=JobListDiscoverResponse)
def discover_job_list(
    payload: JobListDiscoverRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobListDiscoverResponse:
    list_url = str(payload.list_url)
    discovery = run_provider_call(
        request,
        identity,
        provider="web_extraction",
        feature="job_list_discovery",
        operation=lambda: discover_job_list_from_url(list_url, max_results=payload.max_results),
        usage_units=lambda result: len(result.links),
    )
    discovered = discovery.links
    candidates = []
    for candidate in discovered:
        cached_job = repository.get_cached_job_by_source_url(db, candidate.source_url)
        candidates.append(
            {
                "title": cached_job.title if cached_job else candidate.title,
                "company": cached_job.company if cached_job else "",
                "source_url": candidate.source_url,
                "status": "already_cached" if cached_job else "new",
                "jobs_cache_id": cached_job.id if cached_job else None,
            }
        )
    return JobListDiscoverResponse(
        list_url=list_url,
        candidates=candidates,
        next_page_url=discovery.next_page_url,
        next_page_confidence=discovery.next_page_confidence,
        warnings=[],
    )


@router.post("/import-list", response_model=JobListImportResponse)
def import_job_list(
    payload: JobListImportRequest,
    request: Request,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    matcher: ResumeJobMatcher = Depends(get_resume_job_matcher),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobListImportResponse:
    if payload.run_matching and payload.resume_profile_id:
        resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
        if resume_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume profile not found.")

    imported = []
    failed = []
    selected_urls = list(dict.fromkeys(str(url) for url in payload.selected_urls))
    for source_url in selected_urls:
        try:
            cached_job = repository.get_cached_job_by_source_url(db, source_url)
            if cached_job is not None:
                raw_text = cached_job.raw_description_text
            else:
                raw_text = run_provider_call(
                    request,
                    identity,
                    provider="web_extraction",
                    feature="job_url_extract",
                    operation=lambda: fetch_job_page_text_from_url(source_url),
                    usage_units=lambda text: len(text),
                )
            saved_job = repository.create_job_from_source(
                db,
                identity,
                source_url=source_url,
                raw_description_text=raw_text,
                cache_write_source="source_extraction",
            )
            match_score = None
            match_id = None
            if payload.run_matching and payload.resume_profile_id:
                user_job_for_match = repository.get_user_job_for_identity(db, identity, saved_job["id"])
                if user_job_for_match is None:
                    raise ValueError("Saved job could not be found for matching.")
                cached_for_match = repository.get_cached_job_by_id(db, saved_job["jobs_cache_id"])
                job_data = repository.ensure_saved_job_data(db, user_job_for_match, cached_for_match, parser)
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
                    "source_url": source_url,
                    "title": job_data.title if payload.run_matching and payload.resume_profile_id else saved_job["title"],
                    "company": job_data.company if payload.run_matching and payload.resume_profile_id else saved_job["company"],
                    "match_score": match_score,
                    "match_id": match_id,
                }
            )
        except HTTPException as exc:
            failed.append({"source_url": source_url, "reason": str(exc.detail)})
        except Exception:
            failed.append(
                {
                    "source_url": source_url,
                    "reason": "This job could not be imported. Retry or add it manually.",
                }
            )
    return JobListImportResponse(imported=imported, failed=failed)


@router.post("", response_model=JobResponse)
def create_job(
    payload: JobSaveRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    return repository.create_job(db, identity, payload)


@router.post("/bulk-delete", response_model=JobBulkDeleteResponse)
def bulk_delete_jobs(
    payload: JobBulkDeleteRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobBulkDeleteResponse:
    deleted_job_ids, missing_job_ids, blocked_jobs = repository.delete_user_jobs(db, identity, payload.job_ids)
    db.commit()
    return JobBulkDeleteResponse(
        deleted_job_ids=deleted_job_ids,
        missing_job_ids=missing_job_ids,
        blocked_jobs=blocked_jobs,
    )


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


@router.get("/{job_id}/dependencies", response_model=RecordDependencyResponse)
def get_job_dependencies(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> RecordDependencyResponse:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    dependencies = repository.saved_job_dependencies(db, user_job)
    return RecordDependencyResponse(can_delete=not dependencies, dependencies=dependencies)


@router.get("/{job_id}/matches", response_model=JobResumeMatchListResponse)
def list_job_matches(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobResumeMatchListResponse:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return JobResumeMatchListResponse(matches=repository.list_job_resume_matches(db, identity, user_job))


@router.post("/{job_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
def archive_job(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    repository.archive_user_job(db, user_job)
    db.commit()


@router.post("/{job_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def restore_job(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    repository.restore_user_job(db, user_job)
    db.commit()


@router.post("/{job_id}/analyze", response_model=JobResponse)
def analyze_job(
    job_id: int,
    parser: JobDescriptionParser = Depends(get_job_description_parser),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    job_cache = repository.get_job_cache_for_saved_job(db, user_job)
    repository.ensure_saved_job_data(db, user_job, job_cache, parser)
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


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(
    job_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> None:
    user_job = repository.get_user_job_for_identity(db, identity, job_id)
    if user_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    dependencies = repository.delete_user_job(db, user_job)
    if dependencies:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": dependencies[0]["message"],
                "dependencies": dependencies,
            },
        )
    db.commit()

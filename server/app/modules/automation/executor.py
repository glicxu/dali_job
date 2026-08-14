from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import RuntimeConfig
from app.modules.accounts.models import User
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.automation.worker import ExecutionResult, LeaseLost, WorkItem, WorkerExecutionError
from app.modules.job_search.apify_indeed import ApifyIndeedClient
from app.modules.job_search.service import JobSearchProvider
from app.modules.jobs import repository as job_repository
from app.modules.jobs.schemas import IndeedJobSearchResult, JobDescriptionData
from app.modules.jobs.service import JobDescriptionParser, OpenAIJobDescriptionParser
from app.modules.jobs.models import JobResumeMatch
from app.modules.notifications.service import (
    create_email_delivery_if_enabled,
    create_in_app_delivery,
)
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest, ResumeJobMatchResponse
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher, ResumeJobMatcher


class ExecutedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    title: str
    company: str
    raw_description_text: str
    job_data: JobDescriptionData
    match_score: int = Field(..., ge=0, le=10)
    match_data: dict
    model_name: str | None = None
    provider_execution_reference: str | None = None


class ProviderAutomatedSearchExecutor:
    def __init__(
        self,
        *,
        search_provider: JobSearchProvider,
        parser: JobDescriptionParser,
        matcher: ResumeJobMatcher,
    ) -> None:
        self._search_provider = search_provider
        self._parser = parser
        self._matcher = matcher

    def execute(
        self,
        item: WorkItem,
        heartbeat: Callable[[], None],
    ) -> ExecutionResult:
        heartbeat()
        try:
            results = self._search_provider.search(
                keyword=item.keyword,
                location=item.location,
                max_results=item.max_results,
            )
        except HTTPException as exc:
            raise WorkerExecutionError(
                "job_search_provider_failed",
                "The job-search provider could not complete the scheduled search.",
                retryable=exc.status_code != 503,
                quota_chargeable=False,
            ) from exc
        except Exception as exc:
            raise WorkerExecutionError(
                "job_search_provider_failed",
                "The job-search provider could not complete the scheduled search.",
                retryable=True,
                quota_chargeable=False,
            ) from exc
        heartbeat()

        candidates: list[ExecutedCandidate] = []
        warnings: list[str] = []
        seen_urls: set[str] = set()
        for result in results:
            if not result.source_url or result.source_url in seen_urls:
                if not result.source_url:
                    warnings.append("A provider result was skipped because it did not include a source URL.")
                continue
            seen_urls.add(result.source_url)
            raw_text = _raw_text(result)
            if not raw_text:
                warnings.append(f"{result.title or 'A provider result'} had no usable job description.")
                continue
            try:
                heartbeat()
                parsed = self._parser.parse(raw_text)
                job_data = _merge_provider_fields(result, parsed)
                match = self._matcher.compare(
                    ResumeJobMatchRequest(
                        resume_text=json.dumps(item.resume_data_snapshot, ensure_ascii=False),
                        job_description_text=json.dumps(job_data.model_dump(), ensure_ascii=False),
                        resume_data=item.resume_data_snapshot,
                        job_data=job_data.model_dump(),
                    )
                )
                candidates.append(
                    ExecutedCandidate(
                        source_url=result.source_url,
                        title=job_data.title or result.title or "Untitled Job",
                        company=job_data.company or result.company or "Unknown company",
                        raw_description_text=raw_text,
                        job_data=job_data,
                        match_score=match.match_score,
                        match_data=_match_data(match),
                        model_name=match.provider_model_name,
                        provider_execution_reference=match.provider_execution_reference,
                    )
                )
                heartbeat()
                # Evaluate one usable provider result per automated search for
                # the initial product calibration period.
                break
            except LeaseLost:
                raise
            except Exception:
                warnings.append(f"{result.title or 'A provider result'} could not be matched.")

        if results and not candidates:
            raise WorkerExecutionError(
                "job_matching_failed",
                "Jobs were discovered, but none could be prepared for matching.",
                retryable=True,
                quota_chargeable=True,
            )
        return ExecutionResult(
            jobs_discovered=len(results),
            jobs_matched=len(candidates),
            result_payload={"warnings": warnings[:25]},
            artifacts=tuple(candidate.model_dump(mode="json") for candidate in candidates),
        )


class DatabaseAutomationResultPersister:
    def persist(
        self,
        db: Session,
        item: WorkItem,
        result: ExecutionResult,
    ) -> ExecutionResult:
        user = db.get(User, item.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            raise RuntimeError("automation user is unavailable during result persistence")
        identity = AuthenticatedIdentity(
            external_user_id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            timezone=user.timezone,
            provider="dalijob",
        )
        jobs_new = 0
        qualifying_match_ids: list[int] = []
        qualifying_job_ids: list[int] = []
        matches_notified = 0
        seen_urls: set[str] = set()
        for raw_candidate in result.artifacts:
            candidate = ExecutedCandidate.model_validate(raw_candidate)
            if candidate.source_url in seen_urls:
                continue
            seen_urls.add(candidate.source_url)
            existing_cache = job_repository.get_cached_job_by_source_url(db, candidate.source_url)
            cached_job = job_repository.get_or_create_cache_job(
                db,
                source_url=candidate.source_url,
                raw_description_text=candidate.raw_description_text,
                job_data=candidate.job_data,
                title=candidate.title,
                company=candidate.company,
                cache_write_source="provider_normalization",
            )
            if existing_cache is None:
                jobs_new += 1
            if candidate.match_score < item.minimum_match_score:
                continue
            user_job = job_repository.create_user_job(
                db,
                identity,
                jobs_cache_id=cached_job.id,
            )
            resume_hash = job_repository.canonical_json_hash(item.resume_data_snapshot)
            job_snapshot = candidate.job_data.model_dump(mode="json")
            job_hash = job_repository.canonical_json_hash(job_snapshot)
            existing_match = db.scalar(
                select(JobResumeMatch)
                .where(
                    JobResumeMatch.user_id == item.user_id,
                    JobResumeMatch.user_job_id == user_job.id,
                    JobResumeMatch.resume_profile_id == item.resume_profile_id,
                    JobResumeMatch.resume_snapshot_hash == resume_hash,
                    JobResumeMatch.job_snapshot_hash == job_hash,
                    JobResumeMatch.deleted_at.is_(None),
                )
                .order_by(JobResumeMatch.id.desc())
                .limit(1)
            )
            if existing_match is not None:
                match_id = existing_match.id
            else:
                match = job_repository.create_job_resume_match(
                    db,
                    identity,
                    user_job_id=user_job.id,
                    jobs_cache_id=cached_job.id,
                    resume_profile_id=item.resume_profile_id,
                    resume_source="resume_profile",
                    match_origin="automated_search",
                    match_score=candidate.match_score,
                    match_data=candidate.match_data,
                    resume_data_snapshot=item.resume_data_snapshot,
                    job_data_snapshot=job_snapshot,
                    model_name=candidate.model_name,
                    provider_execution_reference=candidate.provider_execution_reference,
                )
                match_id = int(match["id"])
            qualifying_job_ids.append(user_job.id)
            qualifying_match_ids.append(match_id)
            _delivery, created = create_in_app_delivery(
                db,
                workspace_id=item.workspace_id,
                user_id=item.user_id,
                schedule_id=item.schedule_id,
                job_resume_match_id=match_id,
                canonical_job_id=cached_job.id,
            )
            if created:
                matches_notified += 1
            create_email_delivery_if_enabled(
                db,
                workspace_id=item.workspace_id,
                user_id=item.user_id,
                schedule_id=item.schedule_id,
                job_resume_match_id=match_id,
                canonical_job_id=cached_job.id,
            )

        return ExecutionResult(
            jobs_discovered=result.jobs_discovered,
            jobs_new=jobs_new,
            jobs_matched=result.jobs_matched,
            matches_notified=matches_notified,
            result_payload={
                **dict(result.result_payload),
                "qualifying_job_ids": qualifying_job_ids,
                "qualifying_match_ids": qualifying_match_ids,
            },
        )


def build_default_executor(runtime: RuntimeConfig) -> ProviderAutomatedSearchExecutor:
    return ProviderAutomatedSearchExecutor(
        search_provider=ApifyIndeedClient(),
        parser=OpenAIJobDescriptionParser(model=runtime.openai_model),
        matcher=OpenAIResumeJobMatcher(model=runtime.openai_model),
    )


def _raw_text(result: IndeedJobSearchResult) -> str:
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


def _merge_provider_fields(
    result: IndeedJobSearchResult,
    parsed: JobDescriptionData,
) -> JobDescriptionData:
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


def _match_data(result: ResumeJobMatchResponse) -> dict:
    return result.model_dump(
        mode="json",
        exclude={
            "id",
            "saved_job_id",
            "saved_match_id",
            "job_saved",
            "pending_job",
        },
    )

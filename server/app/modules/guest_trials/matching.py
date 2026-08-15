from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.provider_ops import run_provider_call
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.guest_trials.models import (
    GuestMatchCandidate,
    GuestMatchOperation,
    GuestMatchResult,
    GuestProviderAttempt,
    GuestResumeProfile,
    GuestSearchCriterion,
    GuestTrial,
)
from app.modules.guest_trials.schemas import GuestBestMatchResponse, GuestMatchStatusResponse
from app.modules.jobs.schemas import IndeedJobSearchResult
from app.modules.profiles.readiness import evaluate_profile_readiness
from app.modules.profiles.schemas import ResumeData
from app.modules.resume_job_match.schemas import ResumeJobMatchRequest
from app.modules.resume_job_match.service import ResumeJobMatcher

MAX_GUEST_CANDIDATES = 5
SEARCH_RESERVATION_TIMEOUT = timedelta(minutes=10)
MAX_GUEST_JOB_DESCRIPTION_CHARS = 6_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _guest_identity(trial: GuestTrial) -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        external_user_id=f"guest:{trial.public_id}",
        email="guest@invalid.local",
        display_name="Guest trial",
        provider="guest",
    )


def _raw_job_text(result: IndeedJobSearchResult) -> str:
    parts = [
        result.title,
        result.company,
        result.location,
        result.summary,
        result.raw_description_text,
        result.employment_type,
        result.salary_range,
    ]
    return "\n\n".join(part.strip() for part in parts if part and part.strip()).strip()


def get_match_operation(db: Session, trial: GuestTrial) -> GuestMatchOperation | None:
    return db.scalar(
        select(GuestMatchOperation).where(GuestMatchOperation.guest_trial_id == trial.id).limit(1)
    )


def get_match_result(db: Session, trial: GuestTrial) -> GuestMatchResult | None:
    return db.scalar(select(GuestMatchResult).where(GuestMatchResult.guest_trial_id == trial.id).limit(1))


def _result_response(result: GuestMatchResult) -> GuestBestMatchResponse:
    job = result.job_snapshot
    match = result.match_data
    return GuestBestMatchResponse(
        title=str(job.get("title") or "Untitled Job"),
        company=str(job.get("company") or "Unknown company"),
        location=str(job.get("location") or ""),
        source_url=result.source_url,
        match_score=result.match_score,
        summary=str(match.get("summary") or ""),
        job_description=str(job.get("raw_description_text") or job.get("summary") or "").strip()[
            :MAX_GUEST_JOB_DESCRIPTION_CHARS
        ],
        matched_skills=list(match.get("matched_skills") or []),
        missing_skills=list(match.get("missing_skills") or []),
        supported_requirements=list(match.get("supported_requirements") or []),
        unsupported_requirements=list(match.get("unsupported_requirements") or []),
        recommended_resume_updates=list(match.get("recommended_resume_updates") or []),
    )


def match_status(db: Session, trial: GuestTrial) -> GuestMatchStatusResponse:
    operation = get_match_operation(db, trial)
    result = get_match_result(db, trial)
    status_value = operation.status if operation else "not_started"
    return GuestMatchStatusResponse(
        operation_id=operation.id if operation else None,
        status=status_value,
        provider_search_state=trial.provider_search_state,
        retryable=bool(operation and operation.status == "failed" and result is None),
        error_code=operation.error_code if operation else None,
        result=_result_response(result) if result else None,
    )


def require_ready_inputs(
    db: Session,
    trial: GuestTrial,
) -> tuple[GuestResumeProfile, GuestSearchCriterion]:
    profile = db.scalar(
        select(GuestResumeProfile).where(GuestResumeProfile.guest_trial_id == trial.id).limit(1)
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Confirm a profile first.")
    readiness = evaluate_profile_readiness(profile.resume_data)
    if not readiness.ready:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Profile is not ready for matching.",
                "missing_requirements": [item.model_dump() for item in readiness.missing_requirements],
            },
        )
    criterion = db.scalar(
        select(GuestSearchCriterion).where(GuestSearchCriterion.guest_trial_id == trial.id).limit(1)
    )
    if criterion is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Add a target role and location first.",
        )
    return profile, criterion


def reserve_provider_search(
    db: Session,
    trial: GuestTrial,
    *,
    idempotency_key: str,
) -> tuple[GuestMatchOperation, GuestProviderAttempt | None, bool]:
    locked_trial = db.scalar(select(GuestTrial).where(GuestTrial.id == trial.id).with_for_update())
    if locked_trial is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest trial not found.")
    operation = get_match_operation(db, locked_trial)
    if operation is None:
        operation = GuestMatchOperation(guest_trial_id=locked_trial.id, status="pending", attempt_count=0)
        db.add(operation)
        db.flush()
    if get_match_result(db, locked_trial) is not None:
        return operation, None, False
    if locked_trial.provider_search_state == "consumed":
        return operation, None, False
    if locked_trial.provider_search_state == "reserved":
        reserved_attempt = db.scalar(
            select(GuestProviderAttempt)
            .where(
                GuestProviderAttempt.guest_trial_id == locked_trial.id,
                GuestProviderAttempt.state == "reserved",
            )
            .order_by(GuestProviderAttempt.reserved_at.desc())
            .limit(1)
        )
        if reserved_attempt is None or _as_utc(reserved_attempt.reserved_at) > utc_now() - SEARCH_RESERVATION_TIMEOUT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Guest match is already in progress.")
        reserved_attempt.state = "released"
        reserved_attempt.safe_outcome = "stale_reservation_recovered"
        reserved_attempt.failure_category = "worker_interrupted"
        reserved_attempt.released_at = utc_now()
        locked_trial.provider_search_state = "released"

    attempt = db.scalar(
        select(GuestProviderAttempt).where(
            GuestProviderAttempt.guest_trial_id == locked_trial.id,
            GuestProviderAttempt.idempotency_key == idempotency_key,
        )
    )
    if attempt is None:
        attempt = GuestProviderAttempt(
            guest_trial_id=locked_trial.id,
            idempotency_key=idempotency_key,
            provider_feature="job_search",
            state="reserved",
        )
        db.add(attempt)
    else:
        attempt.state = "reserved"
        attempt.safe_outcome = None
        attempt.failure_category = None
        attempt.reserved_at = utc_now()
        attempt.released_at = None
    locked_trial.provider_search_state = "reserved"
    locked_trial.status = "matching"
    operation.status = "searching"
    operation.error_code = None
    operation.attempt_count += 1
    db.flush()
    return operation, attempt, True


def release_provider_search(
    db: Session,
    trial: GuestTrial,
    operation: GuestMatchOperation,
    attempt: GuestProviderAttempt,
    *,
    error_code: str,
    failure_category: str,
) -> None:
    attempt.state = "released"
    attempt.safe_outcome = error_code
    attempt.failure_category = failure_category
    attempt.released_at = utc_now()
    trial.provider_search_state = "released"
    trial.status = "active"
    operation.status = "failed"
    operation.error_code = error_code
    db.flush()


def retain_and_consume_candidates(
    db: Session,
    trial: GuestTrial,
    operation: GuestMatchOperation,
    attempt: GuestProviderAttempt,
    results: list[IndeedJobSearchResult],
) -> list[GuestMatchCandidate]:
    candidates: list[GuestMatchCandidate] = []
    for provider_rank, result in enumerate(results, start=1):
        raw_text = _raw_job_text(result)
        if not raw_text or not result.source_url:
            continue
        candidate = GuestMatchCandidate(
            guest_trial_id=trial.id,
            operation_id=operation.id,
            provider_rank=provider_rank,
            job_snapshot={**result.model_dump(mode="json"), "raw_match_text": raw_text},
        )
        db.add(candidate)
        candidates.append(candidate)
    if not candidates:
        release_provider_search(
            db,
            trial,
            operation,
            attempt,
            error_code="no_usable_jobs",
            failure_category="unusable_response",
        )
        return []
    attempt.state = "consumed"
    attempt.safe_outcome = "usable_search_response"
    attempt.consumed_at = utc_now()
    trial.provider_search_state = "consumed"
    trial.status = "matching"
    operation.status = "matching"
    operation.error_code = None
    db.flush()
    return candidates


def retained_candidates(db: Session, operation: GuestMatchOperation) -> list[GuestMatchCandidate]:
    return list(
        db.scalars(
            select(GuestMatchCandidate)
            .where(GuestMatchCandidate.operation_id == operation.id)
            .order_by(GuestMatchCandidate.provider_rank)
        ).all()
    )


def match_retained_candidates(
    request: Request,
    db: Session,
    trial: GuestTrial,
    operation: GuestMatchOperation,
    profile: GuestResumeProfile,
    matcher: ResumeJobMatcher,
) -> GuestMatchResult | None:
    resume_data = ResumeData.model_validate(profile.resume_data).model_dump()
    identity = _guest_identity(trial)
    candidates = retained_candidates(db, operation)
    for candidate in candidates:
        if candidate.match_data is not None:
            continue
        job_text = str(candidate.job_snapshot.get("raw_match_text") or "")
        try:
            match = run_provider_call(
                request,
                identity,
                provider="openai",
                feature="guest_resume_job_match",
                operation=lambda: matcher.compare(
                    ResumeJobMatchRequest(
                        resume_text=json.dumps(resume_data, ensure_ascii=False),
                        job_description_text=job_text,
                        resume_data=resume_data,
                        job_data=candidate.job_snapshot,
                    )
                ),
            )
        except HTTPException:
            candidate.matcher_provenance = {"outcome": "failed", "failure_code": "provider_failure"}
            db.flush()
            db.commit()
            continue
        candidate.match_score = match.match_score
        candidate.match_data = match.model_dump()
        candidate.matcher_provenance = {
            "outcome": "succeeded",
            "model": match.provider_model_name,
            "execution_reference": match.provider_execution_reference,
        }
        candidate.matched_at = utc_now()
        db.flush()
        db.commit()

    candidates = retained_candidates(db, operation)
    matched = [item for item in candidates if item.match_data is not None and item.match_score is not None]
    if not matched:
        operation.status = "failed"
        operation.error_code = "matcher_unavailable"
        db.flush()
        return None
    best = max(matched, key=lambda item: (int(item.match_score or 0), -item.provider_rank))
    existing = get_match_result(db, trial)
    if existing is not None:
        return existing
    result = GuestMatchResult(
        guest_trial_id=trial.id,
        operation_id=operation.id,
        candidate_id=best.id,
        profile_snapshot=resume_data,
        job_snapshot=best.job_snapshot,
        match_score=int(best.match_score or 0),
        match_data=best.match_data or {},
        source_url=best.job_snapshot.get("source_url"),
    )
    db.add(result)
    operation.status = "result_ready"
    operation.error_code = None
    operation.completed_at = utc_now()
    trial.status = "result_ready"
    db.flush()
    db.refresh(result)
    return result

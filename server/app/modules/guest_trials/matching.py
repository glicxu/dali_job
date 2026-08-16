from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.guest_trials.models import (
    GuestDocument,
    GuestMatchCandidate,
    GuestMatchOperation,
    GuestMatchResult,
    GuestResumeProfile,
    GuestSearchCriterion,
    GuestTrial,
)
from app.modules.guest_trials.schemas import GuestBestMatchResponse, GuestMatchStatusResponse
from app.modules.jobs.models import JobCache
from app.modules.matching_v2.canonical import (
    CANONICALIZATION_VERSION,
    EvidenceSpan,
    build_evidence_spans,
    canonicalize_text,
)
from app.modules.matching_v2.explanations import render_match_explanation
from app.modules.matching_v2.eligibility import evaluate_eligibility
from app.modules.matching_v2.extraction import CandidateProfileExtractor
from app.modules.matching_v2.models import (
    CandidateCareerProfile,
    CandidateProfileVersion,
    JobProfileVersion,
    JobRequirement,
)
from app.modules.matching_v2.qualification import (
    QualificationMatcher,
    build_qualification_input,
    select_candidate_career_context,
    validate_qualification_assessment,
)
from app.modules.matching_v2.registry import DEFAULT_REGISTRY, ROLE_TRACK_POLICIES
from app.modules.matching_v2.repositories import (
    ArtifactOwner,
    SpanInput,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
    create_or_get_qualification_assessment,
    find_cached_qualification_assessment,
    find_cached_candidate_profile,
    sync_policy_registry,
)
from app.modules.matching_v2.schemas import JobApplicationConstraintsResponse, QualificationAssessmentResponse
from app.modules.matching_v2.scoring import QualificationScoreItem, score_match
from app.modules.profiles.readiness import evaluate_profile_readiness
from app.modules.profiles.schemas import ResumeData


MAX_GUEST_JOB_DESCRIPTION_CHARS = 6_000
CATALOG_POLICY_VERSION = "guest-cached-job-catalog.v1"
_WORD_RE = re.compile(r"[a-z0-9+#.]+")
_LEVELS = ("student_or_intern", "entry", "junior", "mid", "senior", "staff", "principal")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        result_context="Best matching profile from the cached job catalog",
        score=match.get("score") if isinstance(match.get("score"), dict) else None,
        explanation=(
            match.get("explanation") if isinstance(match.get("explanation"), dict) else None
        ),
        policy_reason_codes=list((match.get("score") or {}).get("reason_codes") or []),
    )


def match_status(db: Session, trial: GuestTrial) -> GuestMatchStatusResponse:
    operation = get_match_operation(db, trial)
    result = get_match_result(db, trial)
    return GuestMatchStatusResponse(
        operation_id=operation.id if operation else None,
        status=operation.status if operation else "not_started",
        provider_search_state=trial.provider_search_state,
        retryable=bool(
            operation
            and operation.status == "failed"
            and result is None
            and operation.error_code != "cached_job_catalog_empty"
        ),
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


def begin_cached_match(db: Session, trial: GuestTrial, *, idempotency_key: str) -> GuestMatchOperation:
    locked_trial = db.scalar(select(GuestTrial).where(GuestTrial.id == trial.id).with_for_update())
    if locked_trial is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest trial not found.")
    operation = get_match_operation(db, locked_trial)
    if operation is None:
        operation = GuestMatchOperation(guest_trial_id=locked_trial.id, status="pending", attempt_count=0)
        db.add(operation)
        db.flush()
    elif operation.status in {"pending", "searching", "matching"}:
        if operation.idempotency_key == idempotency_key:
            return operation
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Guest match is already in progress.")
    # Retained for backwards API compatibility only. This flow performs no provider search.
    locked_trial.provider_search_state = "available"
    now = utc_now()
    locked_trial.status = "matching"
    operation.status = "pending"
    operation.error_code = None
    operation.idempotency_key = idempotency_key
    operation.correlation_id = operation.correlation_id or f"guest_match_{uuid.uuid4().hex}"
    operation.deadline_at = now + timedelta(seconds=90)
    operation.next_retry_at = None
    operation.lease_owner = None
    operation.lease_expires_at = None
    operation.completed_at = None
    db.flush()
    return operation


def claim_cached_match(
    db: Session,
    operation: GuestMatchOperation,
    *,
    worker_id: str,
) -> bool:
    now = utc_now()
    if operation.deadline_at is not None and _as_utc(operation.deadline_at) <= now:
        _fail(operation, db.get(GuestTrial, operation.guest_trial_id), "operation_deadline_exceeded")
        operation.completed_at = now
        return False
    if operation.status == "matching" and operation.lease_expires_at is not None:
        if _as_utc(operation.lease_expires_at) > now and operation.lease_owner != worker_id:
            return False
    if operation.status == "failed":
        if operation.attempt_count >= 3:
            return False
        if operation.next_retry_at is not None and _as_utc(operation.next_retry_at) > now:
            return False
    if operation.status not in {"pending", "matching", "failed"}:
        return False
    operation.status = "matching"
    operation.lease_owner = worker_id
    operation.lease_expires_at = now + timedelta(seconds=120)
    operation.heartbeat_at = now
    operation.attempt_count += 1
    operation.error_code = None
    db.flush()
    return True


def run_cached_profile_match(
    model_id: str,
    db: Session,
    trial: GuestTrial,
    operation: GuestMatchOperation,
    guest_profile: GuestResumeProfile,
    criterion: GuestSearchCriterion,
    candidate_extractor: CandidateProfileExtractor,
    matcher: QualificationMatcher,
) -> GuestMatchResult:
    owner = ArtifactOwner.guest(guest_trial_id=trial.id)
    try:
        candidate = _candidate_profile(
            db,
            owner=owner,
            guest_profile=guest_profile,
            extractor=candidate_extractor,
            model_id=model_id,
        )
    except (HTTPException, ValueError) as exc:
        _fail(operation, trial, "candidate_profile_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Candidate profiling is temporarily unavailable. Retry shortly.",
        ) from exc

    selected = select_cached_job_profile(db, candidate=candidate, criterion=criterion)
    if selected is None:
        _fail(operation, trial, "cached_job_catalog_empty")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No compatible cached Job Profile is available yet.",
        )
    job_profile, cache_job = selected
    operation.heartbeat_at = utc_now()
    operation.lease_expires_at = utc_now() + timedelta(seconds=120)
    db.flush()
    context = select_candidate_career_context(
        db,
        candidate_profile=candidate,
        job_profile=job_profile,
        selection_revision=1,
    )
    candidate_row = _retain_cached_candidate(db, trial, operation, job_profile, cache_job)
    try:
        qualification = _qualification(
            db,
            owner=owner,
            candidate=candidate,
            job_profile=job_profile,
            context=context,
            matcher=matcher,
        )
    except (HTTPException, ValueError) as exc:
        candidate_row.matcher_provenance = {"outcome": "failed", "failure_code": "provider_failure"}
        _fail(operation, trial, "matcher_unavailable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Matching is temporarily unavailable. Retry against the same cached job.",
        ) from exc

    match_score, match_data = _render_guest_match(db, qualification, job_profile)
    if operation.deadline_at is not None and _as_utc(operation.deadline_at) <= utc_now():
        _fail(operation, trial, "operation_deadline_exceeded")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Matching exceeded the operation deadline.",
        )
    candidate_row.match_score = match_score
    candidate_row.match_data = match_data
    candidate_row.matcher_provenance = {
        "outcome": "succeeded",
        "pipeline": "matching_v2",
        "model": qualification.model_id,
        "qualification_assessment_id": qualification.public_id,
        "catalog_policy_version": CATALOG_POLICY_VERSION,
    }
    candidate_row.matched_at = utc_now()
    existing = get_match_result(db, trial)
    if existing is not None:
        return existing
    result = GuestMatchResult(
        guest_trial_id=trial.id,
        operation_id=operation.id,
        candidate_id=candidate_row.id,
        candidate_profile_version_id=candidate.id,
        qualification_assessment_id=qualification.id,
        profile_snapshot={
            "resume_data": guest_profile.resume_data,
            "candidate_profile_id": candidate.public_id,
            "candidate_profile": candidate.artifact,
        },
        job_snapshot=candidate_row.job_snapshot,
        match_score=match_score,
        match_data=match_data,
        source_url=None,
    )
    db.add(result)
    operation.status = "result_ready"
    operation.error_code = None
    operation.completed_at = utc_now()
    operation.lease_owner = None
    operation.lease_expires_at = None
    trial.status = "result_ready"
    db.flush()
    db.refresh(result)
    return result


def select_cached_job_profile(
    db: Session,
    *,
    candidate: CandidateProfileVersion,
    criterion: GuestSearchCriterion,
) -> tuple[JobProfileVersion, JobCache] | None:
    rows = list(
        db.execute(
            select(JobProfileVersion, JobCache)
            .join(JobCache, JobCache.id == JobProfileVersion.jobs_cache_id)
            .where(
                JobProfileVersion.deleted_at.is_(None),
                JobProfileVersion.trial_eligible.is_(True),
                JobCache.deleted_at.is_(None),
                JobCache.lifecycle_state == "active",
                or_(JobCache.expires_at.is_(None), JobCache.expires_at > utc_now()),
                JobCache.raw_description_text != "",
            )
            .order_by(JobProfileVersion.created_at.desc(), JobProfileVersion.id.desc())
        ).all()
    )
    latest_by_cache: dict[int, tuple[JobProfileVersion, JobCache]] = {}
    for profile, cache in rows:
        latest_by_cache.setdefault(cache.id, (profile, cache))
    if not latest_by_cache:
        return None
    careers = list(
        db.scalars(
            select(CandidateCareerProfile).where(
                CandidateCareerProfile.candidate_profile_version_id == candidate.id
            )
        ).all()
    )
    if not careers:
        return None
    ranked = sorted(
        latest_by_cache.values(),
        key=lambda item: _catalog_rank(item[0], item[1], careers, criterion),
    )
    best = ranked[0]
    if _catalog_rank(best[0], best[1], careers, criterion)[0] >= 4:
        return None
    return best


def _candidate_profile(
    db: Session,
    *,
    owner: ArtifactOwner,
    guest_profile: GuestResumeProfile,
    extractor: CandidateProfileExtractor,
    model_id: str,
) -> CandidateProfileVersion:
    source_text, extraction_version = _guest_resume_source_text(db, guest_profile)
    canonical_text = canonicalize_text(source_text)
    spans = build_evidence_spans(canonical_text, source_prefix=f"guest_resume_{guest_profile.id}")
    if not spans:
        raise ValueError("Guest profile does not contain evidence spans.")
    source = create_or_get_canonical_source(
        db,
        owner=owner,
        source_type="resume",
        canonical_text=canonical_text,
        text_extraction_version=extraction_version,
        canonicalization_version=CANONICALIZATION_VERSION,
        guest_resume_profile_id=guest_profile.id,
        spans=[_span_input(item) for item in spans],
    )
    sync_policy_registry(db)
    cached = find_cached_candidate_profile(
        db,
        source=source,
        model_id=model_id,
    )
    if cached is not None:
        return cached
    extracted = extractor.extract(spans)
    return create_or_get_candidate_profile(
        db,
        source=source,
        artifact=extracted.artifact,
        model_id=extracted.model_id,
        provider_execution_reference=extracted.provider_execution_reference,
    )


def _qualification(db, *, owner, candidate, job_profile, context, matcher):
    cached = find_cached_qualification_assessment(
        db,
        candidate_profile=candidate,
        selection_revision=context.selection.revision,
        job_profile=job_profile,
        model_id=getattr(matcher, "model", None) or getattr(matcher, "_model", None) or candidate.model_id,
    )
    if cached is not None:
        return cached
    qualification_input = build_qualification_input(
        db,
        candidate_profile=candidate,
        job_profile=job_profile,
        career_context=context.career_profile,
    )
    result = matcher.assess(qualification_input)
    requirements = list(
        db.scalars(
            select(JobRequirement).where(JobRequirement.job_profile_version_id == job_profile.id)
        ).all()
    )
    arguments = {
        "requirements": requirements,
        "allowed_evidence_refs": qualification_input.allowed_evidence_refs,
        "allowed_alternative_group_refs": qualification_input.allowed_alternative_group_refs,
        "incomplete_evidence_input": bool(qualification_input.omitted_evidence_refs),
    }
    try:
        artifact = validate_qualification_assessment(result.artifact, **arguments)
    except ValueError as first_error:
        repair = getattr(matcher, "repair", None)
        if repair is None:
            raise
        result = repair(
            qualification_input,
            ({"code": "QUALIFICATION_SEMANTIC_VALIDATION_FAILED", "path": "$", "message": str(first_error)},),
        )
        artifact = validate_qualification_assessment(result.artifact, **arguments)
    warnings = []
    if qualification_input.omitted_evidence_refs:
        warnings.append(
            f"NEEDS_MORE_INFORMATION:OMITTED_CANDIDATE_EVIDENCE:{len(qualification_input.omitted_evidence_refs)}"
        )
    return create_or_get_qualification_assessment(
        db,
        owner=owner,
        candidate_profile=candidate,
        career_selection=context.selection,
        selected_career_profile=context.career_profile,
        selection_reason_code=context.reason_code,
        job_profile=job_profile,
        artifact=artifact,
        input_quality={
            "warnings": warnings,
            "omitted_evidence_count": len(qualification_input.omitted_evidence_refs),
            "complete": not qualification_input.omitted_evidence_refs,
            "validation_retry_count": result.retry_count,
        },
        model_id=result.model_id,
        provider_execution_reference=result.provider_execution_reference,
    )


def _render_guest_match(db: Session, qualification, job_profile: JobProfileVersion) -> tuple[int | None, dict]:
    requirements = list(
        db.scalars(
            select(JobRequirement).where(JobRequirement.job_profile_version_id == job_profile.id)
        ).all()
    )
    by_id = {item.requirement_id: item for item in requirements}
    artifact = QualificationAssessmentResponse.model_validate(qualification.artifact)
    items = [
        QualificationScoreItem(
            requirement_id=item.requirement_id,
            importance=by_id[item.requirement_id].importance,
            scoring_dimension=by_id[item.requirement_id].scoring_dimension,
            status=item.status,
        )
        for item in artifact.requirement_assessments
    ]
    career = job_profile.artifact["career_context"]
    eligibility = evaluate_eligibility(
        JobApplicationConstraintsResponse.model_validate(job_profile.artifact["application_constraints"]),
        None,
        job_country=(job_profile.artifact.get("location") or {}).get("country"),
    )
    score = score_match(
        role_family=career["primary_role_family"],
        track=career["track"],
        target_level=career["target_level"],
        level_confidence=career["confidence"],
        qualification_items=items,
        gates=eligibility.items,
    )
    explanation = render_match_explanation(
        qualification_items=artifact.requirement_assessments,
        requirement_statements={item.requirement_id: item.statement for item in requirements},
        preference_items=[],
        gates=score.gates,
        score=score,
    )
    legacy_score = (
        max(0, min(10, int((score.overall_score + 5) // 10)))
        if score.overall_score is not None
        else None
    )
    supported = list(explanation.strengths)
    unsupported = list(explanation.gaps)
    return legacy_score, {
        "pipeline": "matching_v2",
        "summary": explanation.summary,
        "matched_skills": [item.label for item in supported],
        "missing_skills": [item.label for item in unsupported],
        "supported_requirements": [item.model_dump(mode="json") for item in supported],
        "unsupported_requirements": [item.model_dump(mode="json") for item in unsupported],
        "recommended_resume_updates": list(
            dict.fromkeys(missing for item in artifact.requirement_assessments for missing in item.missing)
        ),
        "score": score.model_dump(mode="json"),
        "explanation": explanation.model_dump(mode="json"),
        "qualification_assessment_id": qualification.public_id,
        "job_profile_id": job_profile.public_id,
    }


def _retain_cached_candidate(db, trial, operation, job_profile, cache_job):
    candidate = db.scalar(
        select(GuestMatchCandidate)
        .where(GuestMatchCandidate.operation_id == operation.id)
        .order_by(GuestMatchCandidate.provider_rank)
        .limit(1)
    )
    if candidate is None:
        candidate = GuestMatchCandidate(
            guest_trial_id=trial.id,
            operation_id=operation.id,
            provider_rank=1,
            job_snapshot={},
        )
        db.add(candidate)
    location = (job_profile.artifact.get("location") or {}).get("display") or ""
    candidate.job_profile_version_id = job_profile.id
    candidate.job_snapshot = {
        "title": job_profile.artifact.get("title") or cache_job.title,
        "company": job_profile.artifact.get("company") or cache_job.company,
        "location": location,
        "raw_description_text": cache_job.raw_description_text,
        "job_profile_id": job_profile.public_id,
        "jobs_cache_id": cache_job.id,
    }
    candidate.match_score = None
    candidate.match_data = None
    candidate.matcher_provenance = None
    candidate.matched_at = None
    db.flush()
    return candidate


def _catalog_rank(profile, cache, careers, criterion):
    context = profile.artifact.get("career_context") or {}
    job_family = str(context.get("primary_role_family") or "unknown")
    job_track = str(context.get("track") or "unknown")
    policy = DEFAULT_REGISTRY.get("job_family_pre_match_policy", "job-family-pre-match.v1").content
    compatible_tracks = set(policy["compatible_tracks"].get(job_track, ()))
    adjacent = set(policy["adjacent_role_families"].get(job_family, ()))
    transferable = set(policy["transferable_role_families"].get(job_family, ()))

    def career_rank(career):
        if career.role_family == job_family:
            family_rank = 0
        elif career.role_family in adjacent:
            family_rank = 1
        elif career.role_family in transferable:
            family_rank = 2
        elif job_family == "unknown" or career.role_family == "unknown":
            family_rank = 3
        else:
            family_rank = 4
        track_rank = 0 if career.track == job_track else 1 if career.track in compatible_tracks else 2
        return family_rank, track_rank, _level_distance(career.level, str(context.get("target_level") or "unknown"))

    career_fit = min(career_rank(career) for career in careers)
    title_tokens = _tokens(str(profile.artifact.get("title") or cache.title))
    target_tokens = _tokens(criterion.keyword)
    location_rank = _location_rank(profile.artifact.get("location") or {}, criterion.location)
    warning_count = len((profile.cleanup or {}).get("warnings") or [])
    approved_rank = 0 if ROLE_TRACK_POLICIES.resolve_public(job_family, job_track) is not None else 1
    return (
        *career_fit,
        approved_rank,
        len(target_tokens - title_tokens),
        location_rank,
        warning_count,
        profile.trial_priority,
        -profile.id,
    )


def _location_rank(location: dict, target: str) -> int:
    normalized = target.strip().lower()
    display = str(location.get("display") or "").lower()
    workplace = str(location.get("workplace_type") or "unknown")
    if normalized in {"", "anywhere", "any"}:
        return 0
    if "remote" in normalized and workplace == "remote":
        return 0
    if normalized in display or (display and display in normalized):
        return 0
    if workplace == "unknown" or not display:
        return 1
    return 2


def _level_distance(left: str, right: str) -> int:
    try:
        return abs(_LEVELS.index(left) - _LEVELS.index(right))
    except ValueError:
        return len(_LEVELS)


def _tokens(value: str) -> set[str]:
    return {item for item in _WORD_RE.findall(value.lower()) if len(item) > 1}


def _guest_resume_source_text(db: Session, profile: GuestResumeProfile) -> tuple[str, str]:
    if profile.source_guest_document_id is not None:
        document = db.get(GuestDocument, profile.source_guest_document_id)
        if document is not None and document.extracted_text.strip():
            return document.extracted_text, "guest-document-extract.v1"
    data = ResumeData.model_validate(profile.resume_data).model_dump(mode="json")
    sections = []
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        heading = key.replace("_", " ").title()
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value)
        sections.append(f"{heading}\n{body}")
    return "\n\n".join(sections), "guest-resume-data.v1"


def _span_input(span: EvidenceSpan) -> SpanInput:
    return SpanInput(
        span_id=span.span_id,
        section=span.section,
        start_utf8_byte=span.start_utf8_byte,
        end_utf8_byte=span.end_utf8_byte,
        excerpt=span.excerpt,
    )


def _fail(operation: GuestMatchOperation, trial: GuestTrial, code: str) -> None:
    now = utc_now()
    operation.status = "failed"
    operation.error_code = code
    operation.lease_owner = None
    operation.lease_expires_at = None
    operation.heartbeat_at = now
    operation.next_retry_at = now + timedelta(seconds=min(60, 2 ** max(operation.attempt_count, 1)))
    if trial is not None:
        trial.status = "active"


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

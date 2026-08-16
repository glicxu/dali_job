from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.provider_ops import run_provider_call
from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.evaluation import repository
from app.modules.accounts.models import User
from app.modules.evaluation.benchmark import build_admission_report
from app.modules.evaluation.catalog import build_fixture_catalog
from app.modules.evaluation.metrics import calculate_aggregate_metrics, calculate_run_metrics, compare_runs
from app.modules.evaluation.export import build_corpus_export, corpus_markdown
from app.modules.evaluation.models import (
    EvaluationAnnotation,
    EvaluationArtifactReview,
    EvaluationJobSnapshot,
    EvaluationMatchReview,
    EvaluationRun,
)
from app.modules.evaluation.review import artifact_annotation_targets, build_disagreement_queue
from app.modules.evaluation.sources import match_company_source, source_company
from app.modules.evaluation.schemas import (
    EvaluationAnnotationCreateRequest,
    EvaluationAnnotationView,
    EvaluationMatchReviewCreateRequest,
    EvaluationMatchReviewSummaryView,
    EvaluationMatchReviewView,
    EvaluationAggregateMetricsView,
    EvaluationComparisonView,
    DisagreementQueueView,
    EvaluationMetricsView,
    EvaluationRunCreateRequest,
    EvaluationRunDetail,
    EvaluationRunListResponse,
    EvaluationRunSummary,
    EvaluationSourceView,
    EvidenceSpanView,
    JobSnapshotImportRequest,
    JobSnapshotListResponse,
    JobSnapshotReviewRequest,
    JobSnapshotView,
    BenchmarkAdmissionReportView,
    CandidateProfileEvaluationView,
    EvaluationArtifactReviewCreateRequest,
    EvaluationArtifactReviewView,
    EvaluationCandidateSourceListResponse,
    EvaluationFixtureCatalogView,
    JobProfileEvaluationView,
)
from app.modules.matching_v2.api_schemas import (
    CandidateProfileView,
    JobProfileView,
    QualificationAssessmentCreateRequest,
)
from app.modules.matching_v2.extraction import CandidateProfileExtractor, JobProfileExtractor
from app.modules.matching_v2.diagnostics import begin_matching_prompt_trace, end_matching_prompt_trace
from app.modules.matching_v2.models import (
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    QualificationAssessment,
    RequirementAssessment,
    SourceSpan,
)
from app.modules.matching_v2.qualification import QualificationMatcher
from app.modules.matching_v2.scoring import recommendation_for_score
from app.modules.matching_v2.router import (
    _candidate_profile_view,
    _job_profile_view,
    _qualification_assessment_view,
    create_candidate_profile,
    create_job_profile,
    create_qualification_assessment,
    get_candidate_profile_extractor,
    get_job_profile_extractor,
    get_qualification_matcher,
)
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.models import ResumeProfile
from app.modules.resume_job_match.job_url_import import JobExtractionResult, fetch_job_result_from_url

router = APIRouter(prefix="/internal/evaluation", tags=["matching-evaluation"])
JobSnapshotFetcher = Callable[[str], JobExtractionResult]


def get_job_snapshot_fetcher() -> JobSnapshotFetcher:
    return fetch_job_result_from_url


def _source_company(source_url: str) -> str:
    return source_company(source_url)


def _require_evaluation_access(request: Request, db: Session, identity: AuthenticatedIdentity):
    if not request.app.state.runtime.matching_v2.evaluation_enabled or identity.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return profile_repository.ensure_account_for_identity(db, identity)


def _snapshot_view(snapshot: EvaluationJobSnapshot) -> JobSnapshotView:
    return JobSnapshotView(
        public_id=snapshot.public_id,
        benchmark_release=snapshot.benchmark_release,
        coverage_slot=snapshot.coverage_slot,
        source_url=snapshot.source_url,
        source_hash=snapshot.source_hash,
        user_saved_job_id=snapshot.user_saved_job_id,
        title=snapshot.title,
        company=snapshot.company,
        raw_description_text=snapshot.raw_description_text,
        capture_metadata=snapshot.capture_metadata,
        review_status=snapshot.review_status,
        review_notes=snapshot.review_notes,
        reviewed_by_user_id=snapshot.reviewed_by_user_id,
        reviewed_at=snapshot.reviewed_at,
        created_at=snapshot.created_at,
    )


@router.post("/job-snapshots/import", response_model=JobSnapshotView)
def import_job_snapshot(
    payload: JobSnapshotImportRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    fetcher: JobSnapshotFetcher = Depends(get_job_snapshot_fetcher),
) -> JobSnapshotView:
    _require_evaluation_access(request, db, identity)
    source_url = str(payload.source_url)
    registry_entry = match_company_source(source_url)
    registry_company = str(registry_entry["company_name"]) if registry_entry is not None else ""
    is_e3 = payload.benchmark_release.startswith("matching-benchmark-jobs.e3")
    if is_e3 and registry_entry is None:
        raise HTTPException(
            status_code=422,
            detail="E3 job imports require an allowlisted employer job-detail URL.",
        )
    if is_e3 and (payload.level_band is None or payload.description_quality is None):
        raise HTTPException(
            status_code=422,
            detail="E3 job imports require level_band and description_quality.",
        )
    result = run_provider_call(
        request,
        identity,
        provider="web_extraction",
        feature="matching_evaluation_job_capture",
        operation=lambda: fetcher(source_url),
        usage_units=lambda item: len(item.focused_text),
    )
    if not result.focused_text.strip():
        raise HTTPException(status_code=422, detail="The job page did not contain usable description text.")
    snapshot = repository.create_or_get_snapshot(
        db,
        identity,
        benchmark_release=payload.benchmark_release,
        coverage_slot=payload.coverage_slot,
        source_url=source_url,
        raw_description_text=result.focused_text,
        title=(result.title or "").strip(),
        company=(
            registry_company
            if is_e3
            else (result.company or "").strip() or registry_company
        ),
        capture_metadata={
            "canonical_url": result.canonical_url,
            "location": result.location,
            "extraction_method": result.extraction_method,
            "extractor_version": result.extractor_version,
            "confidence": result.confidence,
            "warnings": result.warnings,
            "source_registry_company_id": (
                registry_entry["company_id"] if registry_entry is not None else None
            ),
            "ats_family": registry_entry["ats_family"] if registry_entry is not None else None,
            "level_band": payload.level_band,
            "description_quality": payload.description_quality,
        },
    )
    return _snapshot_view(snapshot)


@router.get("/job-snapshots", response_model=JobSnapshotListResponse)
def get_job_snapshots(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobSnapshotListResponse:
    _, workspace = _require_evaluation_access(request, db, identity)
    return JobSnapshotListResponse(
        snapshots=[_snapshot_view(item) for item in repository.list_snapshots(db, workspace_id=workspace.id)]
    )


@router.post("/job-snapshots/{snapshot_id}/review", response_model=JobSnapshotView)
def review_job_snapshot(
    snapshot_id: str,
    payload: JobSnapshotReviewRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> JobSnapshotView:
    user, workspace = _require_evaluation_access(request, db, identity)
    snapshot = repository.get_snapshot(db, public_id=snapshot_id, workspace_id=workspace.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation job snapshot not found.")
    return _snapshot_view(repository.review_snapshot(
        db,
        snapshot=snapshot,
        reviewer_user_id=user.id,
        review_status=payload.review_status,
        review_notes=payload.review_notes,
    ))


@router.get("/admission-report", response_model=BenchmarkAdmissionReportView)
def get_benchmark_admission_report(
    request: Request,
    benchmark_release: str = "matching-benchmark-jobs.v1",
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> BenchmarkAdmissionReportView:
    _, workspace = _require_evaluation_access(request, db, identity)
    return BenchmarkAdmissionReportView.model_validate(build_admission_report(
        repository.list_snapshots(db, workspace_id=workspace.id),
        benchmark_release=benchmark_release,
    ))


@router.get("/fixture-catalog", response_model=EvaluationFixtureCatalogView)
def get_fixture_catalog(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationFixtureCatalogView:
    _, workspace = _require_evaluation_access(request, db, identity)
    catalog = build_fixture_catalog(
        profile_repository.list_resume_profiles(db, identity),
        repository.list_snapshots(db, workspace_id=workspace.id),
    )
    return EvaluationFixtureCatalogView.model_validate(catalog)


@router.get("/candidate-sources", response_model=EvaluationCandidateSourceListResponse)
def get_evaluation_candidate_sources(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationCandidateSourceListResponse:
    user, workspace = _require_evaluation_access(request, db, identity)
    candidates = []
    for resume in profile_repository.list_resume_profiles(db, identity):
        profile = db.scalar(
            select(CandidateProfileVersion)
            .join(CanonicalSource, CandidateProfileVersion.canonical_source_id == CanonicalSource.id)
            .where(
                CandidateProfileVersion.resume_profile_id == resume.id,
                CandidateProfileVersion.deleted_at.is_(None),
                CanonicalSource.workspace_id == workspace.id,
                CanonicalSource.user_id == user.id,
                CanonicalSource.deleted_at.is_(None),
            )
            .order_by(CandidateProfileVersion.created_at.desc(), CandidateProfileVersion.id.desc())
            .limit(1)
        )
        if resume.title.startswith("[EVAL internal"):
            fixture_group = "internal"
        elif resume.title.startswith("[EVAL synthetic"):
            fixture_group = "synthetic"
        else:
            fixture_group = "account"
        candidates.append({
            "resume_profile_id": resume.id,
            "label": resume.title,
            "fixture_group": fixture_group,
            "candidate_profile_id": profile.public_id if profile is not None else None,
            "profile_created_at": profile.created_at if profile is not None else None,
        })
    return EvaluationCandidateSourceListResponse.model_validate({"candidates": candidates})


@router.post(
    "/candidate-sources/{resume_profile_id}/profile",
    response_model=CandidateProfileEvaluationView,
)
def evaluate_candidate_profile(
    resume_profile_id: int,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    candidate_extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
) -> CandidateProfileEvaluationView:
    _, workspace = _require_evaluation_access(request, db, identity)
    resume = profile_repository.get_resume_profile_for_identity(db, identity, resume_profile_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume profile not found.")
    view = create_candidate_profile(
        resume_profile_id,
        request,
        Response(),
        BackgroundTasks(),
        db,
        identity,
        candidate_extractor,
    )
    if not isinstance(view, CandidateProfileView):
        raise HTTPException(status_code=409, detail="Candidate Profile extraction did not complete synchronously.")
    profile = db.scalar(select(CandidateProfileVersion).where(
        CandidateProfileVersion.public_id == view.candidate_profile_id
    ))
    if profile is None:
        raise HTTPException(status_code=409, detail="Candidate Profile was not persisted.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Candidate Profile source is unavailable.")
    return _candidate_evaluation_view(db, workspace.id, resume, profile, source)


@router.post(
    "/job-snapshots/{snapshot_id}/profile",
    response_model=JobProfileEvaluationView,
)
def evaluate_job_profile(
    snapshot_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    job_extractor: JobProfileExtractor = Depends(get_job_profile_extractor),
) -> JobProfileEvaluationView:
    _, workspace = _require_evaluation_access(request, db, identity)
    snapshot = repository.get_snapshot(db, public_id=snapshot_id, workspace_id=workspace.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation job snapshot not found.")
    if snapshot.review_status != "accepted":
        raise HTTPException(status_code=409, detail="The job snapshot must be accepted before profiling.")
    view = create_job_profile(
        snapshot.user_saved_job_id,
        request,
        Response(),
        BackgroundTasks(),
        db,
        identity,
        job_extractor,
    )
    if not isinstance(view, JobProfileView):
        raise HTTPException(status_code=409, detail="Job Profile extraction did not complete synchronously.")
    profile = db.scalar(select(JobProfileVersion).where(
        JobProfileVersion.public_id == view.job_profile_id
    ))
    if profile is None:
        raise HTTPException(status_code=409, detail="Job Profile was not persisted.")
    source = db.get(CanonicalSource, profile.canonical_source_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Job Profile source is unavailable.")
    return _job_evaluation_view(db, workspace.id, snapshot, profile, source)


@router.post(
    "/candidate-profiles/{candidate_profile_id}/reviews",
    response_model=EvaluationArtifactReviewView,
)
def add_candidate_profile_review(
    candidate_profile_id: str,
    payload: EvaluationArtifactReviewCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationArtifactReviewView:
    user, workspace = _require_evaluation_access(request, db, identity)
    profile = db.scalar(
        select(CandidateProfileVersion)
        .join(CanonicalSource, CandidateProfileVersion.canonical_source_id == CanonicalSource.id)
        .where(
            CandidateProfileVersion.public_id == candidate_profile_id,
            CandidateProfileVersion.deleted_at.is_(None),
            CanonicalSource.workspace_id == workspace.id,
            CanonicalSource.user_id == user.id,
            CanonicalSource.deleted_at.is_(None),
        )
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Candidate Profile not found.")
    review = repository.create_artifact_review(
        db,
        workspace_id=workspace.id,
        reviewer_user_id=user.id,
        stage="candidate_profile",
        candidate_profile_version_id=profile.id,
        job_profile_version_id=None,
        overall_score=payload.overall_score,
        confidence=payload.confidence,
        rationale=payload.rationale,
    )
    return _artifact_review_view(db, review, profile.public_id)


@router.post(
    "/job-profiles/{job_profile_id}/reviews",
    response_model=EvaluationArtifactReviewView,
)
def add_job_profile_review(
    job_profile_id: str,
    payload: EvaluationArtifactReviewCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationArtifactReviewView:
    user, workspace = _require_evaluation_access(request, db, identity)
    profile = db.scalar(
        select(JobProfileVersion)
        .join(
            EvaluationJobSnapshot,
            EvaluationJobSnapshot.jobs_cache_id == JobProfileVersion.jobs_cache_id,
        )
        .where(
            JobProfileVersion.public_id == job_profile_id,
            JobProfileVersion.deleted_at.is_(None),
            EvaluationJobSnapshot.workspace_id == workspace.id,
        )
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Job Profile not found.")
    review = repository.create_artifact_review(
        db,
        workspace_id=workspace.id,
        reviewer_user_id=user.id,
        stage="job_profile",
        candidate_profile_version_id=None,
        job_profile_version_id=profile.id,
        overall_score=payload.overall_score,
        confidence=payload.confidence,
        rationale=payload.rationale,
    )
    return _artifact_review_view(db, review, profile.public_id)


@router.post("/runs", response_model=EvaluationRunDetail)
def start_evaluation_run(
    payload: EvaluationRunCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    candidate_extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
    job_extractor: JobProfileExtractor = Depends(get_job_profile_extractor),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
) -> EvaluationRunDetail:
    started_at = datetime.now(timezone.utc)
    user, workspace = _require_evaluation_access(request, db, identity)
    snapshot = repository.get_snapshot(db, public_id=payload.job_snapshot_id, workspace_id=workspace.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation job snapshot not found.")
    if snapshot.review_status != "accepted":
        raise HTTPException(
            status_code=409,
            detail="The job snapshot must be accepted into the benchmark before it can be evaluated.",
        )
    if profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id) is None:
        raise HTTPException(status_code=404, detail="Resume profile not found.")

    trace_token = begin_matching_prompt_trace()
    try:
        stage_started = time.monotonic()
        candidate_view = create_candidate_profile(
            payload.resume_profile_id,
            request,
            Response(),
            BackgroundTasks(),
            db,
            identity,
            candidate_extractor,
        )
        candidate_latency_ms = round((time.monotonic() - stage_started) * 1000, 2)
        stage_started = time.monotonic()
        job_view = create_job_profile(
            snapshot.user_saved_job_id,
            request,
            Response(),
            BackgroundTasks(),
            db,
            identity,
            job_extractor,
        )
        job_latency_ms = round((time.monotonic() - stage_started) * 1000, 2)
        stage_started = time.monotonic()
        qualification_view = create_qualification_assessment(
            QualificationAssessmentCreateRequest(
                candidate_profile_id=candidate_view.candidate_profile_id,
                candidate_career_selection_revision=candidate_view.selection.revision,
                job_profile_id=job_view.job_profile_id,
            ),
            request,
            db,
            identity,
            matcher,
        )
        qualification_latency_ms = round((time.monotonic() - stage_started) * 1000, 2)
    finally:
        end_matching_prompt_trace(trace_token)
    candidate = db.scalar(select(CandidateProfileVersion).where(
        CandidateProfileVersion.public_id == candidate_view.candidate_profile_id
    ))
    job_profile = db.scalar(select(JobProfileVersion).where(
        JobProfileVersion.public_id == job_view.job_profile_id
    ))
    qualification = db.scalar(select(QualificationAssessment).where(
        QualificationAssessment.public_id == qualification_view.qualification_assessment_id
    ))
    if candidate is None or job_profile is None or qualification is None:
        raise HTTPException(status_code=409, detail="Evaluation artifacts were not persisted.")
    run = repository.create_run(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        snapshot=snapshot,
        resume_profile_id=payload.resume_profile_id,
        candidate_profile_version_id=candidate.id,
        job_profile_version_id=job_profile.id,
        qualification_assessment_id=qualification.id,
        run_metadata={
            "pipeline": "matching-v2-three-stage",
            "score_generated": False,
            "stage_execution": {
                "candidate_profile": {
                    "latency_ms": candidate_latency_ms,
                    "cache_status": _cache_status(candidate.created_at, started_at),
                },
                "job_profile": {
                    "latency_ms": job_latency_ms,
                    "cache_status": _cache_status(job_profile.created_at, started_at),
                },
                "qualification": {
                    "latency_ms": qualification_latency_ms,
                    "cache_status": _cache_status(qualification.created_at, started_at),
                },
            },
            "provider_usage": {
                "input_tokens": None,
                "output_tokens": None,
                "cost_usd": None,
                "availability": "provider_does_not_expose_usage_to_current_adapter",
            },
            "validation": {
                "strict_schema_success": True,
                "retry_count": int(qualification.input_quality.get("validation_retry_count", 0)),
            },
        },
        manifest=_build_manifest(
            snapshot=snapshot,
            candidate=candidate,
            job_profile=job_profile,
            qualification=qualification,
            candidate_fixture_release=payload.candidate_fixture_release,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        ),
    )
    return _run_detail(db, run)


@router.get("/runs", response_model=EvaluationRunListResponse)
def get_evaluation_runs(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationRunListResponse:
    _, workspace = _require_evaluation_access(request, db, identity)
    return EvaluationRunListResponse(
        runs=[_run_summary(db, item) for item in repository.list_runs(db, workspace_id=workspace.id)]
    )


@router.get("/runs/{run_id}", response_model=EvaluationRunDetail)
def get_evaluation_run(
    run_id: str,
    request: Request,
    blind: bool = False,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationRunDetail:
    user, workspace = _require_evaluation_access(request, db, identity)
    run = repository.get_run(db, public_id=run_id, workspace_id=workspace.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return _run_detail(db, run, blind_reviewer_user_id=user.id if blind else None)


@router.post("/runs/{run_id}/annotations", response_model=EvaluationAnnotationView)
def add_evaluation_annotation(
    run_id: str,
    payload: EvaluationAnnotationCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationAnnotationView:
    user, workspace = _require_evaluation_access(request, db, identity)
    run = repository.get_run(db, public_id=run_id, workspace_id=workspace.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    valid_targets = _annotation_targets(db, run, payload.stage)
    if payload.target_ref not in valid_targets:
        raise HTTPException(
            status_code=422,
            detail={"code": "UNKNOWN_EVALUATION_TARGET", "valid_targets": sorted(valid_targets)},
        )
    if payload.review_kind == "adjudication" and not payload.expected_value:
        raise HTTPException(status_code=422, detail="Adjudication requires an expected value.")
    annotation = repository.create_annotation(
        db,
        run=run,
        reviewer_user_id=user.id,
        stage=payload.stage,
        target_ref=payload.target_ref,
        review_kind=payload.review_kind,
        verdict=payload.verdict,
        evidence_support=payload.evidence_support,
        expected_value=payload.expected_value,
        confidence=payload.confidence,
        severity=payload.severity,
        error_taxonomy_code=payload.error_taxonomy_code,
        comment=payload.comment,
    )
    return _annotation_view(db, annotation)


@router.post("/runs/{run_id}/match-reviews", response_model=EvaluationMatchReviewView)
def add_evaluation_match_review(
    run_id: str,
    payload: EvaluationMatchReviewCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationMatchReviewView:
    user, workspace = _require_evaluation_access(request, db, identity)
    run = repository.get_run(db, public_id=run_id, workspace_id=workspace.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    if payload.review_kind == "adjudication":
        independent = _latest_independent_match_reviews(
            repository.list_match_reviews(db, run_id=run.id)
        )
        if len(independent) < 2:
            raise HTTPException(
                status_code=409,
                detail="Two independent match reviews are required before adjudication.",
            )
        if user.id in independent:
            raise HTTPException(
                status_code=409,
                detail="The adjudicator must be independent from both match reviewers.",
            )
    review = repository.create_match_review(
        db,
        run=run,
        reviewer_user_id=user.id,
        review_kind=payload.review_kind,
        overall_score=payload.overall_score,
        confidence=payload.confidence,
        rationale=payload.rationale,
    )
    return _match_review_view(db, review)


@router.get("/runs/{run_id}/metrics", response_model=EvaluationMetricsView)
def get_evaluation_metrics(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationMetricsView:
    _, workspace = _require_evaluation_access(request, db, identity)
    run = repository.get_run(db, public_id=run_id, workspace_id=workspace.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return calculate_run_metrics(db, run)


@router.get("/comparisons", response_model=EvaluationComparisonView)
def get_evaluation_comparison(
    baseline_run_id: str,
    candidate_run_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationComparisonView:
    _, workspace = _require_evaluation_access(request, db, identity)
    baseline = repository.get_run(db, public_id=baseline_run_id, workspace_id=workspace.id)
    candidate = repository.get_run(db, public_id=candidate_run_id, workspace_id=workspace.id)
    if baseline is None or candidate is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return compare_runs(db, baseline, candidate)


@router.get("/metrics", response_model=EvaluationAggregateMetricsView)
def get_aggregate_evaluation_metrics(
    request: Request,
    benchmark_release: str | None = None,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationAggregateMetricsView:
    _, workspace = _require_evaluation_access(request, db, identity)
    runs = repository.list_runs(db, workspace_id=workspace.id)
    if benchmark_release is not None:
        runs = [run for run in runs if run.benchmark_release == benchmark_release]
    return calculate_aggregate_metrics(db, runs, benchmark_release=benchmark_release)


@router.get("/adjudication-queue", response_model=DisagreementQueueView)
def get_adjudication_queue(
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> DisagreementQueueView:
    _, workspace = _require_evaluation_access(request, db, identity)
    return DisagreementQueueView(items=build_disagreement_queue(db, workspace_id=workspace.id))


@router.get("/exports/corpus", response_model=None)
def export_evaluation_corpus(
    request: Request,
    export_format: str = Query(default="json", alias="format", pattern="^(json|markdown)$"),
    benchmark_release: str | None = None,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> Response:
    _, workspace = _require_evaluation_access(request, db, identity)
    runs = repository.list_runs(db, workspace_id=workspace.id)
    if benchmark_release is not None:
        runs = [run for run in runs if run.benchmark_release == benchmark_release]
    payload = build_corpus_export(db, runs, benchmark_release=benchmark_release)
    suffix = benchmark_release or "all"
    if export_format == "markdown":
        return Response(
            content=corpus_markdown(payload),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="matching-evaluation-{suffix}.md"'},
        )
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="matching-evaluation-{suffix}.json"'},
    )


def _run_artifacts(db: Session, run: EvaluationRun):
    snapshot = db.get(EvaluationJobSnapshot, run.job_snapshot_id)
    resume = db.get(ResumeProfile, run.resume_profile_id) if run.resume_profile_id is not None else None
    candidate = db.get(CandidateProfileVersion, run.candidate_profile_version_id)
    job_profile = db.get(JobProfileVersion, run.job_profile_version_id)
    qualification = db.get(QualificationAssessment, run.qualification_assessment_id)
    if snapshot is None or candidate is None or job_profile is None or qualification is None:
        raise HTTPException(status_code=409, detail="Evaluation run artifacts are unavailable.")
    candidate_source = db.get(CanonicalSource, candidate.canonical_source_id)
    job_source = db.get(CanonicalSource, job_profile.canonical_source_id)
    if candidate_source is None or job_source is None:
        raise HTTPException(status_code=409, detail="Evaluation source text is unavailable.")
    return snapshot, resume, candidate, job_profile, qualification, candidate_source, job_source


def _run_summary(db: Session, run: EvaluationRun) -> EvaluationRunSummary:
    snapshot, _, candidate, job_profile, qualification, _, _ = _run_artifacts(db, run)
    return EvaluationRunSummary(
        public_id=run.public_id,
        benchmark_release=run.benchmark_release,
        job_snapshot_id=snapshot.public_id,
        resume_profile_id=run.resume_profile_id,
        candidate_profile_id=candidate.public_id,
        job_profile_id=job_profile.public_id,
        qualification_assessment_id=qualification.public_id,
        created_at=run.created_at,
    )


def _source_view(db: Session, source: CanonicalSource) -> EvaluationSourceView:
    spans = db.scalars(select(SourceSpan).where(
        SourceSpan.canonical_source_id == source.id
    ).order_by(SourceSpan.id)).all()
    return EvaluationSourceView(
        text=source.canonical_text,
        spans=[EvidenceSpanView(
            span_id=item.span_id,
            section=item.section,
            start_utf8_byte=item.start_utf8_byte,
            end_utf8_byte=item.end_utf8_byte,
            excerpt=item.excerpt,
        ) for item in spans],
    )


def _artifact_review_view(
    db: Session,
    review: EvaluationArtifactReview,
    artifact_id: str,
) -> EvaluationArtifactReviewView:
    reviewer = db.get(User, review.reviewer_user_id)
    return EvaluationArtifactReviewView(
        public_id=review.public_id,
        stage=cast(str, review.stage),
        artifact_id=artifact_id,
        reviewer_user_id=review.reviewer_user_id,
        reviewer_label=reviewer.email if reviewer is not None else f"user:{review.reviewer_user_id}",
        overall_score=review.overall_score,
        confidence=review.confidence,
        rationale=review.rationale,
        created_at=review.created_at,
    )


def _candidate_evaluation_view(
    db: Session,
    workspace_id: int,
    resume: ResumeProfile,
    profile: CandidateProfileVersion,
    source: CanonicalSource,
) -> CandidateProfileEvaluationView:
    return CandidateProfileEvaluationView(
        resume_profile_id=resume.id,
        resume_title=resume.title,
        resume_source=_source_view(db, source),
        candidate_profile=_candidate_profile_view(db, profile, source),
        annotation_targets=artifact_annotation_targets(db, candidate=profile),
        reviews=[
            _artifact_review_view(db, item, profile.public_id)
            for item in repository.list_artifact_reviews(
                db,
                workspace_id=workspace_id,
                stage="candidate_profile",
                candidate_profile_version_id=profile.id,
            )
        ],
    )


def _job_evaluation_view(
    db: Session,
    workspace_id: int,
    snapshot: EvaluationJobSnapshot,
    profile: JobProfileVersion,
    source: CanonicalSource,
) -> JobProfileEvaluationView:
    return JobProfileEvaluationView(
        job_snapshot_id=snapshot.public_id,
        job_title=snapshot.title,
        job_company=snapshot.company,
        job_source=_source_view(db, source),
        job_profile=_job_profile_view(db, profile, source),
        annotation_targets=artifact_annotation_targets(db, job_profile=profile),
        reviews=[
            _artifact_review_view(db, item, profile.public_id)
            for item in repository.list_artifact_reviews(
                db,
                workspace_id=workspace_id,
                stage="job_profile",
                job_profile_version_id=profile.id,
            )
        ],
    )


def _build_manifest(
    *,
    snapshot: EvaluationJobSnapshot,
    candidate: CandidateProfileVersion,
    job_profile: JobProfileVersion,
    qualification: QualificationAssessment,
    candidate_fixture_release: str,
    started_at: datetime,
    completed_at: datetime,
) -> dict:
    provider_configuration = {
        "candidate_model": candidate.model_id,
        "job_model": job_profile.model_id,
        "qualification_model": qualification.model_id,
    }
    provider_hash = "sha256:" + hashlib.sha256(
        json.dumps(provider_configuration, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "benchmark_release": snapshot.benchmark_release,
        "candidate_fixture_release": candidate_fixture_release,
        "job_fixture_release": snapshot.benchmark_release,
        "candidate_prompt_version": candidate.prompt_version,
        "job_prompt_version": job_profile.prompt_version,
        "qualification_prompt_version": qualification.prompt_version,
        "schema_versions": {
            "candidate": candidate.schema_version,
            "job": job_profile.schema_version,
            "qualification": qualification.schema_version,
        },
        "taxonomy_version": candidate.taxonomy_version,
        "selection_policy_version": qualification.selection_policy_version,
        "qualification_policy_version": qualification.matching_policy_version,
        "model_ids": provider_configuration,
        "provider_configuration_hash": provider_hash,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
    }


def _cache_status(created_at: datetime, started_at: datetime) -> str:
    normalized = created_at if created_at.tzinfo is not None else created_at.replace(tzinfo=timezone.utc)
    return "created" if normalized >= started_at else "reused"


def _annotation_view(db: Session, annotation: EvaluationAnnotation) -> EvaluationAnnotationView:
    reviewer = db.get(User, annotation.reviewer_user_id)
    return EvaluationAnnotationView(
        public_id=annotation.public_id,
        reviewer_user_id=annotation.reviewer_user_id,
        reviewer_label=(reviewer.email if reviewer is not None else f"user:{annotation.reviewer_user_id}"),
        stage=annotation.stage,
        target_ref=annotation.target_ref,
        review_kind=annotation.review_kind,
        verdict=annotation.verdict,
        evidence_support=annotation.evidence_support,
        expected_value=annotation.expected_value,
        confidence=annotation.confidence,
        severity=annotation.severity,
        error_taxonomy_code=annotation.error_taxonomy_code,
        comment=annotation.comment,
        created_at=annotation.created_at,
    )


def _annotation_targets(db: Session, run: EvaluationRun, stage: str) -> set[str]:
    _, _, candidate, job_profile, qualification, candidate_source, job_source = _run_artifacts(db, run)
    if stage == "qualification":
        return set(db.scalars(select(RequirementAssessment.requirement_id).where(
            RequirementAssessment.qualification_assessment_id == qualification.id
        )).all())
    source = candidate_source if stage == "candidate_profile" else job_source
    targets = set(db.scalars(select(SourceSpan.span_id).where(
        SourceSpan.canonical_source_id == source.id
    )).all())
    targets.add(candidate.public_id if stage == "candidate_profile" else job_profile.public_id)
    targets.update(
        item["target_ref"] for item in artifact_annotation_targets(
            db, candidate=candidate, job_profile=job_profile
        ) if item["stage"] == stage
    )
    return targets


def _run_detail(
    db: Session,
    run: EvaluationRun,
    *,
    blind_reviewer_user_id: int | None = None,
) -> EvaluationRunDetail:
    snapshot, resume, candidate, job_profile, qualification, candidate_source, job_source = _run_artifacts(db, run)
    summary = _run_summary(db, run)
    return EvaluationRunDetail(
        **summary.model_dump(),
        resume_title=resume.title if resume is not None else "Deleted resume fixture",
        job_title=snapshot.title,
        job_company=snapshot.company,
        source_url=snapshot.source_url,
        resume_source=_source_view(db, candidate_source),
        candidate_profile=_candidate_profile_view(db, candidate, candidate_source),
        job_source=_source_view(db, job_source),
        job_profile=_job_profile_view(db, job_profile, job_source),
        qualification=_qualification_assessment_view(db, qualification),
        manifest=cast(dict, run.manifest),
        annotations=[
            _annotation_view(db, item)
            for item in repository.list_annotations(db, run_id=run.id)
            if blind_reviewer_user_id is None or item.reviewer_user_id == blind_reviewer_user_id
        ],
        match_review=_match_review_summary(
            db,
            repository.list_match_reviews(
                db,
                run_id=run.id,
                reviewer_user_id=blind_reviewer_user_id,
            ),
        ),
        annotation_targets=artifact_annotation_targets(
            db, candidate=candidate, job_profile=job_profile
        ),
        metrics=calculate_run_metrics(db, run),
        run_metadata=cast(dict, run.run_metadata),
    )


def _latest_independent_match_reviews(
    reviews: list[EvaluationMatchReview],
) -> dict[int, EvaluationMatchReview]:
    latest: dict[int, EvaluationMatchReview] = {}
    for review in reviews:
        if review.review_kind == "independent":
            latest[review.reviewer_user_id] = review
    return latest


def _match_review_view(db: Session, review: EvaluationMatchReview) -> EvaluationMatchReviewView:
    reviewer = db.get(User, review.reviewer_user_id)
    return EvaluationMatchReviewView(
        public_id=review.public_id,
        reviewer_user_id=review.reviewer_user_id,
        reviewer_label=reviewer.email if reviewer is not None else f"user:{review.reviewer_user_id}",
        review_kind=review.review_kind,
        overall_score=review.overall_score,
        recommendation=recommendation_for_score(review.overall_score),
        confidence=review.confidence,
        rationale=review.rationale,
        created_at=review.created_at,
    )


def _match_review_summary(
    db: Session,
    reviews: list[EvaluationMatchReview],
) -> EvaluationMatchReviewSummaryView:
    independent = _latest_independent_match_reviews(reviews)
    adjudications = [review for review in reviews if review.review_kind == "adjudication"]
    adjudication = adjudications[-1] if adjudications else None
    if adjudication is not None:
        state = "adjudicated"
    elif len(independent) >= 2:
        state = "adjudication_ready"
    else:
        state = "review_pending"
    displayed = [*independent.values(), *([adjudication] if adjudication is not None else [])]
    return EvaluationMatchReviewSummaryView(
        state=state,
        independent_reviewer_count=len(independent),
        reviews=[_match_review_view(db, item) for item in displayed],
        adjudicated_review=_match_review_view(db, adjudication) if adjudication is not None else None,
    )

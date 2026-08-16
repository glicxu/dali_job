from __future__ import annotations

from collections.abc import Callable
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.provider_ops import run_provider_call
from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.evaluation import repository
from app.modules.evaluation.models import EvaluationJobSnapshot, EvaluationRun
from app.modules.evaluation.schemas import (
    EvaluationRunCreateRequest,
    EvaluationRunDetail,
    EvaluationRunListResponse,
    EvaluationRunSummary,
    EvaluationSourceView,
    EvidenceSpanView,
    JobSnapshotImportRequest,
    JobSnapshotListResponse,
    JobSnapshotView,
)
from app.modules.matching_v2.api_schemas import QualificationAssessmentCreateRequest
from app.modules.matching_v2.extraction import CandidateProfileExtractor, JobProfileExtractor
from app.modules.matching_v2.models import (
    CandidateProfileVersion,
    CanonicalSource,
    JobProfileVersion,
    QualificationAssessment,
    SourceSpan,
)
from app.modules.matching_v2.qualification import QualificationMatcher
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
        company=(result.company or "").strip(),
        capture_metadata={
            "canonical_url": result.canonical_url,
            "location": result.location,
            "extraction_method": result.extraction_method,
            "extractor_version": result.extractor_version,
            "confidence": result.confidence,
            "warnings": result.warnings,
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
    user, workspace = _require_evaluation_access(request, db, identity)
    snapshot = repository.get_snapshot(db, public_id=payload.job_snapshot_id, workspace_id=workspace.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evaluation job snapshot not found.")
    if profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id) is None:
        raise HTTPException(status_code=404, detail="Resume profile not found.")

    candidate_view = create_candidate_profile(
        payload.resume_profile_id, request, db, identity, candidate_extractor
    )
    job_view = create_job_profile(snapshot.user_saved_job_id, request, db, identity, job_extractor)
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
        run_metadata={"pipeline": "matching-v2-three-stage", "score_generated": False},
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
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> EvaluationRunDetail:
    _, workspace = _require_evaluation_access(request, db, identity)
    run = repository.get_run(db, public_id=run_id, workspace_id=workspace.id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found.")
    return _run_detail(db, run)


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


def _run_detail(db: Session, run: EvaluationRun) -> EvaluationRunDetail:
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
        run_metadata=cast(dict, run.run_metadata),
    )

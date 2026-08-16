from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.evaluation.models import (
    EvaluationAnnotation,
    EvaluationArtifactReview,
    EvaluationJobSnapshot,
    EvaluationMatchReview,
    EvaluationRun,
)
from app.modules.evaluation.schemas import EvaluationRunManifestView
from app.modules.jobs.models import JobCache
from app.modules.jobs.repository import create_user_job
from app.modules.profiles import repository as profile_repository


def create_or_get_snapshot(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    benchmark_release: str,
    coverage_slot: str,
    source_url: str,
    raw_description_text: str,
    title: str,
    company: str,
    capture_metadata: dict,
) -> EvaluationJobSnapshot:
    user, workspace = profile_repository.ensure_account_for_identity(db, identity)
    source_hash = "sha256:" + hashlib.sha256(raw_description_text.encode("utf-8")).hexdigest()
    existing = db.scalar(select(EvaluationJobSnapshot).where(
        EvaluationJobSnapshot.workspace_id == workspace.id,
        EvaluationJobSnapshot.benchmark_release == benchmark_release,
        EvaluationJobSnapshot.source_hash == source_hash,
    ))
    if existing is not None:
        return existing
    cache_job = JobCache(
        title=title,
        company=company,
        source_url=None,
        source_url_hash=None,
        raw_description_text=raw_description_text,
        job_data=None,
    )
    db.add(cache_job)
    db.flush()
    saved_job = create_user_job(db, identity, jobs_cache_id=cache_job.id, notes="Evaluation snapshot")
    snapshot = EvaluationJobSnapshot(
        public_id=f"ejs_{uuid.uuid4().hex}",
        workspace_id=workspace.id,
        user_id=user.id,
        benchmark_release=benchmark_release,
        coverage_slot=coverage_slot,
        source_url=source_url,
        source_hash=source_hash,
        jobs_cache_id=cache_job.id,
        user_saved_job_id=saved_job.id,
        title=title,
        company=company,
        raw_description_text=raw_description_text,
        capture_metadata=capture_metadata,
    )
    db.add(snapshot)
    db.flush()
    db.refresh(snapshot)
    return snapshot


def list_snapshots(db: Session, *, workspace_id: int) -> list[EvaluationJobSnapshot]:
    return list(db.scalars(select(EvaluationJobSnapshot).where(
        EvaluationJobSnapshot.workspace_id == workspace_id,
    ).order_by(desc(EvaluationJobSnapshot.created_at), desc(EvaluationJobSnapshot.id))).all())


def get_snapshot(db: Session, *, public_id: str, workspace_id: int) -> EvaluationJobSnapshot | None:
    return db.scalar(select(EvaluationJobSnapshot).where(
        EvaluationJobSnapshot.public_id == public_id,
        EvaluationJobSnapshot.workspace_id == workspace_id,
    ))


def review_snapshot(
    db: Session,
    *,
    snapshot: EvaluationJobSnapshot,
    reviewer_user_id: int,
    review_status: str,
    review_notes: str,
) -> EvaluationJobSnapshot:
    snapshot.review_status = review_status
    snapshot.review_notes = review_notes
    snapshot.reviewed_by_user_id = reviewer_user_id
    snapshot.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(snapshot)
    return snapshot


def create_run(
    db: Session,
    *,
    workspace_id: int,
    user_id: int,
    snapshot: EvaluationJobSnapshot,
    resume_profile_id: int,
    candidate_profile_version_id: int,
    job_profile_version_id: int,
    qualification_assessment_id: int,
    run_metadata: dict,
    manifest: dict,
) -> EvaluationRun:
    public_id = f"evr_{uuid.uuid4().hex}"
    run = EvaluationRun(
        public_id=public_id,
        workspace_id=workspace_id,
        user_id=user_id,
        benchmark_release=snapshot.benchmark_release,
        job_snapshot_id=snapshot.id,
        resume_profile_id=resume_profile_id,
        candidate_profile_version_id=candidate_profile_version_id,
        job_profile_version_id=job_profile_version_id,
        qualification_assessment_id=qualification_assessment_id,
        run_metadata=run_metadata,
        manifest=EvaluationRunManifestView.model_validate({
            **manifest, "evaluation_run_id": public_id
        }).model_dump(mode="json"),
    )
    db.add(run)
    db.flush()
    db.refresh(run)
    return run


def list_runs(db: Session, *, workspace_id: int) -> list[EvaluationRun]:
    return list(db.scalars(select(EvaluationRun).where(
        EvaluationRun.workspace_id == workspace_id,
    ).order_by(desc(EvaluationRun.created_at), desc(EvaluationRun.id))).all())


def get_run(db: Session, *, public_id: str, workspace_id: int) -> EvaluationRun | None:
    return db.scalar(select(EvaluationRun).where(
        EvaluationRun.public_id == public_id,
        EvaluationRun.workspace_id == workspace_id,
    ))


def create_annotation(
    db: Session,
    *,
    run: EvaluationRun,
    reviewer_user_id: int,
    stage: str,
    target_ref: str,
    review_kind: str,
    verdict: str,
    evidence_support: str,
    expected_value: dict | None,
    confidence: float,
    severity: str,
    error_taxonomy_code: str | None,
    comment: str,
) -> EvaluationAnnotation:
    annotation = EvaluationAnnotation(
        public_id=f"eva_{uuid.uuid4().hex}",
        evaluation_run_id=run.id,
        reviewer_user_id=reviewer_user_id,
        stage=stage,
        target_ref=target_ref,
        review_kind=review_kind,
        verdict=verdict,
        evidence_support=evidence_support,
        expected_value=expected_value,
        confidence=confidence,
        severity=severity,
        error_taxonomy_code=error_taxonomy_code,
        comment=comment,
    )
    db.add(annotation)
    db.flush()
    db.refresh(annotation)
    return annotation


def list_annotations(db: Session, *, run_id: int) -> list[EvaluationAnnotation]:
    return list(db.scalars(select(EvaluationAnnotation).where(
        EvaluationAnnotation.evaluation_run_id == run_id,
    ).order_by(EvaluationAnnotation.created_at, EvaluationAnnotation.id)).all())


def create_match_review(
    db: Session,
    *,
    run: EvaluationRun,
    reviewer_user_id: int,
    review_kind: str,
    overall_score: int,
    confidence: float,
    rationale: str,
) -> EvaluationMatchReview:
    review = EvaluationMatchReview(
        public_id=f"evm_{uuid.uuid4().hex}",
        evaluation_run_id=run.id,
        reviewer_user_id=reviewer_user_id,
        review_kind=review_kind,
        overall_score=overall_score,
        confidence=confidence,
        rationale=rationale,
    )
    db.add(review)
    db.flush()
    db.refresh(review)
    return review


def list_match_reviews(
    db: Session,
    *,
    run_id: int,
    reviewer_user_id: int | None = None,
) -> list[EvaluationMatchReview]:
    statement = select(EvaluationMatchReview).where(
        EvaluationMatchReview.evaluation_run_id == run_id
    )
    if reviewer_user_id is not None:
        statement = statement.where(EvaluationMatchReview.reviewer_user_id == reviewer_user_id)
    return list(db.scalars(statement.order_by(
        EvaluationMatchReview.created_at, EvaluationMatchReview.id
    )).all())


def create_artifact_review(
    db: Session,
    *,
    workspace_id: int,
    reviewer_user_id: int,
    stage: str,
    candidate_profile_version_id: int | None,
    job_profile_version_id: int | None,
    overall_score: int,
    confidence: float,
    rationale: str,
) -> EvaluationArtifactReview:
    review = EvaluationArtifactReview(
        public_id=f"evp_{uuid.uuid4().hex}",
        workspace_id=workspace_id,
        reviewer_user_id=reviewer_user_id,
        stage=stage,
        candidate_profile_version_id=candidate_profile_version_id,
        job_profile_version_id=job_profile_version_id,
        overall_score=overall_score,
        confidence=confidence,
        rationale=rationale,
    )
    db.add(review)
    db.flush()
    db.refresh(review)
    return review


def list_artifact_reviews(
    db: Session,
    *,
    workspace_id: int,
    stage: str,
    candidate_profile_version_id: int | None = None,
    job_profile_version_id: int | None = None,
) -> list[EvaluationArtifactReview]:
    statement = select(EvaluationArtifactReview).where(
        EvaluationArtifactReview.workspace_id == workspace_id,
        EvaluationArtifactReview.stage == stage,
    )
    if stage == "candidate_profile":
        statement = statement.where(
            EvaluationArtifactReview.candidate_profile_version_id == candidate_profile_version_id
        )
    else:
        statement = statement.where(
            EvaluationArtifactReview.job_profile_version_id == job_profile_version_id
        )
    return list(db.scalars(statement.order_by(
        EvaluationArtifactReview.created_at, EvaluationArtifactReview.id
    )).all())

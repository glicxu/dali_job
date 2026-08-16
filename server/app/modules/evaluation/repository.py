from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.evaluation.models import EvaluationJobSnapshot, EvaluationRun
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
) -> EvaluationRun:
    run = EvaluationRun(
        public_id=f"evr_{uuid.uuid4().hex}",
        workspace_id=workspace_id,
        user_id=user_id,
        benchmark_release=snapshot.benchmark_release,
        job_snapshot_id=snapshot.id,
        resume_profile_id=resume_profile_id,
        candidate_profile_version_id=candidate_profile_version_id,
        job_profile_version_id=job_profile_version_id,
        qualification_assessment_id=qualification_assessment_id,
        run_metadata=run_metadata,
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

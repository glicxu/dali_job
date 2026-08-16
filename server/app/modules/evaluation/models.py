from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationJobSnapshot(Base):
    __tablename__ = "matching_evaluation_job_snapshots"
    __table_args__ = (
        CheckConstraint(
            "review_status IN ('draft', 'accepted', 'rejected')",
            name="ck_matching_eval_snapshot_review_status",
        ),
        UniqueConstraint(
            "workspace_id",
            "benchmark_release",
            "source_hash",
            name="uq_matching_eval_snapshot_workspace_release_hash",
        ),
        Index("ix_matching_eval_snapshots_public", "public_id", unique=True),
        Index("ix_matching_eval_snapshots_workspace", "workspace_id"),
        Index("ix_matching_eval_snapshots_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    benchmark_release: Mapped[str] = mapped_column(String(100), nullable=False)
    coverage_slot: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    jobs_cache_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs_cache.id", ondelete="RESTRICT"), nullable=False
    )
    user_saved_job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_saved_jobs.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    raw_description_text: Mapped[str] = mapped_column(Text, nullable=False)
    capture_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvaluationRun(Base):
    __tablename__ = "matching_evaluation_runs"
    __table_args__ = (
        Index("ix_matching_eval_runs_public", "public_id", unique=True),
        Index("ix_matching_eval_runs_workspace", "workspace_id"),
        Index("ix_matching_eval_runs_user", "user_id"),
        Index("ix_matching_eval_runs_snapshot", "job_snapshot_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    benchmark_release: Mapped[str] = mapped_column(String(100), nullable=False)
    job_snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_evaluation_job_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    resume_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("resume_profiles.id", ondelete="SET NULL"), nullable=True
    )
    candidate_profile_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_candidate_profile_versions.id", ondelete="RESTRICT"), nullable=False
    )
    job_profile_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_job_profile_versions.id", ondelete="RESTRICT"), nullable=False
    )
    qualification_assessment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_qualification_assessments.id", ondelete="RESTRICT"), nullable=False
    )
    run_metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvaluationAnnotation(Base):
    __tablename__ = "matching_evaluation_annotations"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('candidate_profile', 'job_profile', 'qualification')",
            name="ck_matching_eval_annotations_stage",
        ),
        CheckConstraint(
            "review_kind IN ('independent', 'adjudication')",
            name="ck_matching_eval_annotations_review_kind",
        ),
        CheckConstraint(
            "verdict IN ('correct', 'partially_correct', 'incorrect', 'missing', 'ambiguous')",
            name="ck_matching_eval_annotations_verdict",
        ),
        CheckConstraint(
            "evidence_support IN ('supported', 'partially_supported', 'unsupported', 'ambiguous', 'not_reviewed')",
            name="ck_matching_eval_annotations_evidence",
        ),
        CheckConstraint(
            "severity IN ('none', 'minor', 'major', 'severe')",
            name="ck_matching_eval_annotations_severity",
        ),
        Index("ix_matching_eval_annotations_public", "public_id", unique=True),
        Index("ix_matching_eval_annotations_run", "evaluation_run_id"),
        Index("ix_matching_eval_annotations_reviewer", "reviewer_user_id"),
        Index("ix_matching_eval_annotations_target", "stage", "target_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    review_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_support: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    error_taxonomy_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvaluationMatchReview(Base):
    __tablename__ = "matching_evaluation_match_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_kind IN ('independent', 'adjudication')",
            name="ck_matching_eval_match_reviews_kind",
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_matching_eval_match_reviews_score",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_matching_eval_match_reviews_confidence",
        ),
        Index("ix_matching_eval_match_reviews_public", "public_id", unique=True),
        Index("ix_matching_eval_match_reviews_run", "evaluation_run_id"),
        Index("ix_matching_eval_match_reviews_reviewer", "reviewer_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    review_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class EvaluationArtifactReview(Base):
    __tablename__ = "matching_evaluation_artifact_reviews"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('candidate_profile', 'job_profile')",
            name="ck_matching_eval_artifact_reviews_stage",
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_matching_eval_artifact_reviews_score",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_matching_eval_artifact_reviews_confidence",
        ),
        CheckConstraint(
            "(stage = 'candidate_profile' AND candidate_profile_version_id IS NOT NULL "
            "AND job_profile_version_id IS NULL) OR "
            "(stage = 'job_profile' AND job_profile_version_id IS NOT NULL "
            "AND candidate_profile_version_id IS NULL)",
            name="ck_matching_eval_artifact_reviews_target",
        ),
        Index("ix_matching_eval_artifact_reviews_public", "public_id", unique=True),
        Index("ix_matching_eval_artifact_reviews_workspace", "workspace_id"),
        Index("ix_matching_eval_artifact_reviews_reviewer", "reviewer_user_id"),
        Index("ix_matching_eval_artifact_reviews_candidate", "candidate_profile_version_id"),
        Index("ix_matching_eval_artifact_reviews_job", "job_profile_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    candidate_profile_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("matching_candidate_profile_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    job_profile_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("matching_job_profile_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

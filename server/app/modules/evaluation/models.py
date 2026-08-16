from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationJobSnapshot(Base):
    __tablename__ = "matching_evaluation_job_snapshots"
    __table_args__ = (
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

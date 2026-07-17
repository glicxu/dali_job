from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = (
        CheckConstraint(
            "interview_type IN ('recruiter_screen', 'phone', 'technical', 'behavioral', 'hiring_manager', 'panel', 'final', 'other')",
            name="ck_interviews_type",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'completed', 'cancelled')",
            name="ck_interviews_status",
        ),
        CheckConstraint(
            "stage IN ('recruiter_contact', 'assessment', 'phone_screen', 'technical_interview', 'final_interview', 'other')",
            name="ck_interviews_stage",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('advanced', 'rejected', 'offer', 'withdrawn', 'no_decision')",
            name="ck_interviews_outcome",
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes >= 15 AND duration_minutes <= 480)",
            name="ck_interviews_duration",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interview_type: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled", index=True)
    stage: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="America/New_York")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location_or_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    private_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class InterviewNote(Base):
    __tablename__ = "interview_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interview_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class InterviewPrepGuide(Base):
    __tablename__ = "interview_prep_guides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interview_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("interviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("managed_operations.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    resume_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_data_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    job_data_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    company_notes_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    output_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="openai")
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="interview-prep-v1")
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False, default="interview-prep-v1")
    provider_execution_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

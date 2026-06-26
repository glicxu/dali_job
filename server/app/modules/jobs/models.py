from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_job_data() -> dict:
    return {
        "title": "",
        "company": "",
        "summary": "",
        "responsibilities": [],
        "required_skills": [],
        "preferred_skills": [],
        "required_experience": [],
        "preferred_experience": [],
        "education": [],
        "certifications": [],
        "tools_and_technologies": [],
        "keywords": [],
        "seniority_level": "",
        "employment_type": "",
        "security_clearance": "",
        "work_location": "",
        "salary_range": "",
        "application_deadline": "",
    }


class JobCache(Base):
    __tablename__ = "jobs_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_description_text: Mapped[str] = mapped_column(Text, nullable=False)
    job_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=default_job_data)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSavedJob(Base):
    __tablename__ = "user_saved_jobs"

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
    jobs_cache_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("jobs_cache.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobResumeMatch(Base):
    __tablename__ = "job_resume_matches"

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
    user_job_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user_saved_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    jobs_cache_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("jobs_cache.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_source: Mapped[str] = mapped_column(String(64), nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    match_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

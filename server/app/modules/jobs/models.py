from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid4())


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


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    raw_description_text: Mapped[str] = mapped_column(Text, nullable=False)
    job_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=default_job_data)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_resume_document_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_resume_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

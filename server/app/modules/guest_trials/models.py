from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.profiles.models import default_resume_data


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GuestTrial(Base):
    __tablename__ = "guest_trials"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'matching', 'result_ready', 'claim_pending', 'claimed', 'expired')",
            name="ck_guest_trials_status",
        ),
        CheckConstraint(
            "provider_search_state IN ('available', 'reserved', 'consumed', 'released')",
            name="ck_guest_trials_provider_search_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active", index=True)
    readiness_version: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_search_state: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    claim_pending_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuestResumeProfile(Base):
    __tablename__ = "guest_resume_profiles"
    __table_args__ = (UniqueConstraint("guest_trial_id", name="uq_guest_resume_profiles_trial"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("guest_trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_guest_document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("guest_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resume_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=default_resume_data)
    readiness_pathway: Mapped[str] = mapped_column(String(32), nullable=False, default="undetermined")
    evidence_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    parser_provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class GuestSearchCriterion(Base):
    __tablename__ = "guest_search_criteria"
    __table_args__ = (UniqueConstraint("guest_trial_id", name="uq_guest_search_criteria_trial"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("guest_trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class GuestDocument(Base):
    __tablename__ = "guest_documents"
    __table_args__ = (
        CheckConstraint("parse_status IN ('pending', 'succeeded', 'failed')", name="ck_guest_documents_parse_status"),
        UniqueConstraint("guest_trial_id", name="uq_guest_documents_trial"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("guest_trials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    parse_suggestions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parser_provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class GuestMatchOperation(Base):
    __tablename__ = "guest_match_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'searching', 'matching', 'result_ready', 'failed')",
            name="ck_guest_match_operations_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_guest_match_operations_attempt_count"),
        UniqueConstraint("guest_trial_id", name="uq_guest_match_operations_trial"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_trials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuestProviderAttempt(Base):
    __tablename__ = "guest_provider_attempts"
    __table_args__ = (
        CheckConstraint("state IN ('reserved', 'consumed', 'released')", name="ck_guest_provider_attempts_state"),
        UniqueConstraint("guest_trial_id", "idempotency_key", name="uq_guest_provider_attempts_trial_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_trials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_feature: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    safe_outcome: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reserved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuestMatchCandidate(Base):
    __tablename__ = "guest_match_candidates"
    __table_args__ = (
        CheckConstraint("provider_rank >= 1", name="ck_guest_match_candidates_rank"),
        CheckConstraint(
            "match_score IS NULL OR (match_score >= 0 AND match_score <= 10)",
            name="ck_guest_match_candidates_score",
        ),
        UniqueConstraint("operation_id", "provider_rank", name="uq_guest_match_candidates_operation_rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_trials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_match_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    job_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    matcher_provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GuestMatchResult(Base):
    __tablename__ = "guest_match_results"
    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 10", name="ck_guest_match_results_score"),
        UniqueConstraint("guest_trial_id", name="uq_guest_match_results_trial"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guest_trial_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_trials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_match_operations.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("guest_match_candidates.id", ondelete="CASCADE"), nullable=False
    )
    profile_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    job_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    match_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

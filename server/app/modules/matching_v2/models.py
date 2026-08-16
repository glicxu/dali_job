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


class CanonicalSource(Base):
    __tablename__ = "matching_canonical_sources"
    __table_args__ = (
        CheckConstraint(
            "(owner_kind = 'authenticated' AND workspace_id IS NOT NULL AND user_id IS NOT NULL "
            "AND guest_trial_id IS NULL) OR "
            "(owner_kind = 'guest' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NOT NULL) OR "
            "(owner_kind = 'shared' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NULL)",
            name="ck_matching_sources_owner",
        ),
        CheckConstraint(
            "source_type IN ('resume', 'job')",
            name="ck_matching_sources_type",
        ),
        Index("ix_matching_sources_public_id", "public_id", unique=True),
        Index("ix_matching_sources_workspace", "workspace_id"),
        Index("ix_matching_sources_user", "user_id"),
        Index("ix_matching_sources_guest", "guest_trial_id"),
        Index("ix_matching_sources_resume", "resume_profile_id"),
        Index("ix_matching_sources_guest_resume", "guest_resume_profile_id"),
        Index("ix_matching_sources_document_version", "document_version_id"),
        Index("ix_matching_sources_hash", "source_hash"),
        Index("ix_matching_sources_cache_key", "cache_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    guest_trial_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("guest_trials.id", ondelete="CASCADE"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resume_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    guest_resume_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("guest_resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("document_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_extraction_version: Mapped[str] = mapped_column(String(100), nullable=False)
    ocr_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    canonicalization_version: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="en")
    cache_key: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceSpan(Base):
    __tablename__ = "matching_source_spans"
    __table_args__ = (
        UniqueConstraint("canonical_source_id", "span_id", name="uq_matching_source_spans_source_span"),
        CheckConstraint("start_utf8_byte >= 0", name="ck_matching_spans_start_nonnegative"),
        CheckConstraint("end_utf8_byte > start_utf8_byte", name="ck_matching_spans_valid_range"),
        Index("ix_matching_spans_source", "canonical_source_id"),
        Index("ix_matching_spans_span_id", "span_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matching_canonical_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    span_id: Mapped[str] = mapped_column(String(180), nullable=False)
    section: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_utf8_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    end_utf8_byte: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CandidateProfileVersion(Base):
    __tablename__ = "matching_candidate_profile_versions"
    __table_args__ = (
        Index("ix_matching_candidate_versions_public", "public_id", unique=True),
        Index("ix_matching_candidate_versions_source", "canonical_source_id"),
        Index("ix_matching_candidate_versions_resume", "resume_profile_id"),
        Index("ix_matching_candidate_versions_cache", "cache_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_source_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matching_canonical_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("resume_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    response_schema_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    semantic_validator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_execution_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact: Mapped[dict] = mapped_column(JSON, nullable=False)
    quality: Mapped[dict] = mapped_column(JSON, nullable=False)
    recommended_primary_career_profile_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    cache_key: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CandidateCareerProfile(Base):
    __tablename__ = "matching_candidate_career_profiles"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_version_id",
            "career_profile_id",
            name="uq_matching_career_profiles_durable_id",
        ),
        UniqueConstraint(
            "candidate_profile_version_id",
            "local_ref",
            name="uq_matching_career_profiles_local_ref",
        ),
        Index("ix_matching_career_profiles_version", "candidate_profile_version_id"),
        Index("ix_matching_career_profiles_id", "career_profile_id"),
        Index("ix_matching_career_profiles_role", "role_family"),
        Index("ix_matching_career_profiles_track", "track"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_profile_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matching_candidate_profile_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    career_profile_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    role_family: Mapped[str] = mapped_column(String(100), nullable=False)
    track: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    dimension_signals: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CandidateCareerSelection(Base):
    __tablename__ = "matching_candidate_career_selections"
    __table_args__ = (
        UniqueConstraint(
            "candidate_profile_version_id",
            "revision",
            name="uq_matching_career_selections_revision",
        ),
        CheckConstraint(
            "selection_source IN ('model_default', 'user_confirmed', 'operator_corrected')",
            name="ck_matching_career_selections_source",
        ),
        Index("ix_matching_career_selections_version", "candidate_profile_version_id"),
        Index("ix_matching_career_selections_profile", "candidate_career_profile_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_profile_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("matching_candidate_profile_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_career_profile_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("matching_candidate_career_profiles.id", ondelete="RESTRICT"),
        nullable=True,
    )
    selection_source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class JobProfileVersion(Base):
    __tablename__ = "matching_job_profile_versions"
    __table_args__ = (
        Index("ix_matching_job_versions_public", "public_id", unique=True),
        Index("ix_matching_job_versions_source", "canonical_source_id"),
        Index("ix_matching_job_versions_cache_job", "jobs_cache_id"),
        Index("ix_matching_job_versions_cache", "cache_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_canonical_sources.id", ondelete="CASCADE"), nullable=False
    )
    jobs_cache_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs_cache.id", ondelete="SET NULL"), nullable=True
    )
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    response_schema_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    deduplication_version: Mapped[str] = mapped_column(String(100), nullable=False)
    semantic_validator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_execution_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact: Mapped[dict] = mapped_column(JSON, nullable=False)
    cleanup: Mapped[dict] = mapped_column(JSON, nullable=False)
    cache_key: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRequirement(Base):
    __tablename__ = "matching_job_requirements"
    __table_args__ = (
        UniqueConstraint("job_profile_version_id", "requirement_id", name="uq_matching_job_requirements_id"),
        UniqueConstraint("job_profile_version_id", "local_ref", name="uq_matching_job_requirements_ref"),
        Index("ix_matching_job_requirements_version", "job_profile_version_id"),
        Index("ix_matching_job_requirements_id", "requirement_id"),
        Index("ix_matching_job_requirements_dimension", "scoring_dimension"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_profile_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_job_profile_versions.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    local_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    scoring_dimension: Mapped[str] = mapped_column(String(60), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(String(30), nullable=False)
    hard_constraint: Mapped[bool] = mapped_column(nullable=False)
    acceptable_evidence_contexts: Mapped[list] = mapped_column(JSON, nullable=False)
    minimum_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    explicit_alternatives: Mapped[list] = mapped_column(JSON, nullable=False)
    policy_alternative_group: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class QualificationAssessment(Base):
    __tablename__ = "matching_qualification_assessments"
    __table_args__ = (
        CheckConstraint(
            "(owner_kind = 'authenticated' AND workspace_id IS NOT NULL AND user_id IS NOT NULL "
            "AND guest_trial_id IS NULL) OR "
            "(owner_kind = 'guest' AND workspace_id IS NULL AND user_id IS NULL "
            "AND guest_trial_id IS NOT NULL)",
            name="ck_matching_qualifications_owner",
        ),
        Index("ix_matching_qualifications_public", "public_id", unique=True),
        Index("ix_matching_qualifications_candidate", "candidate_profile_version_id"),
        Index("ix_matching_qualifications_job", "job_profile_version_id"),
        Index("ix_matching_qualifications_workspace", "workspace_id"),
        Index("ix_matching_qualifications_user", "user_id"),
        Index("ix_matching_qualifications_guest", "guest_trial_id"),
        Index("ix_matching_qualifications_cache", "cache_key", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    guest_trial_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("guest_trials.id", ondelete="CASCADE"), nullable=True
    )
    candidate_profile_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_candidate_profile_versions.id", ondelete="CASCADE"), nullable=False
    )
    candidate_career_selection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_candidate_career_selections.id", ondelete="CASCADE"), nullable=False
    )
    candidate_career_selection_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    selected_candidate_career_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("matching_candidate_career_profiles.id", ondelete="SET NULL"), nullable=True
    )
    selection_reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    job_profile_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_job_profile_versions.id", ondelete="CASCADE"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    response_schema_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    selection_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    matching_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    semantic_validator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    alternative_policy_hashes: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    provider_execution_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    artifact: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_quality: Mapped[dict] = mapped_column(JSON, nullable=False)
    cache_key: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RequirementAssessment(Base):
    __tablename__ = "matching_requirement_assessments"
    __table_args__ = (
        UniqueConstraint(
            "qualification_assessment_id", "requirement_id", name="uq_matching_requirement_assessments_item"
        ),
        CheckConstraint(
            "collection_kind IN ('normal', 'hard_constraint')",
            name="ck_matching_requirement_assessments_collection",
        ),
        Index("ix_matching_requirement_assessments_qualification", "qualification_assessment_id"),
        Index("ix_matching_requirement_assessments_requirement", "job_requirement_id"),
        Index("ix_matching_requirement_assessments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qualification_assessment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_qualification_assessments.id", ondelete="CASCADE"), nullable=False
    )
    job_requirement_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matching_job_requirements.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False)
    collection_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    alternative_group_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    alternative_policy_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    missing: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PromptPolicyRegistryRecord(Base):
    __tablename__ = "matching_policy_registry"
    __table_args__ = (
        UniqueConstraint("artifact_type", "version", name="uq_matching_policy_registry_type_version"),
        Index("ix_matching_policy_registry_type", "artifact_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(120), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

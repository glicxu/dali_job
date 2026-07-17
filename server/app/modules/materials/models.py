from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeneratedApplicationMaterial(Base):
    __tablename__ = "generated_application_materials"
    __table_args__ = (
        CheckConstraint(
            "material_type IN ('tailored_resume', 'cover_letter')",
            name="ck_generated_application_materials_type",
        ),
        UniqueConstraint(
            "workspace_id", "user_id", "application_id", "material_type",
            name="uq_generated_application_materials_owner_application_type",
        ),
        Index("ix_gen_materials_workspace", "workspace_id"),
        Index("ix_gen_materials_user", "user_id"),
        Index("ix_gen_materials_application", "application_id"),
        Index("ix_gen_materials_type", "material_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    application_id: Mapped[int] = mapped_column(Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    material_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class GeneratedApplicationMaterialVersion(Base):
    __tablename__ = "generated_application_material_versions"
    __table_args__ = (
        CheckConstraint("version_source IN ('ai', 'user')", name="ck_generated_material_versions_source"),
        UniqueConstraint("material_id", "version_number", name="uq_generated_material_versions_number"),
        Index("ix_gen_material_versions_material", "material_id"),
        Index("ix_gen_material_versions_parent", "parent_version_id"),
        Index("ix_gen_material_versions_document", "source_document_version_id"),
        Index("ix_gen_material_versions_source", "source_material_version_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("generated_application_materials.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("generated_application_material_versions.id", ondelete="SET NULL"), nullable=True)
    operation_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("managed_operations.id", ondelete="SET NULL"), nullable=True, unique=True)
    source_document_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True)
    source_material_version_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("generated_application_material_versions.id", ondelete="SET NULL"), nullable=True)
    source_resume_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    job_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_notes_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    version_source: Mapped[str] = mapped_column(String(16), nullable=False, default="ai")
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="openai")
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_execution_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

"""add versioned application-generated materials

Revision ID: 20260717_0024
Revises: 20260715_0023
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260717_0024"
down_revision = "20260715_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_application_materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("material_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("material_type IN ('tailored_resume', 'cover_letter')", name="ck_generated_application_materials_type"),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", "application_id", "material_type", name="uq_generated_application_materials_owner_application_type"),
    )
    for name, column in (
        ("ix_gen_materials_workspace", "workspace_id"),
        ("ix_gen_materials_user", "user_id"),
        ("ix_gen_materials_application", "application_id"),
        ("ix_gen_materials_type", "material_type"),
    ):
        op.create_index(name, "generated_application_materials", [column], unique=False)

    op.create_table(
        "generated_application_material_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.Integer(), nullable=True),
        sa.Column("operation_id", sa.Integer(), nullable=True),
        sa.Column("source_document_version_id", sa.Integer(), nullable=True),
        sa.Column("source_material_version_id", sa.Integer(), nullable=True),
        sa.Column("source_resume_snapshot", sa.JSON(), nullable=False),
        sa.Column("job_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_notes_snapshot", sa.Text(), nullable=True),
        sa.Column("content_data", sa.JSON(), nullable=True),
        sa.Column("version_source", sa.String(length=16), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version_source IN ('ai', 'user')", name="ck_generated_material_versions_source"),
        sa.ForeignKeyConstraint(["material_id"], ["generated_application_materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["managed_operations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["generated_application_material_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_version_id"], ["document_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_material_version_id"], ["generated_application_material_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", "version_number", name="uq_generated_material_versions_number"),
        sa.UniqueConstraint("operation_id"),
    )
    for name, column in (
        ("ix_gen_material_versions_material", "material_id"),
        ("ix_gen_material_versions_parent", "parent_version_id"),
        ("ix_gen_material_versions_document", "source_document_version_id"),
        ("ix_gen_material_versions_source", "source_material_version_id"),
    ):
        op.create_index(name, "generated_application_material_versions", [column], unique=False)


def downgrade() -> None:
    op.drop_table("generated_application_material_versions")
    op.drop_table("generated_application_materials")

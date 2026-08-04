"""link generated material versions to rendered documents

Revision ID: 20260722_0025
Revises: 20260717_0024
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260722_0025"
down_revision = "20260717_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_application_material_versions",
        sa.Column("output_document_version_id", sa.Integer(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_generated_material_versions_output_document",
        "generated_application_material_versions",
        ["output_document_version_id"],
    )
    op.create_foreign_key(
        "fk_gen_material_versions_output_document",
        "generated_application_material_versions",
        "document_versions",
        ["output_document_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_gen_material_versions_output_document",
        "generated_application_material_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_generated_material_versions_output_document",
        "generated_application_material_versions",
        type_="unique",
    )
    op.drop_column("generated_application_material_versions", "output_document_version_id")

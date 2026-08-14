"""add soft deletion markers for user-owned account data

Revision ID: 20260814_0030
Revises: 20260812_0029
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0030"
down_revision = "20260812_0029"
branch_labels = None
depends_on = None


TABLES = (
    "workspaces",
    "document_versions",
    "document_download_tickets",
    "job_resume_matches",
    "applications",
    "application_status_history",
    "application_events",
    "application_notes",
    "application_documents",
    "application_tasks",
    "interviews",
    "interview_notes",
    "interview_prep_guides",
    "managed_operations",
    "generated_application_materials",
    "generated_application_material_versions",
    "user_reports",
)


def upgrade() -> None:
    for table_name in TABLES:
        op.add_column(
            table_name,
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.drop_column(table_name, "deleted_at")

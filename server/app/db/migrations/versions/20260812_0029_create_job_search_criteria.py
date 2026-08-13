"""create job search criteria

Revision ID: 20260812_0029
Revises: 20260810_0028
Create Date: 2026-08-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260812_0029"
down_revision = "20260810_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_search_criteria",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="custom"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_search_criteria_workspace_id", "job_search_criteria", ["workspace_id"])
    op.create_index("ix_job_search_criteria_user_id", "job_search_criteria", ["user_id"])
    op.create_index("ix_job_search_criteria_resume_profile_id", "job_search_criteria", ["resume_profile_id"])


def downgrade() -> None:
    op.drop_index("ix_job_search_criteria_resume_profile_id", table_name="job_search_criteria")
    op.drop_index("ix_job_search_criteria_user_id", table_name="job_search_criteria")
    op.drop_index("ix_job_search_criteria_workspace_id", table_name="job_search_criteria")
    op.drop_table("job_search_criteria")

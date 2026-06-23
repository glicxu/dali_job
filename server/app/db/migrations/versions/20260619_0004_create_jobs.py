"""create job cache and user job storage

Revision ID: 20260619_0004
Revises: 20260618_0003
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

revision = "20260619_0004"
down_revision = "20260618_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_url_hash", sa.String(length=64), nullable=True),
        sa.Column("raw_description_text", sa.Text(), nullable=False),
        sa.Column("job_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_cache_source_url_hash", "jobs_cache", ["source_url_hash"], unique=False)

    op.create_table(
        "user_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("jobs_cache_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_description_text", sa.Text(), nullable=False),
        sa.Column("job_data", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["jobs_cache_id"], ["jobs_cache.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_jobs_jobs_cache_id", "user_jobs", ["jobs_cache_id"], unique=False)
    op.create_index("ix_user_jobs_user_id", "user_jobs", ["user_id"], unique=False)
    op.create_index("ix_user_jobs_workspace_id", "user_jobs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_jobs_workspace_id", table_name="user_jobs")
    op.drop_index("ix_user_jobs_user_id", table_name="user_jobs")
    op.drop_index("ix_user_jobs_jobs_cache_id", table_name="user_jobs")
    op.drop_table("user_jobs")
    op.drop_index("ix_jobs_cache_source_url_hash", table_name="jobs_cache")
    op.drop_table("jobs_cache")

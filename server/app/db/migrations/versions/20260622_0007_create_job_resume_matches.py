"""create job resume matches

Revision ID: 20260622_0007
Revises: 20260619_0006
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260622_0007"
down_revision = "20260619_0006"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("job_resume_matches"):
        op.create_table(
            "job_resume_matches",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("workspace_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("user_job_id", sa.Integer(), nullable=False),
            sa.Column("jobs_cache_id", sa.Integer(), nullable=True),
            sa.Column("resume_document_id", sa.Integer(), nullable=True),
            sa.Column("resume_source", sa.String(length=64), nullable=False),
            sa.Column("match_score", sa.Integer(), nullable=False),
            sa.Column("match_data", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["jobs_cache_id"], ["jobs_cache.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["resume_document_id"], ["documents.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_job_id"], ["user_saved_jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("job_resume_matches", "ix_job_resume_matches_jobs_cache_id"):
        op.create_index("ix_job_resume_matches_jobs_cache_id", "job_resume_matches", ["jobs_cache_id"], unique=False)
    if not _index_exists("job_resume_matches", "ix_job_resume_matches_resume_document_id"):
        op.create_index(
            "ix_job_resume_matches_resume_document_id",
            "job_resume_matches",
            ["resume_document_id"],
            unique=False,
        )
    if not _index_exists("job_resume_matches", "ix_job_resume_matches_user_id"):
        op.create_index("ix_job_resume_matches_user_id", "job_resume_matches", ["user_id"], unique=False)
    if not _index_exists("job_resume_matches", "ix_job_resume_matches_user_job_id"):
        op.create_index("ix_job_resume_matches_user_job_id", "job_resume_matches", ["user_job_id"], unique=False)
    if not _index_exists("job_resume_matches", "ix_job_resume_matches_workspace_id"):
        op.create_index("ix_job_resume_matches_workspace_id", "job_resume_matches", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_job_resume_matches_workspace_id", table_name="job_resume_matches")
    op.drop_index("ix_job_resume_matches_user_job_id", table_name="job_resume_matches")
    op.drop_index("ix_job_resume_matches_user_id", table_name="job_resume_matches")
    op.drop_index("ix_job_resume_matches_resume_document_id", table_name="job_resume_matches")
    op.drop_index("ix_job_resume_matches_jobs_cache_id", table_name="job_resume_matches")
    op.drop_table("job_resume_matches")

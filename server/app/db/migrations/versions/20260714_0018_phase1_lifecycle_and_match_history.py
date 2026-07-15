"""add lifecycle controls and immutable match provenance

Revision ID: 20260714_0018
Revises: 20260713_0017
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260714_0018"
down_revision = "20260713_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_saved_jobs", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_user_saved_jobs_archived_at", "user_saved_jobs", ["archived_at"], unique=False)

    op.add_column("job_resume_matches", sa.Column("resume_data_snapshot", sa.JSON(), nullable=True))
    op.add_column("job_resume_matches", sa.Column("job_data_snapshot", sa.JSON(), nullable=True))
    op.add_column("job_resume_matches", sa.Column("resume_snapshot_hash", sa.String(length=64), nullable=True))
    op.add_column("job_resume_matches", sa.Column("job_snapshot_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "job_resume_matches",
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="openai"),
    )
    op.add_column("job_resume_matches", sa.Column("model_name", sa.String(length=255), nullable=True))
    op.add_column(
        "job_resume_matches",
        sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default="resume-job-match-v1"),
    )
    op.add_column(
        "job_resume_matches",
        sa.Column("schema_version", sa.String(length=64), nullable=False, server_default="resume-job-match-v1"),
    )
    op.add_column(
        "job_resume_matches",
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
    )

    # Existing rows predate snapshots. Empty objects make that absence explicit without inventing inputs.
    op.execute("UPDATE job_resume_matches SET resume_data_snapshot = JSON_OBJECT() WHERE resume_data_snapshot IS NULL")
    op.execute("UPDATE job_resume_matches SET job_data_snapshot = JSON_OBJECT() WHERE job_data_snapshot IS NULL")
    op.execute("UPDATE job_resume_matches SET resume_snapshot_hash = '' WHERE resume_snapshot_hash IS NULL")
    op.execute("UPDATE job_resume_matches SET job_snapshot_hash = '' WHERE job_snapshot_hash IS NULL")
    op.alter_column("job_resume_matches", "resume_data_snapshot", existing_type=sa.JSON(), nullable=False)
    op.alter_column("job_resume_matches", "job_data_snapshot", existing_type=sa.JSON(), nullable=False)
    op.alter_column("job_resume_matches", "resume_snapshot_hash", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("job_resume_matches", "job_snapshot_hash", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    op.drop_column("job_resume_matches", "provider_execution_reference")
    op.drop_column("job_resume_matches", "schema_version")
    op.drop_column("job_resume_matches", "prompt_version")
    op.drop_column("job_resume_matches", "model_name")
    op.drop_column("job_resume_matches", "provider")
    op.drop_column("job_resume_matches", "job_snapshot_hash")
    op.drop_column("job_resume_matches", "resume_snapshot_hash")
    op.drop_column("job_resume_matches", "job_data_snapshot")
    op.drop_column("job_resume_matches", "resume_data_snapshot")
    op.drop_index("ix_user_saved_jobs_archived_at", table_name="user_saved_jobs")
    op.drop_column("user_saved_jobs", "archived_at")

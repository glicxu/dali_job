"""add matching evaluation workbench persistence

Revision ID: 20260815_0042
Revises: 20260815_0041
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0042"
down_revision = "20260815_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_evaluation_job_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("benchmark_release", sa.String(length=100), nullable=False),
        sa.Column("coverage_slot", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_hash", sa.String(length=71), nullable=False),
        sa.Column("jobs_cache_id", sa.Integer(), nullable=False),
        sa.Column("user_saved_job_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("raw_description_text", sa.Text(), nullable=False),
        sa.Column("capture_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["jobs_cache_id"], ["jobs_cache.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_saved_job_id"], ["user_saved_jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "benchmark_release",
            "source_hash",
            name="uq_matching_eval_snapshot_workspace_release_hash",
        ),
    )
    op.create_index("ix_matching_eval_snapshots_public", "matching_evaluation_job_snapshots", ["public_id"], unique=True)
    op.create_index("ix_matching_eval_snapshots_workspace", "matching_evaluation_job_snapshots", ["workspace_id"])
    op.create_index("ix_matching_eval_snapshots_user", "matching_evaluation_job_snapshots", ["user_id"])

    op.create_table(
        "matching_evaluation_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("benchmark_release", sa.String(length=100), nullable=False),
        sa.Column("job_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=False),
        sa.Column("qualification_assessment_id", sa.Integer(), nullable=False),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_snapshot_id"], ["matching_evaluation_job_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidate_profile_version_id"], ["matching_candidate_profile_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_profile_version_id"], ["matching_job_profile_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["qualification_assessment_id"], ["matching_qualification_assessments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_eval_runs_public", "matching_evaluation_runs", ["public_id"], unique=True)
    op.create_index("ix_matching_eval_runs_workspace", "matching_evaluation_runs", ["workspace_id"])
    op.create_index("ix_matching_eval_runs_user", "matching_evaluation_runs", ["user_id"])
    op.create_index("ix_matching_eval_runs_snapshot", "matching_evaluation_runs", ["job_snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_matching_eval_runs_snapshot", table_name="matching_evaluation_runs")
    op.drop_index("ix_matching_eval_runs_user", table_name="matching_evaluation_runs")
    op.drop_index("ix_matching_eval_runs_workspace", table_name="matching_evaluation_runs")
    op.drop_index("ix_matching_eval_runs_public", table_name="matching_evaluation_runs")
    op.drop_table("matching_evaluation_runs")
    op.drop_index("ix_matching_eval_snapshots_user", table_name="matching_evaluation_job_snapshots")
    op.drop_index("ix_matching_eval_snapshots_workspace", table_name="matching_evaluation_job_snapshots")
    op.drop_index("ix_matching_eval_snapshots_public", table_name="matching_evaluation_job_snapshots")
    op.drop_table("matching_evaluation_job_snapshots")

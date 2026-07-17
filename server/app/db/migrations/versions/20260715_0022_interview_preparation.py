"""add interview scheduling and preparation history

Revision ID: 20260715_0022
Revises: 20260715_0021
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0022"
down_revision = "20260715_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("interview_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("location_or_url", sa.String(length=2048), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=True),
        sa.Column("private_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "interview_type IN ('recruiter_screen', 'phone', 'technical', 'behavioral', 'hiring_manager', 'panel', 'final', 'other')",
            name="ck_interviews_type",
        ),
        sa.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_interviews_status"),
        sa.CheckConstraint(
            "stage IN ('recruiter_contact', 'assessment', 'phone_screen', 'technical_interview', 'final_interview', 'other')",
            name="ck_interviews_stage",
        ),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('advanced', 'rejected', 'offer', 'withdrawn', 'no_decision')",
            name="ck_interviews_outcome",
        ),
        sa.CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes >= 15 AND duration_minutes <= 480)",
            name="ck_interviews_duration",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("application_id", "scheduled_at", "status", "user_id", "workspace_id"):
        op.create_index(f"ix_interviews_{column}", "interviews", [column], unique=False)

    op.create_table(
        "interview_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_notes_interview_id", "interview_notes", ["interview_id"], unique=False)

    op.create_table(
        "interview_prep_guides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("interview_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=True),
        sa.Column("resume_profile_id", sa.Integer(), nullable=True),
        sa.Column("resume_data_snapshot", sa.JSON(), nullable=False),
        sa.Column("job_data_snapshot", sa.JSON(), nullable=False),
        sa.Column("company_notes_snapshot", sa.Text(), nullable=True),
        sa.Column("source_warnings", sa.JSON(), nullable=False),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("provider_execution_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["managed_operations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resume_profile_id"], ["resume_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
    )
    for column in ("interview_id", "resume_profile_id", "user_id", "workspace_id"):
        op.create_index(f"ix_interview_prep_guides_{column}", "interview_prep_guides", [column], unique=False)


def downgrade() -> None:
    for column in ("workspace_id", "user_id", "resume_profile_id", "interview_id"):
        op.drop_index(f"ix_interview_prep_guides_{column}", table_name="interview_prep_guides")
    op.drop_table("interview_prep_guides")
    op.drop_index("ix_interview_notes_interview_id", table_name="interview_notes")
    op.drop_table("interview_notes")
    for column in ("workspace_id", "user_id", "status", "scheduled_at", "application_id"):
        op.drop_index(f"ix_interviews_{column}", table_name="interviews")
    op.drop_table("interviews")

"""add user feedback for normal job matches

Revision ID: 20260816_0048
Revises: 20260816_0047
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0048"
down_revision = "20260816_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_match_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_resume_match_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_job_match_feedback_score"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_resume_match_id"], ["job_resume_matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_resume_match_id", name="uq_job_match_feedback_user_match"),
    )
    op.create_index("ix_job_match_feedback_workspace_id", "job_match_feedback", ["workspace_id"])
    op.create_index("ix_job_match_feedback_user_id", "job_match_feedback", ["user_id"])
    op.create_index("ix_job_match_feedback_job_resume_match_id", "job_match_feedback", ["job_resume_match_id"])


def downgrade() -> None:
    op.drop_index("ix_job_match_feedback_job_resume_match_id", table_name="job_match_feedback")
    op.drop_index("ix_job_match_feedback_user_id", table_name="job_match_feedback")
    op.drop_index("ix_job_match_feedback_workspace_id", table_name="job_match_feedback")
    op.drop_table("job_match_feedback")

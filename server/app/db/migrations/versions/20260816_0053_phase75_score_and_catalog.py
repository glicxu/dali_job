"""add nullable guest scores and explicit trial catalog eligibility

Revision ID: 20260816_0053
Revises: 20260816_0052
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0053"
down_revision = "20260816_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matching_job_profile_versions",
        sa.Column("trial_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "matching_job_profile_versions",
        sa.Column("trial_priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "matching_job_profile_versions",
        sa.Column("quality_tier", sa.String(40), nullable=True),
    )
    op.create_index(
        "ix_matching_job_profile_versions_trial_eligible",
        "matching_job_profile_versions",
        ["trial_eligible"],
    )
    op.execute(
        sa.text(
            "UPDATE matching_job_profile_versions "
            "SET trial_eligible = true, quality_tier = 'curated_evaluation' "
            "WHERE jobs_cache_id IN ("
            "SELECT jobs_cache_id FROM matching_evaluation_job_snapshots "
            "WHERE review_status = 'accepted'"
            ")"
        )
    )
    op.alter_column("matching_job_profile_versions", "trial_eligible", server_default=None)
    op.alter_column("matching_job_profile_versions", "trial_priority", server_default=None)
    op.alter_column("guest_match_results", "match_score", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column("guest_match_results", "match_score", existing_type=sa.Integer(), nullable=False)
    op.drop_index(
        "ix_matching_job_profile_versions_trial_eligible",
        table_name="matching_job_profile_versions",
    )
    op.drop_column("matching_job_profile_versions", "quality_tier")
    op.drop_column("matching_job_profile_versions", "trial_priority")
    op.drop_column("matching_job_profile_versions", "trial_eligible")

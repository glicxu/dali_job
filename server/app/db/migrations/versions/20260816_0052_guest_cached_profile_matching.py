"""reference V2 artifacts from guest cached-profile matches

Revision ID: 20260816_0052
Revises: 20260816_0051
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0052"
down_revision = "20260816_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guest_match_candidates",
        sa.Column("job_profile_version_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_guest_match_candidates_job_profile",
        "guest_match_candidates",
        "matching_job_profile_versions",
        ["job_profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guest_match_candidates_job_profile_version_id",
        "guest_match_candidates",
        ["job_profile_version_id"],
    )
    op.add_column(
        "guest_match_results",
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "guest_match_results",
        sa.Column("qualification_assessment_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_guest_match_results_candidate_profile",
        "guest_match_results",
        "matching_candidate_profile_versions",
        ["candidate_profile_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_guest_match_results_qualification",
        "guest_match_results",
        "matching_qualification_assessments",
        ["qualification_assessment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guest_match_results_candidate_profile_version_id",
        "guest_match_results",
        ["candidate_profile_version_id"],
    )
    op.create_index(
        "ix_guest_match_results_qualification_assessment_id",
        "guest_match_results",
        ["qualification_assessment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_guest_match_results_qualification_assessment_id",
        table_name="guest_match_results",
    )
    op.drop_index(
        "ix_guest_match_results_candidate_profile_version_id",
        table_name="guest_match_results",
    )
    op.drop_constraint(
        "fk_guest_match_results_qualification",
        "guest_match_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_guest_match_results_candidate_profile",
        "guest_match_results",
        type_="foreignkey",
    )
    op.drop_column("guest_match_results", "qualification_assessment_id")
    op.drop_column("guest_match_results", "candidate_profile_version_id")
    op.drop_index(
        "ix_guest_match_candidates_job_profile_version_id",
        table_name="guest_match_candidates",
    )
    op.drop_constraint(
        "fk_guest_match_candidates_job_profile",
        "guest_match_candidates",
        type_="foreignkey",
    )
    op.drop_column("guest_match_candidates", "job_profile_version_id")

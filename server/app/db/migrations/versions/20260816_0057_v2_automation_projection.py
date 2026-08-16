"""link automation presentation matches to V2 results

Revision ID: 20260816_0057
Revises: 20260816_0056
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0057"
down_revision = "20260816_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_resume_matches",
        sa.Column("matching_v2_result_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_job_resume_matches_matching_v2_result_id",
        "job_resume_matches",
        "matching_match_results",
        ["matching_v2_result_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_job_resume_matches_matching_v2_result_id",
        "job_resume_matches",
        ["matching_v2_result_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_resume_matches_matching_v2_result_id",
        table_name="job_resume_matches",
    )
    op.drop_constraint(
        "fk_job_resume_matches_matching_v2_result_id",
        "job_resume_matches",
        type_="foreignkey",
    )
    op.drop_column("job_resume_matches", "matching_v2_result_id")

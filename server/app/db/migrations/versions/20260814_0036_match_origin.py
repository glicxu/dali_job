"""add match origin provenance

Revision ID: 20260814_0036
Revises: 20260814_0035
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0036"
down_revision = "20260814_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_resume_matches",
        sa.Column(
            "match_origin",
            sa.String(length=32),
            server_default="direct_match",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_job_resume_matches_origin",
        "job_resume_matches",
        "match_origin IN ('direct_match', 'manual_rerun', 'automated_search')",
    )
    op.create_index(
        "ix_job_resume_matches_match_origin",
        "job_resume_matches",
        ["match_origin"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_resume_matches_match_origin", table_name="job_resume_matches")
    op.drop_constraint(
        "ck_job_resume_matches_origin",
        "job_resume_matches",
        type_="check",
    )
    op.drop_column("job_resume_matches", "match_origin")

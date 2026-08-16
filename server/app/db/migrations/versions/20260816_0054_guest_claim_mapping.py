"""persist idempotent guest claim mappings

Revision ID: 20260816_0054
Revises: 20260816_0053
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0054"
down_revision = "20260816_0053"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("claimed_resume_profile_id", "resume_profiles"),
    ("claimed_search_criterion_id", "job_search_criteria"),
    ("claimed_candidate_profile_id", "matching_candidate_profile_versions"),
    ("claimed_qualification_assessment_id", "matching_qualification_assessments"),
)


def upgrade() -> None:
    for column, target in _COLUMNS:
        op.add_column("guest_trials", sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_guest_trials_{column}",
            "guest_trials",
            target,
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for column, _target in reversed(_COLUMNS):
        op.drop_constraint(f"fk_guest_trials_{column}", "guest_trials", type_="foreignkey")
        op.drop_column("guest_trials", column)

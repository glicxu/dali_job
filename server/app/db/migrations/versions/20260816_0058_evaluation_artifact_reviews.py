"""add independent candidate and job profile reviews

Revision ID: 20260816_0058
Revises: 20260816_0057
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0058"
down_revision = "20260816_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_evaluation_artifact_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("candidate_profile_version_id", sa.Integer(), nullable=True),
        sa.Column("job_profile_version_id", sa.Integer(), nullable=True),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('candidate_profile', 'job_profile')",
            name="ck_matching_eval_artifact_reviews_stage",
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_matching_eval_artifact_reviews_score",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_matching_eval_artifact_reviews_confidence",
        ),
        sa.CheckConstraint(
            "(stage = 'candidate_profile' AND candidate_profile_version_id IS NOT NULL "
            "AND job_profile_version_id IS NULL) OR "
            "(stage = 'job_profile' AND job_profile_version_id IS NOT NULL "
            "AND candidate_profile_version_id IS NULL)",
            name="ck_matching_eval_artifact_reviews_target",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["candidate_profile_version_id"],
            ["matching_candidate_profile_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_profile_version_id"],
            ["matching_job_profile_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_matching_eval_artifact_reviews_public",
        "matching_evaluation_artifact_reviews",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_matching_eval_artifact_reviews_workspace",
        "matching_evaluation_artifact_reviews",
        ["workspace_id"],
    )
    op.create_index(
        "ix_matching_eval_artifact_reviews_reviewer",
        "matching_evaluation_artifact_reviews",
        ["reviewer_user_id"],
    )
    op.create_index(
        "ix_matching_eval_artifact_reviews_candidate",
        "matching_evaluation_artifact_reviews",
        ["candidate_profile_version_id"],
    )
    op.create_index(
        "ix_matching_eval_artifact_reviews_job",
        "matching_evaluation_artifact_reviews",
        ["job_profile_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_matching_eval_artifact_reviews_job",
        table_name="matching_evaluation_artifact_reviews",
    )
    op.drop_index(
        "ix_matching_eval_artifact_reviews_candidate",
        table_name="matching_evaluation_artifact_reviews",
    )
    op.drop_index(
        "ix_matching_eval_artifact_reviews_reviewer",
        table_name="matching_evaluation_artifact_reviews",
    )
    op.drop_index(
        "ix_matching_eval_artifact_reviews_workspace",
        table_name="matching_evaluation_artifact_reviews",
    )
    op.drop_index(
        "ix_matching_eval_artifact_reviews_public",
        table_name="matching_evaluation_artifact_reviews",
    )
    op.drop_table("matching_evaluation_artifact_reviews")

"""add overall human match reviews

Revision ID: 20260816_0047
Revises: 20260815_0046
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0047"
down_revision = "20260815_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_evaluation_match_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("review_kind", sa.String(length=30), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "review_kind IN ('independent', 'adjudication')",
            name="ck_matching_eval_match_reviews_kind",
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_matching_eval_match_reviews_score",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_matching_eval_match_reviews_confidence",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"], ["matching_evaluation_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_matching_eval_match_reviews_public",
        "matching_evaluation_match_reviews",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_matching_eval_match_reviews_run",
        "matching_evaluation_match_reviews",
        ["evaluation_run_id"],
    )
    op.create_index(
        "ix_matching_eval_match_reviews_reviewer",
        "matching_evaluation_match_reviews",
        ["reviewer_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_matching_eval_match_reviews_reviewer",
        table_name="matching_evaluation_match_reviews",
    )
    op.drop_index(
        "ix_matching_eval_match_reviews_run",
        table_name="matching_evaluation_match_reviews",
    )
    op.drop_index(
        "ix_matching_eval_match_reviews_public",
        table_name="matching_evaluation_match_reviews",
    )
    op.drop_table("matching_evaluation_match_reviews")

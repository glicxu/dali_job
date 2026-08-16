"""add evaluation manifests and reviewer annotations

Revision ID: 20260815_0043
Revises: 20260815_0042
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0043"
down_revision = "20260815_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matching_evaluation_runs",
        sa.Column("manifest", sa.JSON(), nullable=True),
    )
    op.execute(sa.text("UPDATE matching_evaluation_runs SET manifest = '{}' WHERE manifest IS NULL"))
    with op.batch_alter_table("matching_evaluation_runs") as batch_op:
        batch_op.alter_column("manifest", existing_type=sa.JSON(), nullable=False)
    op.create_table(
        "matching_evaluation_annotations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("target_ref", sa.String(length=160), nullable=False),
        sa.Column("review_kind", sa.String(length=30), nullable=False),
        sa.Column("verdict", sa.String(length=30), nullable=False),
        sa.Column("evidence_support", sa.String(length=30), nullable=False),
        sa.Column("expected_value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("error_taxonomy_code", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stage IN ('candidate_profile', 'job_profile', 'qualification')",
            name="ck_matching_eval_annotations_stage",
        ),
        sa.CheckConstraint(
            "review_kind IN ('independent', 'adjudication')",
            name="ck_matching_eval_annotations_review_kind",
        ),
        sa.CheckConstraint(
            "verdict IN ('correct', 'partially_correct', 'incorrect', 'missing', 'ambiguous')",
            name="ck_matching_eval_annotations_verdict",
        ),
        sa.CheckConstraint(
            "evidence_support IN ('supported', 'partially_supported', 'unsupported', 'ambiguous', 'not_reviewed')",
            name="ck_matching_eval_annotations_evidence",
        ),
        sa.CheckConstraint(
            "severity IN ('none', 'minor', 'major', 'severe')",
            name="ck_matching_eval_annotations_severity",
        ),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["matching_evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_matching_eval_annotations_public", "matching_evaluation_annotations", ["public_id"], unique=True)
    op.create_index("ix_matching_eval_annotations_run", "matching_evaluation_annotations", ["evaluation_run_id"])
    op.create_index("ix_matching_eval_annotations_reviewer", "matching_evaluation_annotations", ["reviewer_user_id"])
    op.create_index("ix_matching_eval_annotations_target", "matching_evaluation_annotations", ["stage", "target_ref"])


def downgrade() -> None:
    op.drop_index("ix_matching_eval_annotations_target", table_name="matching_evaluation_annotations")
    op.drop_index("ix_matching_eval_annotations_reviewer", table_name="matching_evaluation_annotations")
    op.drop_index("ix_matching_eval_annotations_run", table_name="matching_evaluation_annotations")
    op.drop_index("ix_matching_eval_annotations_public", table_name="matching_evaluation_annotations")
    op.drop_table("matching_evaluation_annotations")
    op.drop_column("matching_evaluation_runs", "manifest")

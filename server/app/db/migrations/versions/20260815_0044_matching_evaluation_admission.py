"""add evaluation snapshot admission state

Revision ID: 20260815_0044
Revises: 20260815_0043
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0044"
down_revision = "20260815_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_name = "matching_evaluation_job_snapshots"
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if "review_status" not in columns:
            batch_op.add_column(
                sa.Column("review_status", sa.String(length=30), nullable=False, server_default="draft")
            )
        if "review_notes" not in columns:
            batch_op.add_column(sa.Column("review_notes", sa.Text(), nullable=True))
        if "reviewed_by_user_id" not in columns:
            batch_op.add_column(sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True))
        if "reviewed_at" not in columns:
            batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(sa.text(f"UPDATE {table_name} SET review_notes = '' WHERE review_notes IS NULL"))
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column("review_notes", existing_type=sa.Text(), nullable=False)

    inspector = sa.inspect(op.get_bind())
    foreign_keys = {item.get("name") for item in inspector.get_foreign_keys(table_name)}
    checks = {item.get("name") for item in inspector.get_check_constraints(table_name)}
    with op.batch_alter_table(table_name) as batch_op:
        if "fk_matching_eval_snapshot_reviewer" not in foreign_keys:
            batch_op.create_foreign_key(
                "fk_matching_eval_snapshot_reviewer",
                "users",
                ["reviewed_by_user_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "ck_matching_eval_snapshot_review_status" not in checks:
            batch_op.create_check_constraint(
                "ck_matching_eval_snapshot_review_status",
                "review_status IN ('draft', 'accepted', 'rejected')",
            )


def downgrade() -> None:
    with op.batch_alter_table("matching_evaluation_job_snapshots") as batch_op:
        batch_op.drop_constraint("ck_matching_eval_snapshot_review_status", type_="check")
        batch_op.drop_constraint("fk_matching_eval_snapshot_reviewer", type_="foreignkey")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_user_id")
        batch_op.drop_column("review_notes")
        batch_op.drop_column("review_status")

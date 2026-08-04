"""add account roles and user reports

Revision ID: 20260804_0027
Revises: 20260803_0026
Create Date: 2026-08-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260804_0027"
down_revision = "20260803_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="user"),
    )
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'admin')")
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "user_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="new"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('bug', 'feedback', 'account', 'other')",
            name="ck_user_reports_category",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'in_review', 'resolved', 'closed')",
            name="ck_user_reports_status",
        ),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_reports_workspace_id", "user_reports", ["workspace_id"])
    op.create_index("ix_user_reports_user_id", "user_reports", ["user_id"])
    op.create_index("ix_user_reports_status", "user_reports", ["status"])
    op.create_index("ix_user_reports_created_at", "user_reports", ["created_at"])


def downgrade() -> None:
    op.drop_table("user_reports")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")

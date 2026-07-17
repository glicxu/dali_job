"""add durable managed operations

Revision ID: 20260715_0021
Revises: 20260715_0020
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260715_0021"
down_revision = "20260715_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "managed_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_current", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_message", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model_or_actor", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_managed_operations_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            "operation_type",
            "idempotency_key",
            name="uq_managed_operations_owner_idempotency",
        ),
    )
    op.create_index("ix_managed_operations_operation_type", "managed_operations", ["operation_type"], unique=False)
    op.create_index("ix_managed_operations_provider", "managed_operations", ["provider"], unique=False)
    op.create_index("ix_managed_operations_status", "managed_operations", ["status"], unique=False)
    op.create_index("ix_managed_operations_user_id", "managed_operations", ["user_id"], unique=False)
    op.create_index("ix_managed_operations_workspace_id", "managed_operations", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_managed_operations_workspace_id", table_name="managed_operations")
    op.drop_index("ix_managed_operations_user_id", table_name="managed_operations")
    op.drop_index("ix_managed_operations_status", table_name="managed_operations")
    op.drop_index("ix_managed_operations_provider", table_name="managed_operations")
    op.drop_index("ix_managed_operations_operation_type", table_name="managed_operations")
    op.drop_table("managed_operations")

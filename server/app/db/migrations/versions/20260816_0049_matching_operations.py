"""add durable three-stage matching operations

Revision ID: 20260816_0049
Revises: 20260816_0048
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0049"
down_revision = "20260816_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "matching_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("current_stage", sa.String(40), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("match_result_id", sa.Integer(), nullable=True),
        sa.Column("lease_owner", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'retryable_failure', 'terminal_failure', 'cancelled')",
            name="ck_matching_operations_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_result_id"], ["matching_match_results.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", "idempotency_key", name="uq_matching_operations_owner_idempotency"),
    )
    op.create_index("ix_matching_operations_public", "matching_operations", ["public_id"], unique=True)
    op.create_index("ix_matching_operations_owner", "matching_operations", ["workspace_id", "user_id"])
    op.create_index("ix_matching_operations_status", "matching_operations", ["status"])
    op.create_index("ix_matching_operations_lease", "matching_operations", ["lease_expires_at"])

    op.create_table(
        "matching_operation_stages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("matching_operation_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("input_artifact_ids", sa.JSON(), nullable=False),
        sa.Column("output_artifact_id", sa.String(64), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=True),
        sa.Column("provider_usage", sa.JSON(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'retryable_failure', 'terminal_failure')",
            name="ck_matching_operation_stages_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_matching_operation_stages_attempts"),
        sa.CheckConstraint("max_attempts >= 1", name="ck_matching_operation_stages_max_attempts"),
        sa.ForeignKeyConstraint(["matching_operation_id"], ["matching_operations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("matching_operation_id", "stage", name="uq_matching_operation_stage"),
    )
    op.create_index("ix_matching_operation_stages_operation", "matching_operation_stages", ["matching_operation_id"])
    op.create_index("ix_matching_operation_stages_status", "matching_operation_stages", ["status"])


def downgrade() -> None:
    op.drop_index("ix_matching_operation_stages_status", table_name="matching_operation_stages")
    op.drop_index("ix_matching_operation_stages_operation", table_name="matching_operation_stages")
    op.drop_table("matching_operation_stages")
    op.drop_index("ix_matching_operations_lease", table_name="matching_operations")
    op.drop_index("ix_matching_operations_status", table_name="matching_operations")
    op.drop_index("ix_matching_operations_owner", table_name="matching_operations")
    op.drop_index("ix_matching_operations_public", table_name="matching_operations")
    op.drop_table("matching_operations")

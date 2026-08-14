"""add rotating mobile bearer sessions

Revision ID: 20260814_0034
Revises: 20260814_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0034"
down_revision = "20260814_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("session_type", sa.String(length=20), server_default="browser", nullable=False),
    )
    op.add_column("auth_sessions", sa.Column("token_family_id", sa.String(length=64), nullable=True))
    op.add_column("auth_sessions", sa.Column("device_label", sa.String(length=120), nullable=True))
    op.add_column(
        "auth_sessions", sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_auth_sessions_type", "auth_sessions", "session_type IN ('browser', 'mobile')"
    )
    op.create_index("ix_auth_sessions_session_type", "auth_sessions", ["session_type"])
    op.create_index("ix_auth_sessions_token_family_id", "auth_sessions", ["token_family_id"])
    op.create_index("ix_auth_sessions_refresh_expires_at", "auth_sessions", ["refresh_expires_at"])

    op.create_table(
        "mobile_refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replacement_token_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replacement_token_id"], ["mobile_refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_mobile_refresh_tokens_token_hash"),
    )
    op.create_index("ix_mobile_refresh_tokens_session_id", "mobile_refresh_tokens", ["session_id"])
    op.create_index("ix_mobile_refresh_tokens_token_hash", "mobile_refresh_tokens", ["token_hash"])
    op.create_index("ix_mobile_refresh_tokens_expires_at", "mobile_refresh_tokens", ["expires_at"])
    op.create_index("ix_mobile_refresh_tokens_consumed_at", "mobile_refresh_tokens", ["consumed_at"])
    op.create_index("ix_mobile_refresh_tokens_revoked_at", "mobile_refresh_tokens", ["revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_mobile_refresh_tokens_revoked_at", table_name="mobile_refresh_tokens")
    op.drop_index("ix_mobile_refresh_tokens_consumed_at", table_name="mobile_refresh_tokens")
    op.drop_index("ix_mobile_refresh_tokens_expires_at", table_name="mobile_refresh_tokens")
    op.drop_index("ix_mobile_refresh_tokens_token_hash", table_name="mobile_refresh_tokens")
    op.drop_index("ix_mobile_refresh_tokens_session_id", table_name="mobile_refresh_tokens")
    op.drop_table("mobile_refresh_tokens")
    op.drop_index("ix_auth_sessions_refresh_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_family_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_session_type", table_name="auth_sessions")
    op.drop_constraint("ck_auth_sessions_type", "auth_sessions", type_="check")
    op.drop_column("auth_sessions", "refresh_expires_at")
    op.drop_column("auth_sessions", "device_label")
    op.drop_column("auth_sessions", "token_family_id")
    op.drop_column("auth_sessions", "session_type")

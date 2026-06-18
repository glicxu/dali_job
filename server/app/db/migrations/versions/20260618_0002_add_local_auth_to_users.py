"""add local authentication fields to users

Revision ID: 20260618_0002
Revises: 20260617_0001
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa

revision = "20260618_0002"
down_revision = "20260617_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(length=32), nullable=False, server_default="dalijob"),
    )
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "is_active")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "password_hash")

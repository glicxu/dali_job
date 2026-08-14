"""add notification delivery leases

Revision ID: 20260814_0035
Revises: 20260814_0034
"""

from alembic import op
import sqlalchemy as sa


revision = "20260814_0035"
down_revision = "20260814_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_notification_deliveries_status",
        "notification_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_deliveries_status",
        "notification_deliveries",
        "status IN ('pending', 'sending', 'sent', 'failed', 'suppressed', 'read')",
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_deliveries_lease_owner",
        "notification_deliveries",
        ["lease_owner"],
    )
    op.create_index(
        "ix_notification_deliveries_lease_expires_at",
        "notification_deliveries",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_lease_expires_at",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_lease_owner",
        table_name="notification_deliveries",
    )
    op.drop_column("notification_deliveries", "lease_expires_at")
    op.drop_column("notification_deliveries", "lease_owner")
    op.drop_constraint(
        "ck_notification_deliveries_status",
        "notification_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_notification_deliveries_status",
        "notification_deliveries",
        "status IN ('pending', 'sent', 'failed', 'suppressed', 'read')",
    )

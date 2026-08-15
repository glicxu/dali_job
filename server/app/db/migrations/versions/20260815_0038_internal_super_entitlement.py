"""add internal super automation entitlement

Revision ID: 20260815_0038
Revises: 20260814_0037
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0038"
down_revision = "20260814_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_subscriptions") as batch_op:
        batch_op.drop_constraint("ck_user_subscriptions_tier", type_="check")
        batch_op.create_check_constraint(
            "ck_user_subscriptions_tier",
            "tier_code IN ('free', 'starter', 'plus', 'super')",
        )


def downgrade() -> None:
    # Downgrade is deliberately fail-closed: operators must remove every
    # internal assignment before restoring the narrower database constraint.
    op.execute(sa.text("UPDATE user_subscriptions SET tier_code = 'free' WHERE tier_code = 'super'"))
    with op.batch_alter_table("user_subscriptions") as batch_op:
        batch_op.drop_constraint("ck_user_subscriptions_tier", type_="check")
        batch_op.create_check_constraint(
            "ck_user_subscriptions_tier",
            "tier_code IN ('free', 'starter', 'plus')",
        )

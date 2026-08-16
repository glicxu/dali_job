"""generalize matching operations for profile extraction

Revision ID: 20260816_0051
Revises: 20260816_0050
"""

from alembic import op
import sqlalchemy as sa


revision = "20260816_0051"
down_revision = "20260816_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matching_operations",
        sa.Column("operation_type", sa.String(40), nullable=False, server_default="match"),
    )
    op.alter_column("matching_operations", "operation_type", server_default=None)
    op.create_index("ix_matching_operations_type", "matching_operations", ["operation_type"])


def downgrade() -> None:
    op.drop_index("ix_matching_operations_type", table_name="matching_operations")
    op.drop_column("matching_operations", "operation_type")

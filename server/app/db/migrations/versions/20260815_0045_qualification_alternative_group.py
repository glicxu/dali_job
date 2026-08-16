"""add qualification alternative group reference

Revision ID: 20260815_0045
Revises: 20260815_0044
"""

from alembic import op
import sqlalchemy as sa


revision = "20260815_0045"
down_revision = "20260815_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table_name = "matching_requirement_assessments"
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "alternative_group_refs" not in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("alternative_group_refs", sa.JSON(), nullable=True))


def downgrade() -> None:
    table_name = "matching_requirement_assessments"
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if "alternative_group_refs" in columns:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_column("alternative_group_refs")

"""drop legacy profiles table

Revision ID: 20260623_0011
Revises: 20260623_0010
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260623_0011"
down_revision = "20260623_0010"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if _table_exists("profiles"):
        if _table_exists("resume_profiles"):
            op.get_bind().execute(
                sa.text(
                    """
                    INSERT INTO resume_profiles (
                        workspace_id,
                        user_id,
                        title,
                        resume_data,
                        is_favorite,
                        created_at,
                        updated_at
                    )
                    SELECT
                        p.workspace_id,
                        p.user_id,
                        'Legacy Resume',
                        p.resume_data,
                        1,
                        p.created_at,
                        p.updated_at
                    FROM profiles p
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM resume_profiles rp
                        WHERE rp.workspace_id = p.workspace_id
                          AND rp.user_id = p.user_id
                          AND rp.deleted_at IS NULL
                    )
                    """
                )
            )
        if _index_exists("profiles", "ix_profiles_workspace_id"):
            op.drop_index("ix_profiles_workspace_id", table_name="profiles")
        if _index_exists("profiles", "ix_profiles_user_id"):
            op.drop_index("ix_profiles_user_id", table_name="profiles")
        op.drop_table("profiles")


def downgrade() -> None:
    # The legacy profiles table is intentionally not restored.
    pass

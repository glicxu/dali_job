"""rename resume favorite to default

Revision ID: 20260707_0015
Revises: 20260705_0014
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260707_0015"
down_revision = "20260705_0014"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _normalize_defaults() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, workspace_id, user_id, is_default
            FROM resume_profiles
            WHERE deleted_at IS NULL
            ORDER BY workspace_id, user_id, is_default DESC, updated_at DESC, id DESC
            """
        )
    ).mappings()

    seen: set[tuple[int, int]] = set()
    for row in rows:
        key = (row["workspace_id"], row["user_id"])
        should_be_default = key not in seen
        seen.add(key)
        bind.execute(
            sa.text("UPDATE resume_profiles SET is_default = :is_default WHERE id = :id"),
            {"is_default": should_be_default, "id": row["id"]},
        )


def upgrade() -> None:
    if not _table_exists("resume_profiles"):
        return

    if _index_exists("resume_profiles", "ix_resume_profiles_favorite_sort"):
        op.drop_index("ix_resume_profiles_favorite_sort", table_name="resume_profiles")

    if not _column_exists("resume_profiles", "is_default"):
        if _column_exists("resume_profiles", "is_favorite"):
            op.alter_column(
                "resume_profiles",
                "is_favorite",
                new_column_name="is_default",
                existing_type=sa.Boolean(),
                existing_nullable=False,
                existing_server_default=sa.false(),
            )
        else:
            op.add_column(
                "resume_profiles",
                sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
            )

    _normalize_defaults()

    if not _index_exists("resume_profiles", "ix_resume_profiles_default_sort"):
        op.create_index(
            "ix_resume_profiles_default_sort",
            "resume_profiles",
            ["workspace_id", "user_id", "is_default", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    if not _table_exists("resume_profiles"):
        return

    if _index_exists("resume_profiles", "ix_resume_profiles_default_sort"):
        op.drop_index("ix_resume_profiles_default_sort", table_name="resume_profiles")

    if not _column_exists("resume_profiles", "is_favorite") and _column_exists("resume_profiles", "is_default"):
        op.alter_column(
            "resume_profiles",
            "is_default",
            new_column_name="is_favorite",
            existing_type=sa.Boolean(),
            existing_nullable=False,
            existing_server_default=sa.false(),
        )

    if not _index_exists("resume_profiles", "ix_resume_profiles_favorite_sort"):
        op.create_index(
            "ix_resume_profiles_favorite_sort",
            "resume_profiles",
            ["workspace_id", "user_id", "is_favorite", "updated_at"],
            unique=False,
        )

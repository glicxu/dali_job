"""create user edited jobs

Revision ID: 20260705_0014
Revises: 20260630_0013
Create Date: 2026-07-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260705_0014"
down_revision = "20260630_0013"
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


def _foreign_key_name(table_name: str, column_name: str) -> str | None:
    inspector = inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys(table_name):
        if foreign_key.get("constrained_columns") == [column_name]:
            return foreign_key.get("name")
    return None


def _create_user_edited_jobs() -> None:
    if _table_exists("user_edited_jobs"):
        return
    op.create_table(
        "user_edited_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("raw_description_text", sa.Text(), nullable=False),
        sa.Column("job_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_edited_jobs_user_id", "user_edited_jobs", ["user_id"], unique=False)
    op.create_index("ix_user_edited_jobs_workspace_id", "user_edited_jobs", ["workspace_id"], unique=False)


def _add_user_edited_fk() -> None:
    if not _column_exists("user_saved_jobs", "user_edited_job_id"):
        op.add_column("user_saved_jobs", sa.Column("user_edited_job_id", sa.Integer(), nullable=True))
    if not _index_exists("user_saved_jobs", "ix_user_saved_jobs_user_edited_job_id"):
        op.create_index(
            "ix_user_saved_jobs_user_edited_job_id",
            "user_saved_jobs",
            ["user_edited_job_id"],
            unique=False,
        )
    if _foreign_key_name("user_saved_jobs", "user_edited_job_id") is None:
        op.create_foreign_key(
            "fk_user_saved_jobs_user_edited_job_id_user_edited_jobs",
            "user_saved_jobs",
            "user_edited_jobs",
            ["user_edited_job_id"],
            ["id"],
            ondelete="SET NULL",
        )


def _make_cache_fk_nullable() -> None:
    foreign_key_name = _foreign_key_name("user_saved_jobs", "jobs_cache_id")
    if foreign_key_name:
        op.drop_constraint(foreign_key_name, "user_saved_jobs", type_="foreignkey")
    op.alter_column("user_saved_jobs", "jobs_cache_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        "fk_user_saved_jobs_jobs_cache_id_jobs_cache",
        "user_saved_jobs",
        "jobs_cache",
        ["jobs_cache_id"],
        ["id"],
        ondelete="SET NULL",
    )


def upgrade() -> None:
    _create_user_edited_jobs()
    _add_user_edited_fk()
    _make_cache_fk_nullable()


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for user edited jobs.")

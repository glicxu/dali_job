"""rename user jobs and keep job details only in cache

Revision ID: 20260626_0012
Revises: 20260623_0011
Create Date: 2026-06-26
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20260626_0012"
down_revision = "20260623_0011"
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


def _hash_source_url(source_url: str | None) -> str | None:
    if not source_url:
        return None
    return sha256(source_url.strip().encode("utf-8")).hexdigest()


def _backfill_missing_cache_rows() -> None:
    bind = op.get_bind()
    if not _table_exists("user_jobs"):
        return
    rows = bind.execute(
        text(
            """
            SELECT id, title, company, source_url, raw_description_text, job_data, created_at, updated_at
            FROM user_jobs
            WHERE jobs_cache_id IS NULL
            """
        )
    ).mappings()
    now = datetime.now(timezone.utc)
    for row in rows:
        result = bind.execute(
            text(
                """
                INSERT INTO jobs_cache
                    (title, company, source_url, source_url_hash, raw_description_text, job_data, created_at, updated_at, deleted_at)
                VALUES
                    (:title, :company, :source_url, :source_url_hash, :raw_description_text, :job_data, :created_at, :updated_at, NULL)
                """
            ),
            {
                "title": row["title"] or "",
                "company": row["company"] or "",
                "source_url": row["source_url"],
                "source_url_hash": _hash_source_url(row["source_url"]),
                "raw_description_text": row["raw_description_text"] or "",
                "job_data": row["job_data"],
                "created_at": row["created_at"] or now,
                "updated_at": row["updated_at"] or now,
            },
        )
        cache_id = result.lastrowid
        bind.execute(
            text("UPDATE user_jobs SET jobs_cache_id = :cache_id WHERE id = :user_job_id"),
            {"cache_id": cache_id, "user_job_id": row["id"]},
        )


def upgrade() -> None:
    if _table_exists("user_jobs") and not _table_exists("user_saved_jobs"):
        _backfill_missing_cache_rows()
        op.rename_table("user_jobs", "user_saved_jobs")

    if _table_exists("user_saved_jobs"):
        for column_name in ("title", "company", "source_url", "raw_description_text", "job_data", "saved_at"):
            if _column_exists("user_saved_jobs", column_name):
                op.drop_column("user_saved_jobs", column_name)

        if _index_exists("user_saved_jobs", "ix_user_jobs_jobs_cache_id"):
            op.drop_index("ix_user_jobs_jobs_cache_id", table_name="user_saved_jobs")
        if _index_exists("user_saved_jobs", "ix_user_jobs_user_id"):
            op.drop_index("ix_user_jobs_user_id", table_name="user_saved_jobs")
        if _index_exists("user_saved_jobs", "ix_user_jobs_workspace_id"):
            op.drop_index("ix_user_jobs_workspace_id", table_name="user_saved_jobs")

        if not _index_exists("user_saved_jobs", "ix_user_saved_jobs_jobs_cache_id"):
            op.create_index("ix_user_saved_jobs_jobs_cache_id", "user_saved_jobs", ["jobs_cache_id"], unique=False)
        if not _index_exists("user_saved_jobs", "ix_user_saved_jobs_user_id"):
            op.create_index("ix_user_saved_jobs_user_id", "user_saved_jobs", ["user_id"], unique=False)
        if not _index_exists("user_saved_jobs", "ix_user_saved_jobs_workspace_id"):
            op.create_index("ix_user_saved_jobs_workspace_id", "user_saved_jobs", ["workspace_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for the user_saved_jobs consolidation.")

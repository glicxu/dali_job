"""make jobs_cache source url hash unique

Revision ID: 20260713_0016
Revises: 20260707_0015
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections import defaultdict

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260713_0016"
down_revision = "20260707_0015"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _index_is_unique(table_name: str, index_name: str) -> bool:
    inspector = inspect(op.get_bind())
    for index in inspector.get_indexes(table_name):
        if index["name"] == index_name:
            return bool(index.get("unique"))
    return False


def _collapse_duplicate_cache_hashes() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, source_url_hash
            FROM jobs_cache
            WHERE source_url_hash IS NOT NULL
            ORDER BY id
            """
        )
    ).mappings()
    ids_by_hash: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        ids_by_hash[row["source_url_hash"]].append(row["id"])

    for cache_ids in ids_by_hash.values():
        if len(cache_ids) < 2:
            continue
        keeper_id = cache_ids[0]
        duplicate_ids = cache_ids[1:]
        for duplicate_id in duplicate_ids:
            bind.execute(
                sa.text(
                    """
                    UPDATE user_saved_jobs
                    SET jobs_cache_id = :keeper_id
                    WHERE jobs_cache_id = :duplicate_id
                    """
                ),
                {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE job_resume_matches
                    SET jobs_cache_id = :keeper_id
                    WHERE jobs_cache_id = :duplicate_id
                    """
                ),
                {"keeper_id": keeper_id, "duplicate_id": duplicate_id},
            )
            bind.execute(
                sa.text(
                    """
                    UPDATE jobs_cache
                    SET source_url_hash = NULL,
                        deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP)
                    WHERE id = :duplicate_id
                    """
                ),
                {"duplicate_id": duplicate_id},
            )


def upgrade() -> None:
    _collapse_duplicate_cache_hashes()
    if _index_exists("jobs_cache", "ix_jobs_cache_source_url_hash"):
        if _index_is_unique("jobs_cache", "ix_jobs_cache_source_url_hash"):
            return
        op.drop_index("ix_jobs_cache_source_url_hash", table_name="jobs_cache")
    op.create_index("ix_jobs_cache_source_url_hash", "jobs_cache", ["source_url_hash"], unique=True)


def downgrade() -> None:
    if _index_exists("jobs_cache", "ix_jobs_cache_source_url_hash"):
        op.drop_index("ix_jobs_cache_source_url_hash", table_name="jobs_cache")
    op.create_index("ix_jobs_cache_source_url_hash", "jobs_cache", ["source_url_hash"], unique=False)

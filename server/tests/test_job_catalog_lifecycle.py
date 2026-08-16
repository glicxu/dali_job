from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.jobs import repository
from app.modules.jobs.catalog_lifecycle import close_job, expire_due_jobs
from app.modules.jobs.models import JobCache


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def test_expiration_is_bounded_and_preserves_job_history() -> None:
    factory = _factory()
    with factory() as db:
        jobs = [
            JobCache(
                title=f"Job {index}",
                raw_description_text="Description",
                lifecycle_state="active",
                last_seen_at=NOW - timedelta(days=31),
                expires_at=NOW - timedelta(days=1),
            )
            for index in range(3)
        ]
        db.add_all(jobs)
        db.commit()

        first = expire_due_jobs(db, now=NOW, limit=2)
        db.commit()
        assert first.expired == 2
        assert first.remaining_due is True
        assert db.query(JobCache).count() == 3
        assert db.query(JobCache).filter(JobCache.lifecycle_state == "expired").count() == 2

        second = expire_due_jobs(db, now=NOW, limit=2)
        db.commit()
        assert second.expired == 1
        assert second.remaining_due is False
        assert all(job.deleted_at is None for job in db.query(JobCache).all())


def test_reimport_reactivates_expired_job_and_extends_ttl() -> None:
    factory = _factory()
    with factory() as db:
        job = repository.get_or_create_cache_job(
            db,
            source_url="https://example.com/jobs/1",
            raw_description_text="Build APIs.",
            cache_write_source="source_extraction",
            ttl_days=10,
        )
        job.lifecycle_state = "expired"
        job.expired_at = NOW
        job.expiration_reason = "time_bound_ttl"
        job.expires_at = NOW - timedelta(days=1)
        db.flush()

        seen_again = repository.get_or_create_cache_job(
            db,
            source_url="https://example.com/jobs/1",
            raw_description_text="Build APIs.",
            cache_write_source="source_extraction",
            ttl_days=10,
        )

        assert seen_again.id == job.id
        assert seen_again.lifecycle_state == "active"
        assert seen_again.expired_at is None
        assert seen_again.expiration_reason is None
        assert seen_again.expires_at > seen_again.last_seen_at


def test_source_confirmed_close_is_distinct_from_ttl_expiration() -> None:
    factory = _factory()
    with factory() as db:
        job = JobCache(
            title="Closed job",
            raw_description_text="Description",
            lifecycle_state="active",
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=30),
        )
        db.add(job)
        db.flush()
        close_job(db, job, now=NOW)
        assert job.lifecycle_state == "closed"
        assert job.expiration_reason == "source_confirmed_closed"
        assert job.deleted_at is None

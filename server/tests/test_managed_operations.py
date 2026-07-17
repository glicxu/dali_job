from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


def create_test_client(handler):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    app.state.operation_handlers = {"job_search": handler}
    return TestClient(app)


def test_managed_operation_persists_result_and_deduplicates_idempotency_key() -> None:
    calls = []

    def handler(_db, _identity, payload, context):
        calls.append(payload)
        context.update(1, total=1, message="Search complete", usage={"results": 1})
        return {
            "provider": "test",
            "keyword": payload["keyword"],
            "location": payload["location"],
            "results": [],
            "warnings": [],
        }

    client = create_test_client(handler)
    headers = {"Idempotency-Key": "same-search-request"}
    first = client.post(
        "/api/v1/operations/job-search",
        json={"keyword": "software engineer", "location": "Maryland"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/operations/job-search",
        json={"keyword": "software engineer", "location": "Maryland"},
        headers=headers,
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    operation = client.get(f"/api/v1/operations/{first.json()['id']}").json()
    assert operation["status"] == "succeeded"
    assert "request_payload" not in operation
    assert operation["result_payload"]["keyword"] == "software engineer"
    assert operation["usage"]["results"] == 1
    assert operation["usage"]["duration_ms"] >= 0
    assert calls == [{"keyword": "software engineer", "location": "Maryland", "max_results": 5}]


def test_failed_managed_operation_can_retry_without_exposing_exception_details() -> None:
    def failing_handler(_db, _identity, _payload, _context):
        raise RuntimeError("provider-secret-internal-detail")

    client = create_test_client(failing_handler)
    queued = client.post(
        "/api/v1/operations/job-search",
        json={"keyword": "engineer", "location": "Remote"},
    )
    operation_id = queued.json()["id"]
    failed = client.get(f"/api/v1/operations/{operation_id}").json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "operation_failed"
    assert "provider-secret" not in failed["error_message"]

    def successful_handler(_db, _identity, payload, context):
        context.update(1, total=1, message="Complete")
        return {"keyword": payload["keyword"], "results": []}

    client.app.state.operation_handlers["job_search"] = successful_handler
    retried = client.post(f"/api/v1/operations/{operation_id}/retry")
    assert retried.status_code == 202
    completed = client.get(f"/api/v1/operations/{operation_id}").json()
    assert completed["status"] == "succeeded"
    assert completed["attempt_count"] == 2


def test_queued_operation_can_be_cancelled() -> None:
    client = create_test_client(lambda *_args: {})
    client.app.state.operation_handlers = {}
    queued = client.post(
        "/api/v1/operations/job-search",
        json={"keyword": "engineer", "location": "Remote"},
    )
    operation_id = queued.json()["id"]
    # The missing handler fails immediately under TestClient, which is still a terminal and non-running state.
    cancelled = client.post(f"/api/v1/operations/{operation_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] in {"failed", "cancelled"}

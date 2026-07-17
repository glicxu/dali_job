from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.applications.models import Application, ApplicationDocument, ApplicationStatusHistory
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents.models import Document, DocumentVersion


def create_test_client(*, multiple_users: bool = False) -> tuple[TestClient, sessionmaker]:
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
    if multiple_users:
        def identity_for_header(x_test_user: str = Header()) -> AuthenticatedIdentity:
            return AuthenticatedIdentity(
                external_user_id=x_test_user,
                email=f"{x_test_user}@example.com",
                display_name=x_test_user,
                timezone="America/New_York",
                provider="test",
            )
        app.dependency_overrides[get_current_identity] = identity_for_header
    return TestClient(app), session_factory


def job_payload(index: int) -> dict:
    return {
        "title": f"Engineer {index}",
        "company": "Example",
        "source_url": f"https://careers.example.com/jobs/{index}",
        "raw_description_text": "Build software.",
        "job_data": {
            "title": f"Engineer {index}",
            "company": "Example",
            "summary": "Build software.",
            "responsibilities": [],
            "required_skills": [],
            "preferred_skills": [],
            "required_experience": [],
            "preferred_experience": [],
            "education": [],
            "certifications": [],
            "tools_and_technologies": [],
            "keywords": [],
            "seniority_level": "",
            "employment_type": "",
            "security_clearance": "",
            "work_location": "",
            "salary_range": "",
            "application_deadline": "",
        },
    }


def test_outcome_analytics_formulas_versions_and_date_range() -> None:
    client, session_factory = create_test_client()
    applied_at = datetime(2026, 1, 10, 15, tzinfo=timezone.utc)
    application_ids: list[int] = []
    for index in range(4):
        job = client.post("/api/v1/jobs", json=job_payload(index))
        assert job.status_code == 200
        application = client.post(
            "/api/v1/applications",
            json={
                "user_job_id": job.json()["id"],
                "status": "applied",
                "applied_at": applied_at.isoformat(),
            },
        )
        assert application.status_code == 200
        application_ids.append(application.json()["id"])

    with session_factory() as db:
        applications = {
            row.id: row for row in db.scalars(select(Application).where(Application.id.in_(application_ids)))
        }
        status_events = [
            (application_ids[0], "interviewing", 48),
            (application_ids[0], "offer", 240),
            (application_ids[1], "rejected", 24),
            (application_ids[2], "withdrawn", 72),
        ]
        for application_id, status, hours in status_events:
            db.add(
                ApplicationStatusHistory(
                    application_id=application_id,
                    from_status="applied",
                    to_status=status,
                    source="user",
                    created_at=applied_at + timedelta(hours=hours),
                )
            )
        applications[application_ids[0]].status = "offer"
        applications[application_ids[1]].status = "rejected"
        applications[application_ids[1]].active_duplicate_guard = None
        applications[application_ids[2]].status = "withdrawn"
        applications[application_ids[2]].active_duplicate_guard = None

        owner = applications[application_ids[0]]
        document = Document(
            workspace_id=owner.workspace_id,
            user_id=owner.user_id,
            title="Backend Resume",
            document_type="resume",
        )
        db.add(document)
        db.flush()
        version = DocumentVersion(
            document_id=document.id,
            version_number=1,
            file_name="resume.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256="a" * 64,
            storage_path="test/resume.pdf",
            created_at=applied_at - timedelta(days=1),
        )
        db.add(version)
        db.flush()
        for application_id in application_ids:
            db.add(
                ApplicationDocument(
                    application_id=application_id,
                    document_version_id=version.id,
                    purpose="resume",
                    created_at=applied_at - timedelta(hours=1),
                )
            )
        db.commit()

    response = client.get("/api/v1/analytics/summary?start_date=2026-01-01&end_date=2026-01-31")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metric_version"] == "outcome-analytics-v1"
    assert payload["submitted_application_count"] == 4
    rates = {item["outcome"]: item for item in payload["rates"]}
    assert rates["response"]["percentage"] == 50.0
    assert rates["interview"]["percentage"] == 25.0
    assert rates["offer"]["percentage"] == 25.0
    assert rates["rejected"]["percentage"] == 25.0
    assert rates["withdrawn"]["percentage"] == 25.0
    durations = {item["metric"]: item for item in payload["durations"]}
    assert durations["time_to_first_response"]["average_hours"] == 36.0
    assert durations["time_to_first_interview"]["median_hours"] == 48.0
    assert payload["source_performance"][0]["label"] == "careers.example.com"
    assert payload["source_performance"][0]["sample_size"] == 4
    assert payload["resume_version_performance"][0]["label"] == "Backend Resume v1"
    assert payload["resume_version_performance"][0]["sample_size"] == 4
    assert payload["resume_version_performance"][0]["small_sample"] is True
    assert payload["data_quality"]["missing_resume_version"] == 0
    assert payload["definitions"]

    outside_range = client.get("/api/v1/analytics/summary?start_date=2026-02-01")
    assert outside_range.status_code == 200
    assert outside_range.json()["submitted_application_count"] == 0


def test_analytics_rejects_invalid_range_and_is_owner_scoped() -> None:
    client, _ = create_test_client(multiple_users=True)
    first = {"X-Test-User": "first"}
    second = {"X-Test-User": "second"}
    job = client.post("/api/v1/jobs", json=job_payload(9), headers=first)
    application = client.post(
        "/api/v1/applications",
        json={"user_job_id": job.json()["id"], "status": "applied", "applied_at": "2026-01-10T15:00:00Z"},
        headers=first,
    )
    assert application.status_code == 200
    first_summary = client.get("/api/v1/analytics/summary", headers=first)
    second_summary = client.get("/api/v1/analytics/summary", headers=second)
    assert first_summary.json()["submitted_application_count"] == 1
    assert second_summary.json()["submitted_application_count"] == 0

    invalid = client.get(
        "/api/v1/analytics/summary?start_date=2026-02-01&end_date=2026-01-01",
        headers=first,
    )
    assert invalid.status_code == 422

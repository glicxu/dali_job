from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app


def create_test_client() -> TestClient:
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
    return TestClient(app)


def create_saved_job(client: TestClient) -> int:
    response = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Example Co",
            "raw_description_text": "Build APIs using Python and PostgreSQL for customer workflows.",
            "job_data": {
                "title": "Backend Engineer",
                "company": "Example Co",
                "summary": "Build backend services.",
                "responsibilities": ["Build APIs using Python."],
                "required_skills": ["Python"],
                "preferred_skills": [],
                "required_experience": [],
                "preferred_experience": [],
                "education": [],
                "certifications": [],
                "tools_and_technologies": ["Python"],
                "keywords": ["backend"],
                "seniority_level": "",
                "employment_type": "",
                "security_clearance": "",
                "work_location": "Remote",
                "salary_range": "",
                "application_deadline": "",
            },
        },
    )
    assert response.status_code == 200
    return response.json()["id"]


def test_application_tracking_crud_status_notes_and_tasks() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)

    create_response = client.post(
        "/api/v1/applications",
        json={
            "user_job_id": user_job_id,
            "status": "interested",
            "priority": "high",
            "match_score": 8,
            "next_action_label": "Apply this week",
            "notes": "Strong role.",
        },
    )

    assert create_response.status_code == 200
    application = create_response.json()
    application_id = application["id"]
    assert application["job"]["title"] == "Backend Engineer"
    assert application["status"] == "interested"
    assert application["status_history"][0]["to_status"] == "interested"

    list_response = client.get("/api/v1/applications")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == application_id

    update_response = client.patch(
        f"/api/v1/applications/{application_id}",
        json={"priority": "normal", "salary_notes": "$120k target"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["priority"] == "normal"
    assert update_response.json()["salary_notes"] == "$120k target"

    status_response = client.post(
        f"/api/v1/applications/{application_id}/status",
        json={"status": "applied", "reason": "Submitted through portal"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "applied"
    assert status_response.json()["applied_at"] is not None

    note_response = client.post(
        f"/api/v1/applications/{application_id}/notes",
        json={"body": "Follow up with recruiter next week."},
    )
    assert note_response.status_code == 200
    assert note_response.json()["body"] == "Follow up with recruiter next week."

    task_response = client.post(
        f"/api/v1/applications/{application_id}/tasks",
        json={"title": "Prepare portfolio examples"},
    )
    assert task_response.status_code == 200
    task_id = task_response.json()["id"]

    complete_response = client.patch(
        f"/api/v1/applications/{application_id}/tasks/{task_id}",
        json={"completed": True},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed_at"] is not None

    detail_response = client.get(f"/api/v1/applications/{application_id}")
    detail = detail_response.json()
    assert detail_response.status_code == 200
    assert detail["notes_list"][0]["body"] == "Follow up with recruiter next week."
    assert detail["tasks"][0]["title"] == "Prepare portfolio examples"
    assert any(event["event_type"] == "status_changed" for event in detail["events"])


def test_application_requires_existing_saved_job() -> None:
    client = create_test_client()

    response = client.post("/api/v1/applications", json={"user_job_id": 999999})

    assert response.status_code == 404
    assert response.json()["detail"] == "Saved job not found."

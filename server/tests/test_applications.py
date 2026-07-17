from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity


def create_test_client(tmp_path=None) -> TestClient:
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
    if tmp_path is not None:
        app.state.runtime = app.state.runtime.__class__(
            **{**app.state.runtime.__dict__, "document_storage_dir": str(tmp_path)}
        )
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app)


def create_multi_user_test_client() -> TestClient:
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

    def override_identity(x_test_user: str = Header()) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            external_user_id=x_test_user,
            email=f"{x_test_user}@example.com",
            display_name=x_test_user,
            provider="test",
        )

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_identity] = override_identity
    return TestClient(app)


def create_saved_job(client: TestClient, headers: dict[str, str] | None = None) -> int:
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
        headers=headers,
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


def test_saved_job_delete_is_blocked_while_application_references_it_but_archive_is_allowed() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    application = client.post("/api/v1/applications", json={"user_job_id": user_job_id})
    assert application.status_code == 200

    delete_response = client.delete(f"/api/v1/jobs/{user_job_id}")
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"]["dependencies"][0]["dependency_type"] == "application"

    archive_response = client.post(f"/api/v1/jobs/{user_job_id}/archive")
    assert archive_response.status_code == 204
    assert client.get("/api/v1/jobs").json() == []
    archived_jobs = client.get("/api/v1/jobs?include_archived=true").json()
    assert archived_jobs[0]["id"] == user_job_id
    assert archived_jobs[0]["archived_at"] is not None

    restore_response = client.post(f"/api/v1/jobs/{user_job_id}/restore")
    assert restore_response.status_code == 204
    assert client.get("/api/v1/jobs").json()[0]["id"] == user_job_id


def test_duplicate_active_application_requires_explicit_confirmation() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    first = client.post("/api/v1/applications", json={"user_job_id": user_job_id})
    assert first.status_code == 200

    duplicate = client.post("/api/v1/applications", json={"user_job_id": user_job_id})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["code"] == "duplicate_active_application"
    assert duplicate.json()["detail"]["existing_application_id"] == first.json()["id"]

    confirmed = client.post(
        "/api/v1/applications",
        json={"user_job_id": user_job_id, "confirm_duplicate": True},
    )
    assert confirmed.status_code == 200
    assert len(client.get("/api/v1/applications").json()) == 2


def test_terminal_application_does_not_block_a_new_application() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    first = client.post("/api/v1/applications", json={"user_job_id": user_job_id}).json()
    withdrawn = client.post(
        f"/api/v1/applications/{first['id']}/status",
        json={"status": "withdrawn", "reason": "Role no longer fits"},
    )
    assert withdrawn.status_code == 200

    second = client.post("/api/v1/applications", json={"user_job_id": user_job_id})
    assert second.status_code == 200


def test_status_transitions_are_server_enforced_and_events_include_actor() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    application = client.post("/api/v1/applications", json={"user_job_id": user_job_id}).json()
    application_id = application["id"]

    invalid = client.post(
        f"/api/v1/applications/{application_id}/status",
        json={"status": "offer"},
    )
    assert invalid.status_code == 409
    assert invalid.json()["detail"]["code"] == "invalid_application_transition"

    for next_status in ("applied", "interviewing", "offer", "accepted"):
        response = client.post(
            f"/api/v1/applications/{application_id}/status",
            json={"status": next_status},
        )
        assert response.status_code == 200

    terminal_change = client.post(
        f"/api/v1/applications/{application_id}/status",
        json={"status": "rejected"},
    )
    assert terminal_change.status_code == 409

    detail = client.get(f"/api/v1/applications/{application_id}").json()
    status_events = [event for event in detail["events"] if event["event_type"] == "status_changed"]
    assert status_events
    assert all(event["payload"]["actor_external_user_id"] for event in status_events)
    assert detail["allowed_status_transitions"] == []


def test_stage_filter_and_archive_restore_are_separate_from_status() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    created = client.post(
        "/api/v1/applications",
        json={"user_job_id": user_job_id, "stage": "recruiter_contact"},
    ).json()
    application_id = created["id"]

    filtered = client.get("/api/v1/applications?stage=recruiter_contact")
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()] == [application_id]

    updated = client.patch(
        f"/api/v1/applications/{application_id}",
        json={"stage": "assessment"},
    )
    assert updated.status_code == 200
    assert updated.json()["stage"] == "assessment"
    assert any(event["event_type"] == "stage_changed" for event in updated.json()["events"])

    archived = client.post(f"/api/v1/applications/{application_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "interested"
    assert archived.json()["archived_at"] is not None
    assert client.get("/api/v1/applications").json() == []
    assert client.get("/api/v1/applications?include_archived=true").json()[0]["id"] == application_id

    restored = client.post(
        f"/api/v1/applications/{application_id}/restore",
        json={"confirm_duplicate": False},
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert any(event["event_type"] == "application_restored" for event in restored.json()["events"])


def test_archived_is_not_a_lifecycle_status() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    response = client.post(
        "/api/v1/applications",
        json={"user_job_id": user_job_id, "status": "archived"},
    )
    assert response.status_code == 422


def test_application_records_are_isolated_between_users() -> None:
    client = create_multi_user_test_client()
    user_a = {"X-Test-User": "user-a"}
    user_b = {"X-Test-User": "user-b"}
    user_job_id = create_saved_job(client, user_a)
    created = client.post(
        "/api/v1/applications",
        json={"user_job_id": user_job_id},
        headers=user_a,
    )
    assert created.status_code == 200
    application_id = created.json()["id"]

    assert client.get("/api/v1/applications", headers=user_b).json() == []
    assert client.get(f"/api/v1/applications/{application_id}", headers=user_b).status_code == 404
    assert client.get(f"/api/v1/applications/{application_id}/events", headers=user_b).status_code == 404
    assert client.patch(
        f"/api/v1/applications/{application_id}",
        json={"notes": "Attempted cross-user update"},
        headers=user_b,
    ).status_code == 404


def test_application_tasks_support_types_reminders_filters_and_rescheduling() -> None:
    client = create_test_client()
    user_job_id = create_saved_job(client)
    application_id = client.post("/api/v1/applications", json={"user_job_id": user_job_id}).json()["id"]
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    future = datetime.now(timezone.utc) + timedelta(days=2)

    created = client.post(
        f"/api/v1/applications/{application_id}/tasks",
        json={
            "title": "Follow up with recruiter",
            "task_type": "follow_up",
            "due_at": past.isoformat(),
            "reminder_at": past.isoformat(),
        },
    )
    assert created.status_code == 200
    task = created.json()
    assert task["is_overdue"] is True
    assert task["reminder_due"] is True

    filtered = client.get(
        f"/api/v1/applications/{application_id}/tasks?task_type=follow_up&status=open"
    )
    assert [item["id"] for item in filtered.json()] == [task["id"]]

    rescheduled = client.patch(
        f"/api/v1/applications/{application_id}/tasks/{task['id']}",
        json={"task_type": "interview_prep", "due_at": future.isoformat(), "reminder_at": past.isoformat()},
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["task_type"] == "interview_prep"
    assert rescheduled.json()["is_overdue"] is False

    dismissed = client.patch(
        f"/api/v1/applications/{application_id}/tasks/{task['id']}",
        json={"dismiss_reminder": True},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["reminder_due"] is False
    assert dismissed.json()["reminder_dismissed_at"] is not None

    completed = client.patch(
        f"/api/v1/applications/{application_id}/tasks/{task['id']}",
        json={"completed": True},
    )
    assert completed.status_code == 200
    assert client.get(f"/api/v1/applications/{application_id}/tasks?status=open").json() == []
    assert len(client.get(f"/api/v1/applications/{application_id}/tasks?status=completed").json()) == 1


def test_application_attachment_stays_on_exact_version_and_uses_one_time_download(tmp_path) -> None:
    client = create_test_client(tmp_path)
    user_job_id = create_saved_job(client)
    application_id = client.post("/api/v1/applications", json={"user_job_id": user_job_id}).json()["id"]
    uploaded = client.post(
        "/api/v1/documents",
        data={"title": "Submitted Resume", "document_type": "resume"},
        files={"file": ("resume-v1.txt", b"Submitted version one.", "text/plain")},
    ).json()
    version_one_id = uploaded["latest_version"]["id"]

    attached = client.post(
        f"/api/v1/applications/{application_id}/documents",
        json={"document_version_id": version_one_id, "purpose": "resume"},
    )
    assert attached.status_code == 200
    attachment = attached.json()
    assert attachment["version_number"] == 1

    replacement = client.post(
        f"/api/v1/documents/{uploaded['id']}/versions",
        files={"file": ("resume-v2.txt", b"Replacement version two.", "text/plain")},
    )
    assert replacement.status_code == 200
    assert replacement.json()["latest_version"]["version_number"] == 2

    detail = client.get(f"/api/v1/applications/{application_id}").json()
    assert detail["documents"][0]["document_version_id"] == version_one_id
    assert detail["documents"][0]["version_number"] == 1

    dependencies = client.get(f"/api/v1/documents/{uploaded['id']}/dependencies").json()
    assert any(item["dependency_type"] == "application_document" for item in dependencies["dependencies"])
    assert client.delete(f"/api/v1/documents/{uploaded['id']}?force=true").status_code == 204

    ticket = client.post(
        f"/api/v1/applications/{application_id}/documents/{attachment['id']}/download-ticket"
    )
    assert ticket.status_code == 200
    download_path = ticket.json()["download_path"]
    assert client.get(f"/api/v1{download_path}").content == b"Submitted version one."
    assert client.get(f"/api/v1{download_path}").status_code == 404

    detached = client.delete(
        f"/api/v1/applications/{application_id}/documents/{attachment['id']}"
    )
    assert detached.status_code == 204
    detail = client.get(f"/api/v1/applications/{application_id}").json()
    assert detail["documents"] == []
    event_types = {event["event_type"] for event in detail["events"]}
    assert {"document_attached", "document_download_authorized", "document_detached"}.issubset(event_types)


def test_application_cannot_attach_another_users_document_version() -> None:
    client = create_multi_user_test_client()
    user_a = {"X-Test-User": "attachment-owner"}
    user_b = {"X-Test-User": "other-user"}
    uploaded = client.post(
        "/api/v1/documents",
        data={"title": "Private Resume", "document_type": "resume"},
        files={"file": ("private.txt", b"Private resume.", "text/plain")},
        headers=user_a,
    )
    assert uploaded.status_code == 200
    private_version_id = uploaded.json()["latest_version"]["id"]
    user_b_job_id = create_saved_job(client, user_b)
    user_b_application = client.post(
        "/api/v1/applications",
        json={"user_job_id": user_b_job_id},
        headers=user_b,
    )
    assert user_b_application.status_code == 200

    response = client.post(
        f"/api/v1/applications/{user_b_application.json()['id']}/documents",
        json={"document_version_id": private_version_id, "purpose": "resume"},
        headers=user_b,
    )
    assert response.status_code == 404

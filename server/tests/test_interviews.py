from __future__ import annotations

from fastapi import Header
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.interviews import repository
from app.modules.interviews.models import InterviewPrepGuide
from app.modules.interviews.schemas import InterviewPrepOutput, PrepTalkingPoint
from app.modules.interviews.service import enforce_resume_evidence


def create_test_client(handler=None) -> tuple[TestClient, sessionmaker]:
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
    if handler is not None:
        app.state.operation_handlers = {"interview_prep": handler}
    return TestClient(app), session_factory


def create_application_and_resume(client: TestClient) -> tuple[int, int]:
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Example Co",
            "raw_description_text": "Build Python APIs and operate PostgreSQL services.",
            "job_data": {
                "title": "Backend Engineer",
                "company": "Example Co",
                "summary": "Build backend services.",
                "responsibilities": ["Build Python APIs."],
                "required_skills": ["Python", "PostgreSQL"],
                "preferred_skills": [],
                "required_experience": [],
                "preferred_experience": [],
                "education": [],
                "certifications": [],
                "tools_and_technologies": ["Python", "PostgreSQL"],
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
    assert job.status_code == 200
    application = client.post("/api/v1/applications", json={"user_job_id": job.json()["id"]})
    assert application.status_code == 200
    resume = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Backend Resume",
            "resume_data": {
                "headline": "Backend Engineer",
                "summary": "Builds reliable APIs.",
                "experience": ["Built Python APIs serving customer workflows."],
                "skills": ["Python", "SQL"],
                "education": [],
                "certifications": [],
                "projects": [],
                "awards": [],
                "publications": [],
                "languages": [],
                "volunteer": [],
                "target_roles": [],
                "notes": [],
            },
        },
    )
    assert resume.status_code == 200
    return application.json()["id"], resume.json()["id"]


def test_interviews_schedule_update_and_notes_without_ai() -> None:
    client, _ = create_test_client()
    application_id, _ = create_application_and_resume(client)
    created = client.post(
        "/api/v1/interviews",
        json={
            "application_id": application_id,
            "interview_type": "technical",
            "stage": "technical_interview",
            "duration_minutes": 60,
            "private_notes": "Prepare system design examples.",
        },
    )
    assert created.status_code == 201
    interview_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/interviews/{interview_id}",
        json={"status": "completed", "outcome": "advanced"},
    )
    assert updated.status_code == 200
    assert updated.json()["outcome"] == "advanced"

    note = client.post(
        f"/api/v1/interviews/{interview_id}/notes",
        json={"body": "Review the database scaling answer."},
    )
    assert note.status_code == 201
    detail = client.get(f"/api/v1/interviews/{interview_id}").json()
    assert detail["notes"][0]["body"] == "Review the database scaling answer."


def test_interview_prep_snapshots_inputs_and_appends_regenerations() -> None:
    def prep_handler(db, identity, raw, context):
        guide = repository.get_prep_guide_for_identity(db, identity, int(raw["guide_id"]))
        assert guide is not None
        evidence = guide.resume_data_snapshot["experience"][0]
        output = InterviewPrepOutput(
            overview="Focus on API design and data reliability.",
            talking_points=[
                PrepTalkingPoint(topic="APIs", supported_claim="Built customer APIs.", resume_evidence=evidence)
            ],
            warnings=list(guide.source_warnings or []),
        )
        result = repository.complete_prep_guide(guide, output, model_name="test-model")
        context.update(1, total=1, usage={"guides": 1})
        return jsonable_encoder(result)

    client, session_factory = create_test_client(prep_handler)
    application_id, resume_id = create_application_and_resume(client)
    interview = client.post(
        "/api/v1/interviews",
        json={"application_id": application_id, "interview_type": "technical"},
    ).json()

    first = client.post(
        "/api/v1/operations/interview-prep",
        json={"interview_id": interview["id"], "resume_profile_id": resume_id, "company_notes": "Cloud product."},
    )
    second = client.post(
        "/api/v1/operations/interview-prep",
        json={"interview_id": interview["id"], "resume_profile_id": resume_id, "company_notes": "Data product."},
    )
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] != second.json()["id"]

    detail = client.get(f"/api/v1/interviews/{interview['id']}").json()
    assert len(detail["prep_guides"]) == 2
    assert all(guide["output_data"]["talking_points"] for guide in detail["prep_guides"])
    with session_factory() as db:
        snapshots = list(
            db.scalars(select(InterviewPrepGuide).order_by(InterviewPrepGuide.id.asc()))
        )
        assert snapshots[0].company_notes_snapshot == "Cloud product."
        assert snapshots[1].company_notes_snapshot == "Data product."
        assert snapshots[0].resume_data_snapshot["skills"] == ["Python", "SQL"]


def test_unsupported_talking_points_are_removed() -> None:
    output = InterviewPrepOutput(
        overview="Prepare for the interview.",
        talking_points=[
            PrepTalkingPoint(topic="APIs", supported_claim="Built APIs.", resume_evidence="Built Python APIs."),
            PrepTalkingPoint(topic="Scale", supported_claim="Led a global migration.", resume_evidence="Led a global migration."),
        ],
    )
    checked = enforce_resume_evidence(
        output,
        {"experience": ["Built Python APIs."], "skills": ["Python"]},
        [],
    )
    assert [point.topic for point in checked.talking_points] == ["APIs"]
    assert "removed" in checked.warnings[0]


def test_prep_failure_does_not_block_interview_notes() -> None:
    def failing_handler(*_args):
        raise RuntimeError("provider unavailable")

    client, _ = create_test_client(failing_handler)
    application_id, resume_id = create_application_and_resume(client)
    interview = client.post("/api/v1/interviews", json={"application_id": application_id}).json()
    queued = client.post(
        "/api/v1/operations/interview-prep",
        json={"interview_id": interview["id"], "resume_profile_id": resume_id},
    )
    assert queued.status_code == 202
    operation = client.get(f"/api/v1/operations/{queued.json()['id']}").json()
    assert operation["status"] == "failed"
    assert operation["usage"]["duration_ms"] >= 0
    note = client.post(
        f"/api/v1/interviews/{interview['id']}/notes",
        json={"body": "Provider failed, continue manual preparation."},
    )
    assert note.status_code == 201


def test_interviews_are_owner_scoped() -> None:
    client, _ = create_test_client()

    def identity_for_header(x_test_user: str = Header()) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(
            external_user_id=x_test_user,
            email=f"{x_test_user}@example.com",
            display_name=x_test_user,
            provider="test",
        )

    client.app.dependency_overrides[get_current_identity] = identity_for_header
    first_headers = {"X-Test-User": "first"}
    second_headers = {"X-Test-User": "second"}
    job = client.post(
        "/api/v1/jobs",
        json={
            "title": "Private Role",
            "company": "Example",
            "raw_description_text": "Private job.",
            "job_data": {
                "title": "Private Role",
                "company": "Example",
                "summary": "Private job.",
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
        },
        headers=first_headers,
    )
    assert job.status_code == 200, job.text
    application = client.post(
        "/api/v1/applications",
        json={"user_job_id": job.json()["id"]},
        headers=first_headers,
    )
    interview = client.post(
        "/api/v1/interviews",
        json={"application_id": application.json()["id"]},
        headers=first_headers,
    )
    assert interview.status_code == 201
    assert client.get("/api/v1/interviews", headers=second_headers).json() == []
    assert client.get(
        f"/api/v1/interviews/{interview.json()['id']}", headers=second_headers
    ).status_code == 404

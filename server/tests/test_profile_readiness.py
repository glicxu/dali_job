from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.profiles.readiness import READINESS_VERSION, evaluate_profile_readiness
from app.modules.profiles.schemas import ResumeData


def test_search_preferences_alone_do_not_pass_profile_readiness() -> None:
    result = evaluate_profile_readiness(
        ResumeData(
            headline="Backend Engineer",
            target_roles=["Backend Engineer"],
        )
    )

    assert result.ready is False
    assert result.pathway == "undetermined"
    assert result.readiness_version == READINESS_VERSION
    assert {item.code for item in result.missing_requirements} == {
        "experience_context_required",
        "experience_detail_required",
        "skills_required",
    }
    assert result.evidence_summary.experience_items == 0
    assert result.evidence_summary.skill_items == 0


def test_experienced_profile_passes_with_work_detail_and_distinct_skills() -> None:
    result = evaluate_profile_readiness(
        ResumeData(
            experience=["Built and launched Python APIs that reduced processing time by 35%."],
            skills=["Python", "FastAPI", "PostgreSQL"],
        )
    )

    assert result.ready is True
    assert result.pathway == "experienced"
    assert result.missing_requirements == []
    assert result.warnings == []
    assert result.evidence_summary.outcome_items == 1


def test_early_career_profile_can_pass_without_formal_work_experience() -> None:
    result = evaluate_profile_readiness(
        ResumeData(
            projects=["Designed and completed a mobile budgeting app used by 12 student testers."],
            education=["Bachelor of Science in Computer Science"],
            skills=["Dart", "Flutter", "Firebase"],
        )
    )

    assert result.ready is True
    assert result.pathway == "early_career"
    assert result.evidence_summary.experience_items == 0
    assert result.evidence_summary.supporting_items == 2


def test_career_transition_uses_transferable_evidence_not_target_role() -> None:
    result = evaluate_profile_readiness(
        ResumeData(
            experience=["Led customer onboarding and improved completion rates by 18 percent."],
            skills=["Process design", "Data analysis", "Stakeholder communication"],
            target_roles=["Product Manager"],
        )
    )

    assert result.ready is True
    assert result.pathway == "experienced"
    assert result.evidence_summary.experience_items == 1


def test_duplicate_skills_and_weak_context_do_not_pass() -> None:
    result = evaluate_profile_readiness(
        ResumeData(
            education=["BS"],
            skills=["Python", " python ", "SQL"],
        )
    )

    assert result.ready is False
    assert result.pathway == "early_career"
    assert result.evidence_summary.skill_items == 2
    assert {item.code for item in result.missing_requirements} == {
        "experience_detail_required",
        "skills_required",
    }
    assert [warning.code for warning in result.warnings] == ["outcome_detail_recommended"]


def test_readiness_endpoint_enforces_profile_ownership() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    current_identity = {
        "value": AuthenticatedIdentity(
            external_user_id="101",
            email="owner@example.com",
            display_name="Profile Owner",
            provider="local",
        )
    }

    def override_db():
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_current_identity] = lambda: current_identity["value"]
    client = TestClient(app)

    created = client.post(
        "/api/v1/resume-profiles",
        json={
            "title": "Ready profile",
            "resume_data": {
                "experience": ["Built and shipped accessible mobile applications for paying customers."],
                "skills": ["Dart", "Flutter", "REST APIs"],
            },
        },
    )
    assert created.status_code == 200
    profile_id = created.json()["id"]

    response = client.get(f"/api/v1/resume-profiles/{profile_id}/readiness")
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert "target_roles" not in response.json()["evidence_summary"]

    current_identity["value"] = AuthenticatedIdentity(
        external_user_id="202",
        email="other@example.com",
        display_name="Other User",
        provider="local",
    )
    assert client.get(f"/api/v1/resume-profiles/{profile_id}/readiness").status_code == 404

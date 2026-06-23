from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.profiles.models import ResumeProfile
import app.modules.profiles.router as profile_router
from app.modules.profiles.schemas import ResumeData


class StubResumeParser:
    def parse(self, resume_text: str) -> ResumeData:
        return ResumeData(
            headline="Parsed Resume",
            summary="Parsed summary.",
            skills=["Parsed Skill"],
        )


async def fake_extract_resume_text(_file) -> str:
    return "Redacted resume text"


def test_resume_import_preview_does_not_update_profile_until_apply(monkeypatch) -> None:
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

    monkeypatch.setattr(profile_router, "extract_resume_text", fake_extract_resume_text)

    app = create_app()
    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[profile_router.get_resume_profile_parser] = lambda: StubResumeParser()
    client = TestClient(app)

    response = client.post(
        "/api/v1/profile/resume-imports",
        files={"file": ("resume.pdf", b"fake pdf bytes", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["suggestions"]["headline"] == "Parsed Resume"

    with session_factory() as session:
        assert session.query(ResumeProfile).count() == 0

    apply_response = client.post("/api/v1/profile/resume-imports/apply", json=response.json()["suggestions"])

    assert apply_response.status_code == 200
    assert apply_response.json()["title"] == "Parsed Resume"
    with session_factory() as session:
        resume_profiles = session.query(ResumeProfile).all()
        assert len(resume_profiles) == 1
        assert resume_profiles[0].resume_data["headline"] == "Parsed Resume"
        assert resume_profiles[0].resume_data["skills"] == ["Parsed Skill"]

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db_session
from app.main import create_app
from app.modules.health.router import EXPECTED_ALEMBIC_HEAD


def create_health_client(revision: str | None) -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    if revision is not None:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": revision},
            )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    app = create_app()

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app)


def test_database_health_reports_ready_at_expected_head() -> None:
    response = create_health_client(EXPECTED_ALEMBIC_HEAD).get("/api/v1/health/db")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database_ready": True,
        "current_revision": EXPECTED_ALEMBIC_HEAD,
        "expected_revision": EXPECTED_ALEMBIC_HEAD,
    }


def test_database_health_fails_when_migration_table_is_missing() -> None:
    response = create_health_client(None).get("/api/v1/health/db")

    assert response.status_code == 503
    assert response.json()["database_ready"] is False
    assert response.json()["current_revision"] is None


def test_database_health_fails_when_revision_is_outdated() -> None:
    response = create_health_client("20260714_0018").get("/api/v1/health/db")

    assert response.status_code == 503
    assert response.json()["database_ready"] is False
    assert response.json()["current_revision"] == "20260714_0018"

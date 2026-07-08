from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.auth.dependencies import get_auth_secret
from app.modules.auth.security import hash_password, verify_password


def test_password_hash_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", password_hash)
    assert not verify_password("wrong password", password_hash)


def test_auth_secret_prefers_environment(monkeypatch) -> None:
    monkeypatch.setenv("DALIJOB_JWT_SECRET", "env-secret")

    assert get_auth_secret() == "env-secret"


def test_register_and_login_issue_dalijob_token() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    app = create_app()
    app.state.runtime = app.state.runtime.__class__(
        **{
            **app.state.runtime.__dict__,
            "auth_mode": "local",
        }
    )

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

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "strong-password",
            "display_name": "Example User",
        },
    )

    assert register_response.status_code == 200
    register_payload = register_response.json()
    assert register_payload["token_type"] == "bearer"
    assert register_payload["user"]["email"] == "user@example.com"
    assert register_payload["user"]["provider"] == "dalijob"
    assert register_payload["access_token"]

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "strong-password"},
    )

    assert login_response.status_code == 200
    assert login_response.json()["access_token"]

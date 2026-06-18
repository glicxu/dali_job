from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.documents.models import Document, DocumentVersion


def test_document_upload_list_text_and_download(tmp_path) -> None:
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
    app.state.runtime = app.state.runtime.__class__(
        **{
            **app.state.runtime.__dict__,
            "document_storage_dir": str(tmp_path),
        }
    )
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    upload_response = client.post(
        "/api/v1/documents",
        data={"title": "Master Resume", "document_type": "resume"},
        files={
            "file": (
                "resume.txt",
                b"Jane Example\njane@example.com\n\nSummary\nBackend engineer with Python.",
                "text/plain",
            )
        },
    )

    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["title"] == "Master Resume"
    assert uploaded["latest_version"]["file_name"] == "resume.txt"
    assert uploaded["latest_version"]["extracted_text_available"] is True

    list_response = client.get("/api/v1/documents")
    assert list_response.status_code == 200
    assert len(list_response.json()["documents"]) == 1

    text_response = client.get(f"/api/v1/documents/{uploaded['id']}/text")
    assert text_response.status_code == 200
    extracted_text = text_response.json()["extracted_text"]
    assert "jane@example.com" not in extracted_text
    assert "Backend engineer with Python." in extracted_text

    download_response = client.get(f"/api/v1/documents/{uploaded['id']}/download")
    assert download_response.status_code == 200
    assert download_response.content.startswith(b"Jane Example")

    with session_factory() as session:
        document = session.execute(select(Document)).scalar_one()
        version = session.execute(select(DocumentVersion)).scalar_one()
        assert document.title == "Master Resume"
        assert version.sha256
        assert version.storage_path

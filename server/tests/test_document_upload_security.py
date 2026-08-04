from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.documents.storage import read_supported_upload, safe_file_name
from app.modules.profiles import resume_import


def _upload(content: bytes, content_type: str, filename: str = "resume.pdf") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.parametrize(
    ("content", "content_type", "expected_detail"),
    [
        (b"not a pdf", "application/pdf", "valid PDF signature"),
        (b"%PDF-1.7\nnot text", "text/plain", "declared as plain text"),
        (b"text\x00binary", "text/plain", "binary data"),
        (b"\xff\xfe", "text/plain", "UTF-8"),
    ],
)
def test_upload_rejects_mime_spoofing_and_binary_text(
    content: bytes,
    content_type: str,
    expected_detail: str,
) -> None:
    with pytest.raises(HTTPException) as caught:
        asyncio.run(read_supported_upload(_upload(content, content_type)))

    assert caught.value.status_code == 400
    assert expected_detail in str(caught.value.detail)


def test_upload_read_is_bounded_before_validation() -> None:
    oversized = b"a" * (resume_import.MAX_RESUME_BYTES + 1)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(read_supported_upload(_upload(oversized, "text/plain", "resume.txt")))

    assert caught.value.status_code == 413


@pytest.mark.parametrize(
    ("unsafe_name", "safe_name"),
    [
        ("../../resume.pdf", "resume.pdf"),
        (r"..\..\resume.pdf", "resume.pdf"),
        ("\r\nmalicious.txt", "malicious.txt"),
        ("..", "document"),
    ],
)
def test_file_name_is_reduced_to_safe_basename(unsafe_name: str, safe_name: str) -> None:
    assert safe_file_name(unsafe_name) == safe_name


def test_malformed_pdf_is_rejected_before_storage(tmp_path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with session_factory() as session:
            yield session

    app = create_app()
    app.state.runtime = app.state.runtime.__class__(
        **{**app.state.runtime.__dict__, "document_storage_dir": str(tmp_path)}
    )
    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/documents",
        files={"file": ("resume.pdf", b"%PDF-1.7\nmalformed", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Could not safely read the uploaded PDF."
    assert list(tmp_path.iterdir()) == []


def test_pdf_page_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return "resume"

    class FakeReader:
        is_encrypted = False
        pages = [FakePage() for _ in range(resume_import.MAX_PDF_PAGES + 1)]

        def __init__(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(resume_import, "PdfReader", FakeReader)

    with pytest.raises(HTTPException) as caught:
        resume_import.extract_pdf_text(b"%PDF-1.7\n")

    assert caught.value.status_code == 400
    assert "at most" in str(caught.value.detail)


def test_pdf_extracted_text_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return "x" * (resume_import.MAX_PDF_EXTRACTED_CHARS + 1)

    class FakeReader:
        is_encrypted = False
        pages = [FakePage()]

        def __init__(self, *_args, **_kwargs) -> None:
            pass

    monkeypatch.setattr(resume_import, "PdfReader", FakeReader)

    with pytest.raises(HTTPException) as caught:
        resume_import.extract_pdf_text(b"%PDF-1.7\n")

    assert caught.value.status_code == 400
    assert "processing limit" in str(caught.value.detail)

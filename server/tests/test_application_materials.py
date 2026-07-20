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
from app.modules.materials import repository
from app.modules.materials.models import GeneratedApplicationMaterial, GeneratedApplicationMaterialVersion
from app.modules.materials.schemas import (
    CoverLetterOutput,
    CoverLetterParagraph,
    EvidenceBackedText,
    TailoredResumeOutput,
)
from app.modules.materials.service import enforce_material_evidence
from app.modules.materials.rendering import render_material


def create_test_client(handler=None) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
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
        app.state.operation_handlers = {"application_material_generation": handler}
    return TestClient(app), session_factory


def create_application(client: TestClient, headers: dict | None = None) -> int:
    job = client.post(
        "/api/v1/jobs",
        headers=headers,
        json={
            "title": "Backend Engineer",
            "company": "Example Co",
            "raw_description_text": "Build Python APIs and PostgreSQL services.",
            "job_data": {
                "title": "Backend Engineer", "company": "Example Co", "summary": "Build backend services.",
                "responsibilities": ["Build Python APIs."], "required_skills": ["Python", "PostgreSQL"],
                "preferred_skills": [], "required_experience": [], "preferred_experience": [],
                "education": [], "certifications": [], "tools_and_technologies": ["Python", "PostgreSQL"],
                "keywords": ["backend"], "seniority_level": "", "employment_type": "",
                "security_clearance": "", "work_location": "Remote", "salary_range": "",
                "application_deadline": "",
            },
        },
    )
    assert job.status_code == 200, job.text
    application = client.post("/api/v1/applications", headers=headers, json={"user_job_id": job.json()["id"]})
    assert application.status_code == 200, application.text
    return application.json()["id"]


def upload_resume(client: TestClient, text: str, headers: dict | None = None) -> dict:
    response = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"title": "Master Resume", "document_type": "resume"},
        files={"file": ("resume.txt", text.encode(), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def material_handler(db, identity, raw, context):
    version = repository.get_version_for_identity(db, identity, int(raw["material_version_id"]))
    assert version is not None
    material = db.get(GeneratedApplicationMaterial, version.material_id)
    assert material is not None
    if material.material_type == "tailored_resume":
        content = TailoredResumeOutput(
            headline=EvidenceBackedText(text="Backend Engineer", source_evidence="Built Python APIs."),
            experience=[EvidenceBackedText(text="Built Python APIs for customer workflows.", source_evidence="Built Python APIs.")],
            skills=[EvidenceBackedText(text="Python", source_evidence="Python")],
        ).model_dump(mode="json")
    else:
        content = CoverLetterOutput(
            paragraphs=[CoverLetterParagraph(
                text="My Python API experience aligns with this backend role.",
                resume_evidence=["Built Python APIs."], job_evidence=["Build Python APIs."],
            )]
        ).model_dump(mode="json")
    repository.complete_generation(version, content, [], model_name="test-model", provider_execution_reference="test-run")
    context.update(1, total=1, usage={"generated": 1})
    return jsonable_encoder(repository.material_response(db, identity, material))


def test_tailored_resume_snapshots_exact_document_version_and_appends_revision() -> None:
    client, session_factory = create_test_client(material_handler)
    application_id = create_application(client)
    resume = upload_resume(client, "Backend Engineer\nBuilt Python APIs.\nPython")
    version_one_id = resume["latest_version"]["id"]
    replacement = client.post(
        f"/api/v1/documents/{resume['id']}/versions",
        files={"file": ("resume-v2.txt", b"Changed resume content.", "text/plain")},
    )
    assert replacement.status_code == 200

    queued = client.post(
        "/api/v1/operations/tailored-resume",
        json={"application_id": application_id, "source_document_version_id": version_one_id},
    )
    assert queued.status_code == 202, queued.text
    assert client.get(f"/api/v1/operations/{queued.json()['id']}").json()["status"] == "succeeded"
    material = client.get(f"/api/v1/application-materials?application_id={application_id}").json()["materials"][0]
    first = material["versions"][0]
    assert first["source_document_version_id"] == version_one_id
    assert first["source_document_version_number"] == 1

    revised_content = dict(first["content_data"])
    revised_content["tailoring_notes"] = ["User-approved wording."]
    revised = client.post(
        f"/api/v1/application-materials/{material['id']}/versions",
        json={"parent_version_id": first["id"], "content_data": revised_content},
    )
    assert revised.status_code == 201, revised.text
    assert [version["version_number"] for version in revised.json()["versions"]] == [2, 1]
    assert revised.json()["versions"][0]["version_source"] == "user"

    with session_factory() as db:
        stored = db.scalar(select(GeneratedApplicationMaterialVersion).where(GeneratedApplicationMaterialVersion.id == first["id"]))
        assert stored.source_resume_snapshot["extracted_text"] == "Backend Engineer\nBuilt Python APIs.\nPython"
        assert stored.content_data["tailoring_notes"] == []


def test_cover_letter_can_link_to_exact_tailored_resume_version() -> None:
    client, _ = create_test_client(material_handler)
    application_id = create_application(client)
    resume = upload_resume(client, "Built Python APIs. Python")
    source_version = resume["latest_version"]["id"]
    client.post("/api/v1/operations/tailored-resume", json={"application_id": application_id, "source_document_version_id": source_version})
    tailored = client.get("/api/v1/application-materials").json()["materials"][0]
    tailored_version_id = tailored["versions"][0]["id"]

    response = client.post(
        "/api/v1/operations/cover-letter",
        json={
            "application_id": application_id,
            "source_document_version_id": source_version,
            "source_material_version_id": tailored_version_id,
        },
    )
    assert response.status_code == 202, response.text
    materials = client.get("/api/v1/application-materials").json()["materials"]
    cover = next(material for material in materials if material["material_type"] == "cover_letter")
    assert cover["versions"][0]["source_material_version_id"] == tailored_version_id
    assert cover["versions"][0]["content_data"]["paragraphs"]


def test_materials_are_owner_scoped() -> None:
    client, _ = create_test_client(material_handler)

    def identity_for_header(x_test_user: str = Header()) -> AuthenticatedIdentity:
        return AuthenticatedIdentity(external_user_id=x_test_user, email=f"{x_test_user}@example.com", display_name=x_test_user, provider="test")

    client.app.dependency_overrides[get_current_identity] = identity_for_header
    first = {"X-Test-User": "first"}
    second = {"X-Test-User": "second"}
    application_id = create_application(client, first)
    resume = upload_resume(client, "Built Python APIs. Python", first)
    client.post(
        "/api/v1/operations/tailored-resume", headers=first,
        json={"application_id": application_id, "source_document_version_id": resume["latest_version"]["id"]},
    )
    material = client.get("/api/v1/application-materials", headers=first).json()["materials"][0]
    assert client.get("/api/v1/application-materials", headers=second).json()["materials"] == []
    assert client.get(f"/api/v1/application-materials/{material['id']}", headers=second).status_code == 404


def test_unsupported_material_evidence_is_removed() -> None:
    output = TailoredResumeOutput(
        experience=[
            EvidenceBackedText(text="Built APIs.", source_evidence="Built Python APIs."),
            EvidenceBackedText(text="Led global migration.", source_evidence="Led global migration."),
        ]
    )
    checked, warnings = enforce_material_evidence(
        "tailored_resume", output,
        {"extracted_text": "Backend Engineer\nBuilt Python APIs."},
        {"job_data": {"responsibilities": ["Build Python APIs."]}},
    )
    assert isinstance(checked, TailoredResumeOutput)
    assert [item.text for item in checked.experience] == ["Built APIs."]
    assert "Removed 1" in warnings[0]


def test_provider_failure_preserves_pending_material_and_application() -> None:
    def failing_handler(*_args):
        raise RuntimeError("provider unavailable")

    client, _ = create_test_client(failing_handler)
    application_id = create_application(client)
    resume = upload_resume(client, "Built Python APIs. Python")
    queued = client.post(
        "/api/v1/operations/tailored-resume",
        json={
            "application_id": application_id,
            "source_document_version_id": resume["latest_version"]["id"],
        },
    )
    assert queued.status_code == 202
    operation = client.get(f"/api/v1/operations/{queued.json()['id']}").json()
    assert operation["status"] == "failed"
    material = client.get("/api/v1/application-materials").json()["materials"][0]
    assert material["versions"][0]["content_data"] is None
    assert material["versions"][0]["source_document_version_id"] == resume["latest_version"]["id"]
    assert client.get(f"/api/v1/applications/{application_id}").status_code == 200


def test_completed_material_renders_to_pdf_and_docx() -> None:
    content = TailoredResumeOutput(
        headline=EvidenceBackedText(text="Backend Engineer", source_evidence="Backend Engineer"),
        skills=[EvidenceBackedText(text="Python", source_evidence="Python")],
    ).model_dump(mode="json")

    pdf = render_material("tailored_resume", content, "pdf")
    docx = render_material("tailored_resume", content, "docx")

    assert pdf.startswith(b"%PDF")
    assert docx.startswith(b"PK")


def test_rendered_material_is_saved_and_attached_to_application() -> None:
    client, _ = create_test_client(material_handler)
    application_id = create_application(client)
    resume = upload_resume(client, "Backend Engineer\nBuilt Python APIs.\nPython")
    client.post(
        "/api/v1/operations/tailored-resume",
        json={"application_id": application_id, "source_document_version_id": resume["latest_version"]["id"]},
    )
    material = client.get("/api/v1/application-materials").json()["materials"][0]
    version_id = material["versions"][0]["id"]

    rendered = client.post(
        f"/api/v1/application-materials/versions/{version_id}/render",
        json={"format": "pdf", "attach_to_application": True},
    )

    assert rendered.status_code == 201, rendered.text
    payload = rendered.json()
    assert payload["content_type"] == "application/pdf"
    assert payload["attachment_id"] is not None
    attachments = client.get(f"/api/v1/applications/{application_id}/documents").json()
    assert any(item["document_version_id"] == payload["document_version_id"] for item in attachments)

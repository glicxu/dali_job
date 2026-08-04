from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.applications import repository as application_repository
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents import repository as document_repository
from app.modules.documents.storage import sha256_hex, write_document_file
from app.modules.materials.models import GeneratedApplicationMaterial, GeneratedApplicationMaterialVersion

TAILORED_RESUME_SECTIONS = (
    ("Summary", "summary"),
    ("Skills", "skills"),
    ("Experience", "experience"),
    ("Education", "education"),
    ("Certifications", "certifications"),
    ("Projects", "projects"),
)


def _item_text(item: object) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or "").strip()
    return str(item or "").strip()


def render_tailored_resume_text(content_data: dict) -> str:
    lines: list[str] = []
    headline = _item_text(content_data.get("headline"))
    if headline:
        lines.extend((headline, ""))

    for heading, key in TAILORED_RESUME_SECTIONS:
        items = [_item_text(item) for item in content_data.get(key, [])]
        items = [item for item in items if item]
        if not items:
            continue
        lines.append(heading)
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    rendered = "\n".join(lines).strip()
    return f"{rendered}\n" if rendered else "Tailored resume\n"


def materialize_tailored_resume_document(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    storage_root: str,
    material: GeneratedApplicationMaterial,
    version: GeneratedApplicationMaterialVersion,
) -> int | None:
    if material.material_type != "tailored_resume" or version.content_data is None:
        return None

    application = application_repository.get_application_for_identity(
        db,
        identity,
        material.application_id,
        include_archived=True,
    )
    if application is None:
        raise ValueError("Application not found for generated tailored resume.")

    if version.output_document_version_id is None:
        job_title = str((version.job_snapshot or {}).get("title") or "Application").strip()
        text = render_tailored_resume_text(dict(version.content_data))
        content = text.encode("utf-8")
        file_name = f"tailored-resume-application-{application.id}-v{version.version_number}.txt"
        storage_path = write_document_file(storage_root, content, file_name)
        try:
            created = document_repository.create_document_with_version(
                db,
                identity,
                title=f"Tailored Resume - {job_title}",
                document_type="tailored_resume",
                file_name=file_name,
                content_type="text/plain",
                size_bytes=len(content),
                sha256=sha256_hex(content),
                storage_path=storage_path,
                extracted_text=text,
            )
            version.output_document_version_id = int(created["latest_version"]["id"])
            db.flush()
        except Exception:
            Path(storage_path).unlink(missing_ok=True)
            raise

    try:
        application_repository.attach_document(
            db,
            identity,
            application,
            document_version_id=version.output_document_version_id,
            purpose="resume",
        )
    except application_repository.DuplicateApplicationDocumentError:
        pass
    return version.output_document_version_id

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.modules.applications import repository as application_repository
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs import repository as job_repository
from app.modules.materials.models import GeneratedApplicationMaterial, GeneratedApplicationMaterialVersion, utc_now
from app.modules.materials.schemas import (
    CoverLetterGenerationRequest,
    MaterialRevisionRequest,
    TailoredResumeGenerationRequest,
    validate_material_content,
)
from app.modules.profiles.repository import ensure_account_for_identity


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip() or None


def _owned_application(db: Session, identity: AuthenticatedIdentity, application_id: int):
    return application_repository.get_application_for_identity(db, identity, application_id, include_archived=True)


def _owned_document_version(db: Session, identity: AuthenticatedIdentity, version_id: int) -> tuple[Document, DocumentVersion] | None:
    user, workspace = ensure_account_for_identity(db, identity)
    row = db.execute(
        select(Document, DocumentVersion)
        .join(DocumentVersion, DocumentVersion.document_id == Document.id)
        .where(
            DocumentVersion.id == version_id,
            Document.workspace_id == workspace.id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
    ).first()
    return row if row is not None else None


def _resume_snapshot(document: Document, version: DocumentVersion) -> dict:
    return {
        "document_id": document.id,
        "document_version_id": version.id,
        "document_title": document.title,
        "document_type": document.document_type,
        "version_number": version.version_number,
        "file_name": version.file_name,
        "sha256": version.sha256,
        "extracted_text": version.extracted_text or "",
    }


def _job_snapshot(db: Session, identity: AuthenticatedIdentity, application) -> dict:
    if application.user_job_id is None:
        raise ValueError("The application does not reference a saved job.")
    user_job = job_repository.get_user_job_for_identity(db, identity, application.user_job_id)
    if user_job is None:
        raise ValueError("The application's saved job is unavailable.")
    job = job_repository.job_response_for_identity(db, identity, user_job)
    return {
        "user_saved_job_id": user_job.id,
        "title": job.get("title") or "",
        "company": job.get("company") or "",
        "source_url": job.get("source_url"),
        "raw_description_text": job.get("raw_description_text") or "",
        "job_data": job.get("job_data") or {},
    }


def _get_or_create_material(db: Session, identity: AuthenticatedIdentity, application_id: int, material_type: str) -> GeneratedApplicationMaterial:
    user, workspace = ensure_account_for_identity(db, identity)
    material = db.scalar(
        select(GeneratedApplicationMaterial).where(
            GeneratedApplicationMaterial.workspace_id == workspace.id,
            GeneratedApplicationMaterial.user_id == user.id,
            GeneratedApplicationMaterial.application_id == application_id,
            GeneratedApplicationMaterial.material_type == material_type,
        )
    )
    if material is None:
        material = GeneratedApplicationMaterial(
            workspace_id=workspace.id, user_id=user.id, application_id=application_id, material_type=material_type
        )
        db.add(material)
        db.flush()
    return material


def _next_version_number(db: Session, material_id: int) -> int:
    current = db.scalar(select(func.coalesce(func.max(GeneratedApplicationMaterialVersion.version_number), 0)).where(GeneratedApplicationMaterialVersion.material_id == material_id)) or 0
    return int(current) + 1


def get_version_for_identity(db: Session, identity: AuthenticatedIdentity, version_id: int) -> GeneratedApplicationMaterialVersion | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(GeneratedApplicationMaterialVersion)
        .join(GeneratedApplicationMaterial, GeneratedApplicationMaterial.id == GeneratedApplicationMaterialVersion.material_id)
        .where(
            GeneratedApplicationMaterialVersion.id == version_id,
            GeneratedApplicationMaterial.workspace_id == workspace.id,
            GeneratedApplicationMaterial.user_id == user.id,
        )
    )


def create_generation_version(
    db: Session,
    identity: AuthenticatedIdentity,
    material_type: str,
    payload: TailoredResumeGenerationRequest | CoverLetterGenerationRequest,
) -> GeneratedApplicationMaterialVersion:
    application = _owned_application(db, identity, payload.application_id)
    if application is None:
        raise ValueError("Application not found.")
    resume_row = _owned_document_version(db, identity, payload.source_document_version_id)
    if resume_row is None:
        raise ValueError("Resume document version not found.")
    document, version = resume_row
    if document.document_type != "resume":
        raise ValueError("The selected document must be a resume.")
    if not version.extracted_text:
        raise ValueError("The selected resume version does not have extracted text.")

    source_material_version_id = getattr(payload, "source_material_version_id", None)
    if source_material_version_id is not None:
        source_version = get_version_for_identity(db, identity, source_material_version_id)
        if source_version is None:
            raise ValueError("Source tailored-resume version not found.")
        source_material = db.get(GeneratedApplicationMaterial, source_version.material_id)
        if source_material is None or source_material.application_id != application.id or source_material.material_type != "tailored_resume" or source_version.content_data is None:
            raise ValueError("The source material must be a completed tailored resume for this application.")

    material = _get_or_create_material(db, identity, application.id, material_type)
    pending = GeneratedApplicationMaterialVersion(
        material_id=material.id,
        version_number=_next_version_number(db, material.id),
        source_document_version_id=version.id,
        source_material_version_id=source_material_version_id,
        source_resume_snapshot=_resume_snapshot(document, version),
        job_snapshot=_job_snapshot(db, identity, application),
        request_notes_snapshot=_clean(payload.target_notes),
        version_source="ai",
        warnings=[],
        prompt_version="application-materials-v1",
        schema_version="application-materials-v1",
    )
    db.add(pending)
    material.updated_at = utc_now()
    db.flush()
    return pending


def link_operation(version: GeneratedApplicationMaterialVersion, operation_id: int) -> None:
    version.operation_id = operation_id


def complete_generation(version: GeneratedApplicationMaterialVersion, content_data: dict, warnings: list[str], *, model_name: str, provider_execution_reference: str | None) -> None:
    version.content_data = content_data
    version.warnings = list(dict.fromkeys(warnings))
    version.model_name = model_name
    version.provider_execution_reference = provider_execution_reference
    version.completed_at = utc_now()


def create_revision(db: Session, identity: AuthenticatedIdentity, material_id: int, payload: MaterialRevisionRequest) -> GeneratedApplicationMaterialVersion:
    material = get_material_for_identity(db, identity, material_id)
    if material is None:
        raise ValueError("Application material not found.")
    parent = get_version_for_identity(db, identity, payload.parent_version_id)
    if parent is None or parent.material_id != material.id or parent.content_data is None:
        raise ValueError("Completed parent material version not found.")
    content = validate_material_content(material.material_type, payload.content_data)
    revision = GeneratedApplicationMaterialVersion(
        material_id=material.id,
        version_number=_next_version_number(db, material.id),
        parent_version_id=parent.id,
        source_document_version_id=parent.source_document_version_id,
        source_material_version_id=parent.source_material_version_id,
        source_resume_snapshot=dict(parent.source_resume_snapshot or {}),
        job_snapshot=dict(parent.job_snapshot or {}),
        request_notes_snapshot=parent.request_notes_snapshot,
        content_data=content,
        version_source="user",
        warnings=list(parent.warnings or []),
        provider=parent.provider,
        model_name=parent.model_name,
        prompt_version=parent.prompt_version,
        schema_version=parent.schema_version,
        provider_execution_reference=parent.provider_execution_reference,
        completed_at=utc_now(),
    )
    db.add(revision)
    material.updated_at = utc_now()
    db.flush()
    return revision


def get_material_for_identity(db: Session, identity: AuthenticatedIdentity, material_id: int) -> GeneratedApplicationMaterial | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(select(GeneratedApplicationMaterial).where(GeneratedApplicationMaterial.id == material_id, GeneratedApplicationMaterial.workspace_id == workspace.id, GeneratedApplicationMaterial.user_id == user.id))


def _version_response(version: GeneratedApplicationMaterialVersion) -> dict:
    snapshot = dict(version.source_resume_snapshot or {})
    return {
        "id": version.id,
        "material_id": version.material_id,
        "version_number": version.version_number,
        "parent_version_id": version.parent_version_id,
        "operation_id": version.operation_id,
        "source_document_version_id": version.source_document_version_id,
        "source_material_version_id": version.source_material_version_id,
        "source_document_title": snapshot.get("document_title") or "Resume",
        "source_document_file_name": snapshot.get("file_name") or "",
        "source_document_version_number": int(snapshot.get("version_number") or 0),
        "source_document_sha256": snapshot.get("sha256") or "",
        "content_data": version.content_data,
        "version_source": version.version_source,
        "warnings": list(version.warnings or []),
        "provider": version.provider,
        "model_name": version.model_name,
        "prompt_version": version.prompt_version,
        "schema_version": version.schema_version,
        "provider_execution_reference": version.provider_execution_reference,
        "created_at": version.created_at,
        "completed_at": version.completed_at,
    }


def material_response(db: Session, identity: AuthenticatedIdentity, material: GeneratedApplicationMaterial) -> dict:
    application = _owned_application(db, identity, material.application_id)
    detail = application_repository.application_detail(db, identity, application) if application else {}
    job = detail.get("job") or {}
    versions = db.scalars(select(GeneratedApplicationMaterialVersion).where(GeneratedApplicationMaterialVersion.material_id == material.id).order_by(desc(GeneratedApplicationMaterialVersion.version_number))).all()
    return {
        "id": material.id,
        "application_id": material.application_id,
        "material_type": material.material_type,
        "application_label": f"{job.get('title') or 'Application'} - {job.get('company') or 'Unknown company'}",
        "created_at": material.created_at,
        "updated_at": material.updated_at,
        "versions": [_version_response(version) for version in versions],
    }


def list_materials(db: Session, identity: AuthenticatedIdentity, application_id: int | None = None) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    query = select(GeneratedApplicationMaterial).where(GeneratedApplicationMaterial.workspace_id == workspace.id, GeneratedApplicationMaterial.user_id == user.id)
    if application_id is not None:
        query = query.where(GeneratedApplicationMaterial.application_id == application_id)
    materials = db.scalars(query.order_by(desc(GeneratedApplicationMaterial.updated_at))).all()
    return [material_response(db, identity, material) for material in materials]

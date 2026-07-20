from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.applications import repository as application_repository
from app.modules.documents import repository as document_repository
from app.modules.documents.storage import sha256_hex, write_document_file
from app.modules.materials import repository
from app.modules.materials.rendering import plain_text, render_material
from app.modules.materials.schemas import (
    MaterialListResponse,
    MaterialRenderRequest,
    MaterialRenderResponse,
    MaterialResponse,
    MaterialRevisionRequest,
)

router = APIRouter(prefix="/application-materials", tags=["application-materials"])


@router.get("", response_model=MaterialListResponse)
def list_application_materials(
    application_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MaterialListResponse:
    return MaterialListResponse(materials=repository.list_materials(db, identity, application_id))


@router.get("/{material_id}", response_model=MaterialResponse)
def get_application_material(
    material_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    material = repository.get_material_for_identity(db, identity, material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application material not found.")
    return repository.material_response(db, identity, material)


@router.post("/{material_id}/versions", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
def revise_application_material(
    material_id: int,
    payload: MaterialRevisionRequest,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> dict:
    try:
        version = repository.create_revision(db, identity, material_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    material = repository.get_material_for_identity(db, identity, version.material_id)
    return repository.material_response(db, identity, material)


@router.post("/versions/{version_id}/render", response_model=MaterialRenderResponse, status_code=status.HTTP_201_CREATED)
def render_application_material(
    version_id: int,
    payload: MaterialRenderRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> MaterialRenderResponse:
    version = repository.get_version_for_identity(db, identity, version_id)
    if version is None or version.content_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Completed material version not found.")
    material = repository.get_material_for_identity(db, identity, version.material_id)
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application material not found.")
    application = application_repository.get_application_for_identity(
        db, identity, material.application_id, include_archived=True
    )
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    content = render_material(material.material_type, version.content_data, payload.format)
    extension = payload.format
    content_type = (
        "application/pdf"
        if payload.format == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    label = "tailored-resume" if material.material_type == "tailored_resume" else "cover-letter"
    file_name = f"{label}-v{version.version_number}.{extension}"
    storage_path = write_document_file(request.app.state.runtime.document_storage_dir, content, file_name)
    created = document_repository.create_document_with_version(
        db,
        identity,
        title=f"{label.replace('-', ' ').title()} v{version.version_number}",
        document_type="resume" if material.material_type == "tailored_resume" else "cover_letter",
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        storage_path=storage_path,
        extracted_text=plain_text(material.material_type, version.content_data),
    )
    document_version_id = int(created["latest_version"]["id"])
    attachment_id = None
    if payload.attach_to_application:
        attached = application_repository.attach_document(
            db,
            identity,
            application,
            document_version_id=document_version_id,
            purpose="resume" if material.material_type == "tailored_resume" else "cover_letter",
        )
        attachment_id = int(attached["id"])
    db.commit()
    return MaterialRenderResponse(
        material_id=material.id,
        material_version_id=version.id,
        document_id=int(created["id"]),
        document_version_id=document_version_id,
        attachment_id=attachment_id,
        file_name=Path(storage_path).name if not file_name else file_name,
        content_type=content_type,
        size_bytes=len(content),
    )

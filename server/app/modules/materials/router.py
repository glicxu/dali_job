from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.materials import repository
from app.modules.materials.schemas import MaterialListResponse, MaterialResponse, MaterialRevisionRequest

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

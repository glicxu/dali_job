from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.provider_ops import enforce_provider_rate_limit
from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents import repository as document_repository
from app.modules.documents.storage import (
    extract_redacted_text,
    read_supported_upload,
    safe_file_name,
    sha256_hex,
    write_document_file,
)
from app.modules.job_search.apify_indeed import APIFY_INDEED_ACTOR_ID
from app.modules.interviews import repository as interview_repository
from app.modules.interviews.models import InterviewPrepGuide
from app.modules.interviews.schemas import InterviewPrepRequest
from app.modules.materials import repository as material_repository
from app.modules.materials.models import GeneratedApplicationMaterialVersion
from app.modules.materials.schemas import CoverLetterGenerationRequest, TailoredResumeGenerationRequest
from app.modules.jobs.schemas import (
    IndeedJobSearchImportRequest,
    IndeedJobSearchRequest,
    JobImportRequest,
    JobListDiscoverRequest,
    JobListImportRequest,
)
from app.modules.operations import repository
from app.modules.operations.handlers import build_operation_handlers
from app.modules.operations.models import ManagedOperation
from app.modules.operations.schemas import (
    JobAnalyzeOperationRequest,
    ManagedOperationListResponse,
    ManagedOperationResponse,
    ManagedOperationSummaryResponse,
    ResumeParseRetryRequest,
)
from app.modules.operations.service import execute_operation, session_factory_for
from app.modules.resume_job_match.schemas import BulkSavedJobMatchRequest, ResumeJobMatchRequest

router = APIRouter(prefix="/operations", tags=["operations"])
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
VALID_STATUSES = {"queued", "running", *TERMINAL_STATUSES}


def _idempotency_key(operation_type: str, payload: dict, provided: str | None) -> str:
    material = provided.strip() if provided and provided.strip() else json.dumps(
        {"operation_type": operation_type, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _handlers(request: Request) -> dict:
    handlers = getattr(request.app.state, "operation_handlers", None)
    if handlers is None:
        handlers = build_operation_handlers(request.app)
        request.app.state.operation_handlers = handlers
    return handlers


def _enqueue(
    *,
    operation_type: str,
    payload: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session,
    identity: AuthenticatedIdentity,
    idempotency_key: str | None,
    provider: str | None,
    model_or_actor: str | None,
    prompt_version: str | None = None,
    progress_total: int | None = None,
) -> ManagedOperationResponse:
    enforce_provider_rate_limit(request, identity, feature=operation_type)
    operation, created = repository.create_operation(
        db,
        identity,
        operation_type=operation_type,
        idempotency_key=_idempotency_key(operation_type, payload, idempotency_key),
        request_payload=payload,
        provider=provider,
        model_or_actor=model_or_actor,
        prompt_version=prompt_version,
        progress_total=progress_total,
    )
    db.commit()
    db.refresh(operation)
    if created or operation.status == "queued":
        background_tasks.add_task(
            execute_operation,
            session_factory_for(db),
            operation.id,
            _handlers(request),
        )
    return ManagedOperationResponse.model_validate(operation)


@router.post("/job-search", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_search(
    payload: IndeedJobSearchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="job_search",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="apify",
        model_or_actor=APIFY_INDEED_ACTOR_ID,
        progress_total=1,
    )


@router.post("/provider-job-import", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_provider_job_import(
    payload: IndeedJobSearchImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="provider_job_import",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai" if payload.run_matching else "job_search_provider",
        model_or_actor=request.app.state.runtime.openai_model if payload.run_matching else APIFY_INDEED_ACTOR_ID,
        prompt_version="resume-job-match-v1" if payload.run_matching else None,
        progress_total=len(payload.selected_results),
    )


@router.post("/job-list-discover", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_list_discover(
    payload: JobListDiscoverRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="job_list_discover",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="web_extraction",
        model_or_actor=None,
        progress_total=1,
    )


@router.post("/job-list-import", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_list_import(
    payload: JobListImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="job_list_import",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai+web_extraction" if payload.run_matching else "web_extraction",
        model_or_actor=request.app.state.runtime.openai_model if payload.run_matching else None,
        prompt_version="resume-job-match-v1" if payload.run_matching else None,
        progress_total=len(payload.selected_urls),
    )


@router.post("/job-draft", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_draft(
    payload: JobImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="job_draft",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai+web_extraction" if payload.job_url else "openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="job-description-v1",
        progress_total=1,
    )


@router.post("/job-analyze", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_job_analyze(
    payload: JobAnalyzeOperationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="job_analyze",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="job-description-v1",
        progress_total=1,
    )


@router.post("/resume-job-match", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_resume_job_match(
    payload: ResumeJobMatchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="resume_job_match",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai+web_extraction" if payload.job_url else "openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="resume-job-match-v1",
        progress_total=1,
    )


@router.post("/bulk-resume-job-match", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_bulk_resume_job_match(
    payload: BulkSavedJobMatchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="bulk_resume_job_match",
        payload=payload.model_dump(mode="json"),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="resume-job-match-v1",
        progress_total=len(payload.user_job_ids),
    )


@router.post("/resume-parse", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_resume_parse(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    content = await read_supported_upload(file)
    file_name = safe_file_name(file.filename)
    content_type = file.content_type or "application/octet-stream"
    resume_text = extract_redacted_text(content, content_type)
    if not resume_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No resume text could be extracted.")
    storage_path = write_document_file(request.app.state.runtime.document_storage_dir, content, file_name)
    document = document_repository.create_document_with_version(
        db,
        identity,
        title=Path(file_name).stem or "Resume",
        document_type="resume",
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        storage_path=storage_path,
        extracted_text=resume_text,
    )
    return _enqueue(
        operation_type="resume_parse",
        payload={"document_id": document["id"]},
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key or f"document-version:{document['latest_version']['id']}",
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="resume-profile-v1",
        progress_total=1,
    )


@router.post("/resume-parse/retry", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_resume_parse_retry(
    payload: ResumeParseRetryRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue(
        operation_type="resume_parse",
        payload=payload.model_dump(),
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="resume-profile-v1",
        progress_total=1,
    )


@router.post("/interview-prep", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_interview_prep(
    payload: InterviewPrepRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    try:
        guide = interview_repository.create_prep_guide(db, identity, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    response = _enqueue(
        operation_type="interview_prep",
        payload={"guide_id": guide.id},
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="interview-prep-v1",
        progress_total=1,
    )
    existing_guide = db.scalar(
        select(InterviewPrepGuide).where(InterviewPrepGuide.operation_id == response.id)
    )
    if existing_guide is not None and existing_guide.id != guide.id:
        db.delete(guide)
    else:
        interview_repository.link_prep_operation(guide, response.id)
    db.commit()
    return response


def _enqueue_application_material(
    material_type: str,
    payload: TailoredResumeGenerationRequest | CoverLetterGenerationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None,
    db: Session,
    identity: AuthenticatedIdentity,
) -> ManagedOperationResponse:
    try:
        version = material_repository.create_generation_version(db, identity, material_type, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    response = _enqueue(
        operation_type="application_material_generation",
        payload={"material_version_id": version.id},
        request=request,
        background_tasks=background_tasks,
        db=db,
        identity=identity,
        idempotency_key=idempotency_key,
        provider="openai",
        model_or_actor=request.app.state.runtime.openai_model,
        prompt_version="application-materials-v1",
        progress_total=1,
    )
    existing = db.scalar(
        select(GeneratedApplicationMaterialVersion).where(
            GeneratedApplicationMaterialVersion.operation_id == response.id
        )
    )
    if existing is not None and existing.id != version.id:
        db.delete(version)
    else:
        material_repository.link_operation(version, response.id)
    db.commit()
    return response


@router.post("/tailored-resume", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_tailored_resume(
    payload: TailoredResumeGenerationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue_application_material(
        "tailored_resume", payload, request, background_tasks, idempotency_key, db, identity
    )


@router.post("/cover-letter", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_cover_letter(
    payload: CoverLetterGenerationRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    return _enqueue_application_material(
        "cover_letter", payload, request, background_tasks, idempotency_key, db, identity
    )


@router.get("", response_model=ManagedOperationListResponse)
def list_managed_operations(
    operation_status: str | None = Query(default=None, alias="status"),
    operation_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationListResponse:
    if operation_status and operation_status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invalid operation status.")
    return ManagedOperationListResponse(
        operations=repository.list_operations(
            db,
            identity,
            operation_status=operation_status,
            operation_type=operation_type,
            limit=limit,
        )
    )


@router.get("/summary", response_model=ManagedOperationSummaryResponse)
def managed_operation_summary(
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationSummaryResponse:
    return ManagedOperationSummaryResponse.model_validate(repository.summarize_operations(db, identity))


def _owned_operation(db: Session, identity: AuthenticatedIdentity, operation_id: int) -> ManagedOperation:
    operation = repository.get_operation_for_identity(db, identity, operation_id)
    if operation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operation not found.")
    return operation


@router.get("/{operation_id}", response_model=ManagedOperationResponse)
def get_managed_operation(
    operation_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperation:
    return _owned_operation(db, identity, operation_id)


@router.post("/{operation_id}/retry", response_model=ManagedOperationResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_managed_operation(
    operation_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    operation = _owned_operation(db, identity, operation_id)
    if operation.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed or cancelled operations can retry.")
    if operation.attempt_count >= operation.max_attempts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This operation reached its retry limit.")
    enforce_provider_rate_limit(request, identity, feature=f"{operation.operation_type}_retry")
    repository.queue_retry(operation)
    db.commit()
    db.refresh(operation)
    background_tasks.add_task(
        execute_operation,
        session_factory_for(db),
        operation.id,
        _handlers(request),
    )
    return ManagedOperationResponse.model_validate(operation)


@router.post("/{operation_id}/cancel", response_model=ManagedOperationResponse)
def cancel_managed_operation(
    operation_id: int,
    db: Session = Depends(get_db_session),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
) -> ManagedOperationResponse:
    operation = _owned_operation(db, identity, operation_id)
    if operation.status in TERMINAL_STATUSES:
        return ManagedOperationResponse.model_validate(operation)
    repository.request_cancel(operation)
    db.commit()
    db.refresh(operation)
    return ManagedOperationResponse.model_validate(operation)

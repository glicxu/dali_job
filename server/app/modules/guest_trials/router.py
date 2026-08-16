from __future__ import annotations

from typing import cast
import socket
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.provider_ops import run_provider_call
from app.db.session import get_db_session
from app.modules.auth.dependencies import AuthenticatedIdentity, get_current_identity
from app.modules.documents.storage import (
    extract_redacted_text,
    normalized_content_type,
    read_supported_upload,
    safe_file_name,
    sha256_hex,
)
from app.modules.guest_trials.dependencies import get_current_guest_trial
from app.modules.guest_trials.models import GuestDocument, GuestResumeProfile, GuestSearchCriterion, GuestTrial
from app.modules.guest_trials.matching import (
    begin_cached_match,
    claim_cached_match,
    match_status,
    require_ready_inputs,
    run_cached_profile_match,
)
from app.modules.guest_trials.schemas import (
    GuestCriteriaResponse,
    GuestCriteriaUpdateRequest,
    GuestProfileResponse,
    GuestProfileUpdateRequest,
    GuestMatchStatusResponse,
    GuestResumeImportResponse,
    GuestTrialCreateResponse,
    GuestTrialCurrentResponse,
    GuestClaimRequest,
    GuestClaimResponse,
)
from app.modules.guest_trials.service import (
    create_guest_trial,
    delete_guest_trial,
    get_guest_criteria,
    get_guest_document,
    get_guest_profile,
    put_guest_criteria,
    put_guest_document,
    put_guest_profile,
    record_guest_document_parse,
    claim_guest_trial,
)
from app.modules.guest_trials.storage import delete_guest_document_file, write_guest_document
from app.modules.guest_trials.rate_limit import enforce_guest_creation_limit, enforce_guest_parse_limit
from app.modules.profiles.resume_import import OpenAIResumeProfileParser, ResumeProfileParser
from app.modules.matching_v2.extraction import CandidateProfileExtractor
from app.modules.matching_v2.qualification import QualificationMatcher
from app.modules.matching_v2.router import get_candidate_profile_extractor, get_qualification_matcher
from app.modules.profiles.readiness import evaluate_profile_readiness
from app.modules.profiles.schemas import ProfileReadinessResponse, ResumeData
from app.modules.operations.service import session_factory_for

router = APIRouter(prefix="/guest-trials", tags=["guest-trials"])


class LazyGuestResumeParser:
    def __init__(self, model: str) -> None:
        self.model = model
        self._delegate: OpenAIResumeProfileParser | None = None

    def parse(self, resume_text: str) -> ResumeData:
        if self._delegate is None:
            self._delegate = OpenAIResumeProfileParser(model=self.model)
        return self._delegate.parse(resume_text)


def get_guest_resume_parser(request: Request) -> ResumeProfileParser:
    return cast(ResumeProfileParser, LazyGuestResumeParser(request.app.state.runtime.openai_model))


def _profile_response(profile: GuestResumeProfile) -> GuestProfileResponse:
    resume_data = ResumeData.model_validate(profile.resume_data)
    return GuestProfileResponse(
        resume_data=resume_data,
        readiness=evaluate_profile_readiness(resume_data),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _criteria_response(criterion: GuestSearchCriterion) -> GuestCriteriaResponse:
    return GuestCriteriaResponse(
        keyword=criterion.keyword,
        location=criterion.location,
        created_at=criterion.created_at,
        updated_at=criterion.updated_at,
    )


def _resume_import_response(document: GuestDocument) -> GuestResumeImportResponse:
    suggestions = ResumeData.model_validate(document.parse_suggestions or {})
    warning = None
    if document.parse_status == "failed":
        warning = "Resume analysis is temporarily unavailable. Retry or confirm your profile manually."
    elif document.parse_status == "pending":
        warning = "Resume analysis has not completed. Retry or confirm your profile manually."
    return GuestResumeImportResponse(
        document_id=document.id,
        file_name=document.file_name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        extracted_text_preview=document.extracted_text[:2000],
        parse_status=document.parse_status,
        suggestions=suggestions,
        parse_warning=warning,
    )


def _parse_document(
    request: Request,
    db: Session,
    trial: GuestTrial,
    document: GuestDocument,
    parser: ResumeProfileParser,
) -> GuestDocument:
    identity = AuthenticatedIdentity(
        external_user_id=f"guest:{trial.public_id}",
        email="guest@invalid.local",
        display_name="Guest trial",
        provider="guest",
    )
    try:
        suggestions = run_provider_call(
            request,
            identity,
            provider="openai",
            feature="guest_resume_profile_parse",
            operation=lambda: parser.parse(document.extracted_text),
        )
    except HTTPException as exc:
        return record_guest_document_parse(
            db,
            document,
            suggestions=None,
            provenance={
                "parser_version": "resume-parser-v1",
                "provider": "openai",
                "model": request.app.state.runtime.openai_model,
                "outcome": "failed",
                "failure_code": f"http_{exc.status_code}",
            },
        )
    return record_guest_document_parse(
        db,
        document,
        suggestions=suggestions.model_dump(),
        provenance={
            "parser_version": "resume-parser-v1",
            "provider": "openai",
            "model": request.app.state.runtime.openai_model,
            "outcome": "succeeded",
        },
    )


@router.post("", response_model=GuestTrialCreateResponse, status_code=status.HTTP_201_CREATED)
def create_trial(request: Request, db: Session = Depends(get_db_session)) -> GuestTrialCreateResponse:
    enforce_guest_creation_limit(request)
    created = create_guest_trial(db)
    return GuestTrialCreateResponse(
        public_id=created.trial.public_id,
        guest_secret=created.secret,
        guest_credential=created.credential,
        status=created.trial.status,
        expires_at=created.trial.expires_at,
    )


@router.post("/claim", response_model=GuestClaimResponse)
def claim_trial_for_current_account(
    payload: GuestClaimRequest,
    identity: AuthenticatedIdentity = Depends(get_current_identity),
    db: Session = Depends(get_db_session),
) -> GuestClaimResponse:
    try:
        claimed = claim_guest_trial(db, credential=payload.guest_credential, identity=identity)
    except ValueError as exc:
        code = str(exc)
        status_code = {
            "INVALID_GUEST_CREDENTIAL": status.HTTP_401_UNAUTHORIZED,
            "GUEST_TRIAL_ALREADY_CLAIMED": status.HTTP_409_CONFLICT,
            "GUEST_RESULT_NOT_READY": status.HTTP_409_CONFLICT,
            "GUEST_ARTIFACTS_UNAVAILABLE": status.HTTP_409_CONFLICT,
            "GUEST_CLAIM_MAPPING_UNAVAILABLE": status.HTTP_409_CONFLICT,
        }.get(code, status.HTTP_409_CONFLICT)
        raise HTTPException(status_code=status_code, detail={"code": code}) from exc
    return GuestClaimResponse(
        status="claimed",
        resume_profile_id=claimed.resume_profile_id,
        search_criterion_id=claimed.search_criterion_id,
        candidate_profile_id=claimed.candidate_profile_id,
        qualification_assessment_id=claimed.qualification_assessment_id,
    )


@router.get("/current", response_model=GuestTrialCurrentResponse)
def get_current_trial(
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> GuestTrialCurrentResponse:
    profile = get_guest_profile(db, trial)
    criterion = get_guest_criteria(db, trial)
    document = get_guest_document(db, trial)
    return GuestTrialCurrentResponse(
        public_id=trial.public_id,
        status=trial.status,
        provider_search_state=trial.provider_search_state,
        expires_at=trial.expires_at,
        profile=_profile_response(profile) if profile else None,
        criteria=_criteria_response(criterion) if criterion else None,
        resume_import=_resume_import_response(document) if document else None,
    )


@router.post("/current/resume-import", response_model=GuestResumeImportResponse)
async def import_current_resume(
    request: Request,
    file: UploadFile = File(...),
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
    parser: ResumeProfileParser = Depends(get_guest_resume_parser),
) -> GuestResumeImportResponse:
    content = await read_supported_upload(file)
    file_name = safe_file_name(file.filename)
    content_type = normalized_content_type(file.content_type)
    extracted_text = extract_redacted_text(content, content_type)
    if not extracted_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No resume text could be extracted.")
    storage_root = request.app.state.runtime.document_storage_dir
    storage_path = write_guest_document(storage_root, trial.public_id, content, file_name)
    document, previous_storage_path = put_guest_document(
        db,
        trial,
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256_hex(content),
        storage_path=storage_path,
        extracted_text=extracted_text,
    )
    if previous_storage_path and previous_storage_path != storage_path:
        delete_guest_document_file(storage_root, previous_storage_path)
    try:
        enforce_guest_parse_limit(request, trial.public_id)
    except HTTPException:
        return _resume_import_response(document)
    return _resume_import_response(_parse_document(request, db, trial, document, parser))


@router.post("/current/resume-import/retry", response_model=GuestResumeImportResponse)
def retry_current_resume_parse(
    request: Request,
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
    parser: ResumeProfileParser = Depends(get_guest_resume_parser),
) -> GuestResumeImportResponse:
    document = get_guest_document(db, trial)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guest resume upload not found.")
    enforce_guest_parse_limit(request, trial.public_id)
    return _resume_import_response(_parse_document(request, db, trial, document, parser))


@router.put("/current/profile", response_model=GuestProfileResponse)
def update_current_profile(
    payload: GuestProfileUpdateRequest,
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> GuestProfileResponse:
    return _profile_response(put_guest_profile(db, trial, payload))


@router.get("/current/readiness", response_model=ProfileReadinessResponse)
def get_current_readiness(
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> ProfileReadinessResponse:
    profile = get_guest_profile(db, trial)
    return evaluate_profile_readiness(profile.resume_data if profile else ResumeData())


@router.put("/current/criteria", response_model=GuestCriteriaResponse)
def update_current_criteria(
    payload: GuestCriteriaUpdateRequest,
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> GuestCriteriaResponse:
    return _criteria_response(put_guest_criteria(db, trial, payload))


@router.delete("/current", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_trial(
    request: Request,
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> Response:
    deleted = delete_guest_trial(db, trial, storage_root=request.app.state.runtime.document_storage_dir)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The trial could not be safely deleted. Retry shortly.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/current/match", response_model=GuestMatchStatusResponse)
def get_current_match(
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
) -> GuestMatchStatusResponse:
    return match_status(db, trial)


@router.post(
    "/current/match",
    response_model=GuestMatchStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run an immediate guest match",
    description=(
        "Starts an immediate match against the existing cached Job Profile catalog and returns "
        "a pollable operation; no external job query or provider-search allowance is used."
    ),
)
def create_current_match(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    trial: GuestTrial = Depends(get_current_guest_trial),
    db: Session = Depends(get_db_session),
    candidate_extractor: CandidateProfileExtractor = Depends(get_candidate_profile_extractor),
    matcher: QualificationMatcher = Depends(get_qualification_matcher),
) -> GuestMatchStatusResponse:
    normalized_key = (idempotency_key or "").strip()
    if not normalized_key or len(normalized_key) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must contain 1 to 64 characters.",
        )
    existing_status = match_status(db, trial)
    if existing_status.result is not None:
        response.status_code = status.HTTP_200_OK
        return existing_status
    profile, criterion = require_ready_inputs(db, trial)
    operation = begin_cached_match(db, trial, idempotency_key=normalized_key)
    db.commit()
    background_tasks.add_task(
        _execute_guest_match_background,
        session_factory_for(db),
        operation.id,
        request.app.state.runtime.openai_model,
        candidate_extractor,
        matcher,
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return match_status(db, trial)


def _execute_guest_match_background(
    session_factory,
    operation_id: int,
    model_id: str,
    candidate_extractor: CandidateProfileExtractor,
    matcher: QualificationMatcher,
) -> None:
    worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
    with session_factory() as db:
        from app.modules.guest_trials.models import GuestMatchOperation

        operation = db.get(GuestMatchOperation, operation_id)
        if operation is None or not claim_cached_match(db, operation, worker_id=worker_id):
            db.commit()
            return
        trial = db.get(GuestTrial, operation.guest_trial_id)
        if trial is None:
            db.commit()
            return
        profile, criterion = require_ready_inputs(db, trial)
        db.commit()
        try:
            run_cached_profile_match(
                model_id,
                db,
                trial,
                operation,
                profile,
                criterion,
                candidate_extractor,
                matcher,
            )
        except HTTPException:
            db.commit()
            return
        db.commit()

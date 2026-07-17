from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.modules.applications.models import Application, ApplicationEvent
from app.modules.applications.schemas import ApplicationJobSummary
from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.interviews.models import Interview, InterviewNote, InterviewPrepGuide, utc_now
from app.modules.interviews.schemas import (
    InterviewCreateRequest,
    InterviewNoteCreateRequest,
    InterviewPrepOutput,
    InterviewPrepRequest,
    InterviewUpdateRequest,
)
from app.modules.jobs import repository as job_repository
from app.modules.profiles import repository as profile_repository
from app.modules.profiles.repository import ensure_account_for_identity


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _owner_ids(db: Session, identity: AuthenticatedIdentity) -> tuple[int, int]:
    user, workspace = ensure_account_for_identity(db, identity)
    return workspace.id, user.id


def _job_summary(db: Session, identity: AuthenticatedIdentity, application: Application) -> dict | None:
    if application.user_job_id is None:
        return None
    user_job = job_repository.get_user_job_for_identity(db, identity, application.user_job_id)
    if user_job is None:
        return None
    job = job_repository.job_response_for_identity(db, identity, user_job)
    job_data = job.get("job_data") or {}
    return ApplicationJobSummary(
        id=job["id"],
        title=job.get("title") or "",
        company=job.get("company") or "",
        source_url=job.get("source_url"),
        summary=job_data.get("summary") or "",
        work_location=job_data.get("work_location") or "",
        application_deadline=job_data.get("application_deadline") or "",
    ).model_dump()


def _guide_response(guide: InterviewPrepGuide) -> dict:
    return {
        "id": guide.id,
        "interview_id": guide.interview_id,
        "operation_id": guide.operation_id,
        "resume_profile_id": guide.resume_profile_id,
        "source_warnings": list(guide.source_warnings or []),
        "output_data": guide.output_data,
        "provider": guide.provider,
        "model_name": guide.model_name,
        "prompt_version": guide.prompt_version,
        "schema_version": guide.schema_version,
        "provider_execution_reference": guide.provider_execution_reference,
        "created_at": guide.created_at,
        "completed_at": guide.completed_at,
    }


def _interview_response(
    db: Session,
    identity: AuthenticatedIdentity,
    interview: Interview,
    *,
    detail: bool = False,
) -> dict:
    application = db.get(Application, interview.application_id)
    payload = {
        "id": interview.id,
        "workspace_id": interview.workspace_id,
        "user_id": interview.user_id,
        "application_id": interview.application_id,
        "interview_type": interview.interview_type,
        "status": interview.status,
        "stage": interview.stage,
        "scheduled_at": interview.scheduled_at,
        "timezone": interview.timezone,
        "duration_minutes": interview.duration_minutes,
        "location_or_url": interview.location_or_url,
        "outcome": interview.outcome,
        "private_notes": interview.private_notes,
        "job": _job_summary(db, identity, application) if application else None,
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
    }
    if detail:
        payload["notes"] = [
            note
            for note in db.scalars(
                select(InterviewNote)
                .where(InterviewNote.interview_id == interview.id)
                .order_by(desc(InterviewNote.created_at))
            )
        ]
        payload["prep_guides"] = [
            _guide_response(guide)
            for guide in db.scalars(
                select(InterviewPrepGuide)
                .where(InterviewPrepGuide.interview_id == interview.id)
                .order_by(desc(InterviewPrepGuide.created_at))
            )
        ]
    return payload


def get_interview_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    interview_id: int,
) -> Interview | None:
    workspace_id, user_id = _owner_ids(db, identity)
    return db.scalar(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.workspace_id == workspace_id,
            Interview.user_id == user_id,
        )
    )


def list_interviews(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    application_id: int | None = None,
) -> list[dict]:
    workspace_id, user_id = _owner_ids(db, identity)
    query = select(Interview).where(
        Interview.workspace_id == workspace_id,
        Interview.user_id == user_id,
    )
    if application_id is not None:
        query = query.where(Interview.application_id == application_id)
    interviews = db.scalars(
        query.order_by(Interview.scheduled_at.is_(None), Interview.scheduled_at.asc(), Interview.created_at.desc())
    )
    return [_interview_response(db, identity, interview) for interview in interviews]


def interview_detail(db: Session, identity: AuthenticatedIdentity, interview: Interview) -> dict:
    return _interview_response(db, identity, interview, detail=True)


def create_interview(
    db: Session,
    identity: AuthenticatedIdentity,
    payload: InterviewCreateRequest,
) -> dict:
    workspace_id, user_id = _owner_ids(db, identity)
    application = db.scalar(
        select(Application).where(
            Application.id == payload.application_id,
            Application.workspace_id == workspace_id,
            Application.user_id == user_id,
        )
    )
    if application is None:
        raise ValueError("Application not found.")
    if application.archived_at is not None:
        raise ValueError("Restore the application before scheduling an interview.")
    interview = Interview(
        workspace_id=workspace_id,
        user_id=user_id,
        application_id=application.id,
        interview_type=payload.interview_type,
        stage=payload.stage,
        scheduled_at=payload.scheduled_at,
        timezone=_clean(payload.timezone) or identity.timezone,
        duration_minutes=payload.duration_minutes,
        location_or_url=_clean(payload.location_or_url),
        private_notes=_clean(payload.private_notes),
    )
    db.add(interview)
    db.flush()
    db.add(
        ApplicationEvent(
            application_id=application.id,
            event_type="interview_scheduled",
            source="user",
            payload={"interview_id": interview.id, "interview_type": interview.interview_type},
        )
    )
    db.flush()
    return interview_detail(db, identity, interview)


def update_interview(
    db: Session,
    identity: AuthenticatedIdentity,
    interview: Interview,
    payload: InterviewUpdateRequest,
) -> dict:
    changes = payload.model_dump(exclude_unset=True)
    if "timezone" in changes:
        changes["timezone"] = _clean(changes["timezone"]) or identity.timezone
    for field in ("location_or_url", "private_notes"):
        if field in changes:
            changes[field] = _clean(changes[field])
    for field, value in changes.items():
        setattr(interview, field, value)
    db.flush()
    db.add(
        ApplicationEvent(
            application_id=interview.application_id,
            event_type="interview_updated",
            source="user",
            payload={"interview_id": interview.id, "fields": sorted(changes)},
        )
    )
    db.flush()
    return interview_detail(db, identity, interview)


def add_interview_note(
    db: Session,
    interview: Interview,
    payload: InterviewNoteCreateRequest,
) -> InterviewNote:
    note = InterviewNote(interview_id=interview.id, body=payload.body.strip())
    db.add(note)
    db.flush()
    db.add(
        ApplicationEvent(
            application_id=interview.application_id,
            event_type="interview_note_added",
            source="user",
            payload={"interview_id": interview.id, "note_id": note.id},
        )
    )
    db.flush()
    return note


def create_prep_guide(
    db: Session,
    identity: AuthenticatedIdentity,
    payload: InterviewPrepRequest,
) -> InterviewPrepGuide:
    interview = get_interview_for_identity(db, identity, payload.interview_id)
    if interview is None:
        raise ValueError("Interview not found.")
    resume_profile = profile_repository.get_resume_profile_for_identity(db, identity, payload.resume_profile_id)
    if resume_profile is None:
        raise ValueError("Resume profile not found.")
    application = db.get(Application, interview.application_id)
    job_snapshot: dict = {}
    if application and application.user_job_id:
        user_job = job_repository.get_user_job_for_identity(db, identity, application.user_job_id)
        if user_job is not None:
            job = job_repository.job_response_for_identity(db, identity, user_job)
            job_snapshot = {
                "title": job.get("title") or "",
                "company": job.get("company") or "",
                "source_url": job.get("source_url"),
                "raw_description_text": job.get("raw_description_text") or "",
                "job_data": job.get("job_data") or {},
            }

    resume_snapshot = dict(resume_profile.resume_data or {})
    warnings: list[str] = []
    if not any(resume_snapshot.get(field) for field in ("experience", "skills", "projects")):
        warnings.append("The selected resume has limited experience, skills, and project evidence.")
    if not job_snapshot.get("job_data"):
        warnings.append("Structured job data is unavailable; preparation uses the saved raw job description.")
    if not _clean(payload.company_notes):
        warnings.append("No company notes were provided, so company-specific preparation is limited.")

    workspace_id, user_id = _owner_ids(db, identity)
    guide = InterviewPrepGuide(
        workspace_id=workspace_id,
        user_id=user_id,
        interview_id=interview.id,
        resume_profile_id=resume_profile.id,
        resume_data_snapshot=resume_snapshot,
        job_data_snapshot=job_snapshot,
        company_notes_snapshot=_clean(payload.company_notes),
        source_warnings=warnings,
    )
    db.add(guide)
    db.flush()
    return guide


def get_prep_guide_for_identity(
    db: Session,
    identity: AuthenticatedIdentity,
    guide_id: int,
) -> InterviewPrepGuide | None:
    workspace_id, user_id = _owner_ids(db, identity)
    return db.scalar(
        select(InterviewPrepGuide).where(
            InterviewPrepGuide.id == guide_id,
            InterviewPrepGuide.workspace_id == workspace_id,
            InterviewPrepGuide.user_id == user_id,
        )
    )


def link_prep_operation(guide: InterviewPrepGuide, operation_id: int) -> None:
    guide.operation_id = operation_id


def complete_prep_guide(
    guide: InterviewPrepGuide,
    output: InterviewPrepOutput,
    *,
    model_name: str,
    provider_execution_reference: str | None = None,
) -> dict:
    guide.output_data = output.model_dump()
    guide.model_name = model_name
    guide.provider_execution_reference = provider_execution_reference
    guide.completed_at = utc_now()
    return _guide_response(guide)

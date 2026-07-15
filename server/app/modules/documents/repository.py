from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents.models import Document, DocumentVersion
from app.modules.jobs.models import JobResumeMatch
from app.modules.profiles.models import ResumeProfile
from app.modules.profiles.repository import ensure_account_for_identity


def _latest_version(db: Session, document_id: int) -> DocumentVersion | None:
    return db.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(desc(DocumentVersion.version_number))
        .limit(1)
    )


def _document_response(document: Document, latest: DocumentVersion | None) -> dict:
    return {
        "id": document.id,
        "workspace_id": document.workspace_id,
        "user_id": document.user_id,
        "title": document.title,
        "document_type": document.document_type,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "latest_version": None
        if latest is None
        else {
            "id": latest.id,
            "document_id": latest.document_id,
            "version_number": latest.version_number,
            "file_name": latest.file_name,
            "content_type": latest.content_type,
            "size_bytes": latest.size_bytes,
            "sha256": latest.sha256,
            "extracted_text_available": bool(latest.extracted_text),
            "created_at": latest.created_at,
        },
    }


def list_documents(db: Session, identity: AuthenticatedIdentity) -> list[dict]:
    user, workspace = ensure_account_for_identity(db, identity)
    documents = db.scalars(
        select(Document)
        .where(
            Document.workspace_id == workspace.id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
        .order_by(desc(Document.updated_at))
    ).all()
    return [_document_response(document, _latest_version(db, document.id)) for document in documents]


def get_document_for_identity(db: Session, identity: AuthenticatedIdentity, document_id: int) -> Document | None:
    user, workspace = ensure_account_for_identity(db, identity)
    return db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace.id,
            Document.user_id == user.id,
            Document.deleted_at.is_(None),
        )
    )


def get_latest_version(db: Session, document: Document) -> DocumentVersion | None:
    return _latest_version(db, document.id)


def create_document_with_version(
    db: Session,
    identity: AuthenticatedIdentity,
    *,
    title: str,
    document_type: str,
    file_name: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    storage_path: str,
    extracted_text: str | None,
) -> dict:
    user, workspace = ensure_account_for_identity(db, identity)
    document = Document(
        workspace_id=workspace.id,
        user_id=user.id,
        title=title,
        document_type=document_type,
    )
    db.add(document)
    db.flush()
    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        file_name=file_name,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        storage_path=storage_path,
        extracted_text=extracted_text,
    )
    db.add(version)
    db.flush()
    return _document_response(document, version)


def document_dependencies(db: Session, document: Document) -> list[dict]:
    profile_count = db.scalar(
        select(func.count(ResumeProfile.id)).where(
            ResumeProfile.source_document_id == document.id,
            ResumeProfile.deleted_at.is_(None),
        )
    ) or 0
    match_count = db.scalar(
        select(func.count(JobResumeMatch.id)).where(JobResumeMatch.resume_document_id == document.id)
    ) or 0
    dependencies: list[dict] = []
    if profile_count:
        dependencies.append(
            {
                "dependency_type": "resume_profile",
                "dependency_count": profile_count,
                "message": f"{profile_count} active resume profile{'s' if profile_count != 1 else ''} use this document.",
            }
        )
    if match_count:
        dependencies.append(
            {
                "dependency_type": "match_history",
                "dependency_count": match_count,
                "message": f"{match_count} historical match{'es' if match_count != 1 else ''} reference this document.",
            }
        )
    return dependencies


def soft_delete_document(db: Session, document: Document) -> None:
    from app.modules.documents.models import utc_now

    document.deleted_at = utc_now()
    db.flush()

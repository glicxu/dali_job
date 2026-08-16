from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from DaliCommonLib.dali_db_man import DbMan  # noqa: E402

from app.config import load_runtime_config  # noqa: E402
from app.db.base import Base  # noqa: E402,F401
from app.modules.documents.models import Document, DocumentVersion  # noqa: E402
from app.modules.documents.storage import extract_redacted_text  # noqa: E402
from app.modules.matching_v2.canonical import (  # noqa: E402
    CANONICALIZATION_VERSION,
    build_evidence_spans,
    canonicalize_text,
)
from app.modules.matching_v2.extraction import (  # noqa: E402
    OpenAICandidateProfileExtractor,
    validate_candidate_extraction,
)
from app.modules.matching_v2.models import CandidateProfileVersion  # noqa: E402
from app.modules.matching_v2.repositories import (  # noqa: E402
    ArtifactOwner,
    SpanInput,
    create_or_get_candidate_profile,
    create_or_get_canonical_source,
)
from app.modules.profiles.models import ResumeProfile  # noqa: E402
from app.modules.profiles.resume_import import resume_privacy_risks  # noqa: E402
from app.modules.matching_v2.schemas import CandidateExtractionResponse  # noqa: E402
from db_common import get_schema_name  # noqa: E402


DEFAULT_PREFIX = "[EVAL internal 20260816]"
TEXT_EXTRACTION_VERSION = "document-layout-redacted.v3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay the protected internal resume corpus through Candidate Profile V3."
    )
    parser.add_argument("-c", "--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--title-prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--resume-id", type=int, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runtime = load_runtime_config(args.config)
    factory = sessionmaker(
        bind=DbMan.get_db_engine(schema=get_schema_name()),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    with factory() as db:
        query = select(ResumeProfile).where(
            ResumeProfile.deleted_at.is_(None),
            ResumeProfile.title.startswith(args.title_prefix),
        )
        if args.resume_id:
            query = query.where(ResumeProfile.id.in_(args.resume_id))
        resumes = list(db.scalars(query.order_by(ResumeProfile.id)).all())
    if not resumes:
        raise RuntimeError("No protected evaluation resumes matched the selection.")

    extractor = OpenAICandidateProfileExtractor(runtime.openai_model)
    results = []
    for ordinal, resume in enumerate(resumes, start=1):
        started = time.monotonic()
        try:
            row = _replay_one(factory, runtime, extractor, resume.id)
            row["status"] = "succeeded"
        except Exception as exc:
            row = {
                "resume_profile_id": resume.id,
                "resume_title": resume.title,
                "status": "failed",
                "error_type": type(exc).__name__,
                "validation_diagnostics": _safe_validation_diagnostics(exc),
            }
        row["latency_ms"] = round((time.monotonic() - started) * 1000, 2)
        results.append(row)
        _write_report(args.output, runtime.openai_model, results)
        print(f"[{ordinal}/{len(resumes)}] resume_id={resume.id} status={row['status']}", flush=True)
    return 0 if all(row["status"] == "succeeded" for row in results) else 1


def _replay_one(factory, runtime, extractor, resume_id: int) -> dict:
    with factory() as db:
        resume = db.get(ResumeProfile, resume_id)
        if resume is None or resume.source_document_version_id is None:
            raise RuntimeError("Evaluation resume has no source document version.")
        version = db.get(DocumentVersion, resume.source_document_version_id)
        document = db.get(Document, version.document_id) if version is not None else None
        if version is None or document is None:
            raise RuntimeError("Evaluation source document is unavailable.")
        storage_path = _validated_storage_path(runtime.document_storage_dir, version.storage_path)
        content = storage_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != version.sha256:
            raise RuntimeError("Evaluation source document hash does not match its immutable version.")
        redacted = extract_redacted_text(content, version.content_type)
        if redacted is None:
            raise RuntimeError("Evaluation source document type is unsupported.")
        privacy_risks = list(resume_privacy_risks(redacted))
        if privacy_risks:
            raise RuntimeError("Evaluation source did not pass the privacy gate.")
        canonical_text = canonicalize_text(redacted)
        spans = build_evidence_spans(canonical_text, source_prefix=f"resume_{resume.id}")
        owner = ArtifactOwner.authenticated(
            workspace_id=document.workspace_id,
            user_id=document.user_id,
        )
        source = create_or_get_canonical_source(
            db,
            owner=owner,
            source_type="resume",
            canonical_text=canonical_text,
            text_extraction_version=TEXT_EXTRACTION_VERSION,
            canonicalization_version=CANONICALIZATION_VERSION,
            resume_profile_id=resume.id,
            document_version_id=version.id,
            spans=[
                SpanInput(
                    span_id=span.span_id,
                    section=span.section,
                    start_utf8_byte=span.start_utf8_byte,
                    end_utf8_byte=span.end_utf8_byte,
                    excerpt=span.excerpt,
                )
                for span in spans
            ],
        )
        source_id = source.id
        source_public_id = source.public_id
        old_profile = db.scalar(
            select(CandidateProfileVersion)
            .where(
                CandidateProfileVersion.resume_profile_id == resume.id,
                CandidateProfileVersion.prompt_version == "candidate-extract.v1",
            )
            .order_by(CandidateProfileVersion.created_at.desc())
            .limit(1)
        )
        old_summary = _profile_summary(old_profile.artifact) if old_profile is not None else None
        prior_current = db.scalar(
            select(CandidateProfileVersion)
            .where(
                CandidateProfileVersion.canonical_source_id == source.id,
                CandidateProfileVersion.prompt_version == "candidate-extract.v3",
                CandidateProfileVersion.model_id == runtime.openai_model,
            )
            .order_by(CandidateProfileVersion.created_at.desc())
            .limit(1)
        )
        prior_current_artifact = (
            dict(prior_current.artifact) if prior_current is not None else None
        )
        prior_current_reference = (
            prior_current.provider_execution_reference if prior_current is not None else None
        )
        db.commit()

    if prior_current_artifact is not None:
        artifact = validate_candidate_extraction(
            CandidateExtractionResponse.model_validate(prior_current_artifact),
            {span.span_id for span in spans},
            evidence_by_ref={span.span_id: span.excerpt for span in spans},
        )
        model_id = runtime.openai_model
        provider_execution_reference = prior_current_reference
        reused_current_provider_output = True
    else:
        extraction = extractor.extract(spans)
        artifact = extraction.artifact
        model_id = extraction.model_id
        provider_execution_reference = extraction.provider_execution_reference
        reused_current_provider_output = False
    with factory() as db:
        source = db.get(type(source), source_id)
        profile = create_or_get_candidate_profile(
            db,
            source=source,
            artifact=artifact,
            model_id=model_id,
            provider_execution_reference=provider_execution_reference,
            resume_profile_id=resume_id,
        )
        db.commit()
        profile_id = profile.public_id

    return {
        "resume_profile_id": resume_id,
        "resume_title": resume.title,
        "document_file_name": version.file_name,
        "document_type": version.content_type,
        "source_id": source_public_id,
        "candidate_profile_id": profile_id,
        "prompt_version": "candidate-extract.v3",
        "response_schema_version": "candidate-extract-response.v3",
        "semantic_validator_version": "matching-semantic-validator.v2",
        "reused_current_provider_output": reused_current_provider_output,
        "privacy_risks": privacy_risks,
        "canonical_character_count": len(canonical_text),
        "span_count": len(spans),
        "section_counts": dict(sorted(Counter(span.section for span in spans).items())),
        "v1": old_summary,
        "v3": _profile_summary(artifact.model_dump(mode="json")),
    }


def _profile_summary(artifact: dict) -> dict:
    profiles = artifact.get("career_profiles") or []
    primary_ref = artifact.get("recommended_primary_career_profile_ref")
    primary = next((item for item in profiles if item.get("local_ref") == primary_ref), None)
    return {
        "fact_counts": {
            key: len(artifact.get(key) or [])
            for key in (
                "skills", "experience", "projects", "education", "certifications", "publications",
                "awards", "patents", "languages",
            )
        },
        "career_profile_count": len(profiles),
        "primary": {
            key: primary.get(key) for key in ("role_family", "track", "level", "confidence")
        } if primary else None,
        "quality": artifact.get("quality"),
    }


def _safe_validation_diagnostics(exc: Exception) -> list[dict[str, object]]:
    current: BaseException | None = exc
    diagnostics: list[dict[str, object]] = []
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(diagnostics) < 12:
        seen.add(id(current))
        if isinstance(current, ValidationError):
            diagnostics.extend({
                "error_type": "ValidationError",
                "path": [str(part) for part in error.get("loc", ())],
                "validation_type": error.get("type", "unknown"),
                "message": error.get("msg", "schema validation failed"),
            } for error in current.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )[: 12 - len(diagnostics)])
        elif isinstance(current, ValueError):
            message = str(current)
            safe_message = (
                "publication title lacks explicit cited support"
                if "publication title" in message.casefold()
                else "candidate semantic validation failed"
            )
            diagnostics.append({"error_type": type(current).__name__, "message": safe_message})
        current = current.__cause__
    return diagnostics


def _validated_storage_path(storage_root: str, stored_path: str) -> Path:
    root = Path(storage_root).expanduser().resolve()
    path = Path(stored_path).expanduser().resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise RuntimeError("Evaluation source path is outside the configured document root.")
    return path


def _write_report(output_value: str, model_id: str, results: list[dict]) -> None:
    output = Path(output_value).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "candidate-profile-replay-report.v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model_id,
        "prompt_version": "candidate-extract.v3",
        "text_extraction_version": TEXT_EXTRACTION_VERSION,
        "results": results,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

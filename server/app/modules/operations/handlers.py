from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder

from app.modules.auth.dependencies import AuthenticatedIdentity
from app.modules.documents import repository as document_repository
from app.modules.job_search.apify_indeed import APIFY_INDEED_ACTOR_ID, ApifyIndeedClient
from app.modules.job_search import router as job_search_router
from app.modules.job_search.service import JobSearchProvider
from app.modules.interviews import repository as interview_repository
from app.modules.interviews.service import OpenAIInterviewPrepGenerator
from app.modules.materials import repository as material_repository
from app.modules.materials.models import GeneratedApplicationMaterial
from app.modules.materials.service import OpenAIMaterialGenerator
from app.modules.jobs import router as jobs_router
from app.modules.jobs.schemas import (
    IndeedJobSearchImportRequest,
    IndeedJobSearchRequest,
    JobImportRequest,
    JobListDiscoverRequest,
    JobListImportRequest,
)
from app.modules.jobs.service import OpenAIJobDescriptionParser
from app.modules.operations.service import OperationContext, OperationHandler
from app.modules.profiles.resume_import import OpenAIResumeProfileParser, ResumeImportResponse
from app.modules.resume_job_match import router as match_router
from app.modules.resume_job_match.schemas import BulkSavedJobMatchRequest, ResumeJobMatchRequest
from app.modules.resume_job_match.service import OpenAIResumeJobMatcher


class _UnusedProvider:
    def parse(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Job parsing was not requested for this operation.")

    def compare(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Resume matching was not requested for this operation.")


class _LazyJobDescriptionParser:
    def __init__(self, model: str) -> None:
        self._model = model
        self._delegate: OpenAIJobDescriptionParser | None = None

    def parse(self, raw_description_text: str):
        if self._delegate is None:
            self._delegate = OpenAIJobDescriptionParser(model=self._model)
        return self._delegate.parse(raw_description_text)


class _LazyResumeJobMatcher:
    def __init__(self, model: str) -> None:
        self._model = model
        self._delegate: OpenAIResumeJobMatcher | None = None

    def compare(self, request):
        if self._delegate is None:
            self._delegate = OpenAIResumeJobMatcher(model=self._model)
        return self._delegate.compare(request)


def _worker_request(app: Any, path: str) -> Request:
    request = Request(
        {
            "type": "http",
            "app": app,
            "client": ("managed-operation", 0),
            "headers": [],
            "method": "POST",
            "path": path,
        }
    )
    request.state.provider_limit_already_enforced = True
    return request


def build_operation_handlers(app: Any) -> dict[str, OperationHandler]:
    runtime = app.state.runtime

    search_provider: JobSearchProvider = ApifyIndeedClient()

    def job_search(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = IndeedJobSearchRequest.model_validate(raw)
        context.update(0, total=1, message="Searching job listings")
        response = job_search_router.search_indeed_jobs(
            payload=payload,
            request=_worker_request(app, "/operations/job-search"),
            db=db,
            client=search_provider,
            identity=identity,
        )
        context.update(
            1,
            total=1,
            message="Search complete",
            usage={"results": len(response.results)},
        )
        return jsonable_encoder(response)

    def provider_import(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = IndeedJobSearchImportRequest.model_validate(raw)
        total = len(payload.selected_results)
        context.update(0, total=total, message="Importing selected jobs")
        parser = _LazyJobDescriptionParser(model=runtime.openai_model) if payload.run_matching else _UnusedProvider()
        matcher = _LazyResumeJobMatcher(model=runtime.openai_model) if payload.run_matching else _UnusedProvider()
        response = job_search_router.import_indeed_search_results(
            payload=payload,
            parser=parser,
            matcher=matcher,
            db=db,
            identity=identity,
        )
        context.update(
            total,
            total=total,
            message="Import complete",
            usage={"imported": len(response.imported), "failed": len(response.failed)},
        )
        return jsonable_encoder(response)

    def list_discover(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = JobListDiscoverRequest.model_validate(raw)
        context.update(0, total=1, message="Discovering job links")
        response = jobs_router.discover_job_list(
            payload=payload,
            request=_worker_request(app, "/operations/job-list-discover"),
            db=db,
            identity=identity,
        )
        context.update(
            1,
            total=1,
            message="Discovery complete",
            usage={"results": len(response.candidates)},
        )
        return jsonable_encoder(response)

    def list_import(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = JobListImportRequest.model_validate(raw)
        total = len(payload.selected_urls)
        context.update(0, total=total, message="Importing selected jobs")
        parser = _LazyJobDescriptionParser(model=runtime.openai_model) if payload.run_matching else _UnusedProvider()
        matcher = _LazyResumeJobMatcher(model=runtime.openai_model) if payload.run_matching else _UnusedProvider()
        response = jobs_router.import_job_list(
            payload=payload,
            request=_worker_request(app, "/operations/job-list-import"),
            parser=parser,
            matcher=matcher,
            db=db,
            identity=identity,
        )
        context.update(
            total,
            total=total,
            message="Import complete",
            usage={"imported": len(response.imported), "failed": len(response.failed)},
        )
        return jsonable_encoder(response)

    def resume_parse(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        document_id = int(raw["document_id"])
        document = document_repository.get_document_for_identity(db, identity, document_id)
        if document is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume document not found.")
        version = document_repository.get_latest_version(db, document)
        if version is None or not version.extracted_text:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Resume document does not have extracted text available for parsing.",
            )
        context.update(0, total=1, message="Parsing resume")
        suggestions = OpenAIResumeProfileParser(model=runtime.openai_model).parse(version.extracted_text)
        context.update(
            1,
            total=1,
            message="Resume parsed",
            usage={"input_characters": len(version.extracted_text)},
        )
        return jsonable_encoder(
            ResumeImportResponse(
                file_name=version.file_name,
                document_id=document.id,
                document_version_id=version.id,
                extracted_text_preview=version.extracted_text[:2000],
                suggestions=suggestions,
                parse_warning=None,
            )
        )

    def job_draft(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = JobImportRequest.model_validate(raw)
        context.update(0, total=1, message="Analyzing job description")
        response = jobs_router.draft_job_description(
            payload=payload,
            request=_worker_request(app, "/operations/job-draft"),
            parser=_LazyJobDescriptionParser(model=runtime.openai_model),
            db=db,
            identity=identity,
        )
        context.update(1, total=1, message="Job analysis complete")
        return jsonable_encoder(response)

    def job_analyze(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        context.update(0, total=1, message="Analyzing saved job")
        response = jobs_router.analyze_job(
            job_id=int(raw["job_id"]),
            parser=_LazyJobDescriptionParser(model=runtime.openai_model),
            db=db,
            identity=identity,
        )
        context.update(1, total=1, message="Job analysis complete")
        return jsonable_encoder(response)

    def resume_job_match(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = ResumeJobMatchRequest.model_validate(raw)
        context.update(0, total=1, message="Comparing resume and job")
        response = match_router.create_resume_job_match(
            payload=payload,
            request=_worker_request(app, "/operations/resume-job-match"),
            matcher=_LazyResumeJobMatcher(model=runtime.openai_model),
            parser=_LazyJobDescriptionParser(model=runtime.openai_model),
            db=db,
            identity=identity,
        )
        context.update(1, total=1, message="Match complete", usage={"matches": 1})
        return jsonable_encoder(response)

    def bulk_match(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        payload = BulkSavedJobMatchRequest.model_validate(raw)
        total = len(payload.user_job_ids)
        context.update(0, total=total, message="Matching selected jobs")
        response = match_router.create_bulk_saved_job_matches(
            payload=payload,
            matcher=_LazyResumeJobMatcher(model=runtime.openai_model),
            parser=_LazyJobDescriptionParser(model=runtime.openai_model),
            db=db,
            identity=identity,
        )
        context.update(
            total,
            total=total,
            message="Bulk match complete",
            usage={"matched": len(response.matched), "failed": len(response.failed)},
        )
        return jsonable_encoder(response)

    def interview_prep(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        guide = interview_repository.get_prep_guide_for_identity(db, identity, int(raw["guide_id"]))
        if guide is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview prep request not found.")
        context.update(0, total=1, message="Preparing interview guide")
        generated = OpenAIInterviewPrepGenerator(model=runtime.openai_model).generate(
            dict(guide.resume_data_snapshot or {}),
            dict(guide.job_data_snapshot or {}),
            guide.company_notes_snapshot,
            list(guide.source_warnings or []),
        )
        response = interview_repository.complete_prep_guide(
            guide,
            generated.output,
            model_name=generated.model_name,
            provider_execution_reference=generated.provider_execution_reference,
        )
        db.flush()
        context.update(
            1,
            total=1,
            message="Interview guide ready",
            usage={
                "study_priorities": len(generated.output.study_priorities),
                "likely_questions": len(generated.output.likely_questions),
                "input_characters": len(jsonable_encoder(guide.resume_data_snapshot).__str__())
                + len(jsonable_encoder(guide.job_data_snapshot).__str__()),
            },
        )
        return jsonable_encoder(response)

    def application_material(db, identity: AuthenticatedIdentity, raw: dict, context: OperationContext):
        version = material_repository.get_version_for_identity(db, identity, int(raw["material_version_id"]))
        if version is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application material request not found.")
        material = db.get(GeneratedApplicationMaterial, version.material_id)
        if material is None:
            raise RuntimeError("Application material owner record is missing.")
        source_material = None
        if version.source_material_version_id is not None:
            source_version = material_repository.get_version_for_identity(
                db, identity, version.source_material_version_id
            )
            source_material = dict(source_version.content_data or {}) if source_version else None
        context.update(0, total=1, message=f"Generating {material.material_type.replace('_', ' ')}")
        generated = OpenAIMaterialGenerator(model=runtime.openai_model).generate(
            material.material_type,
            dict(version.source_resume_snapshot or {}),
            dict(version.job_snapshot or {}),
            version.request_notes_snapshot,
            source_material,
        )
        content_data = generated.output.model_dump(mode="json")
        material_repository.complete_generation(
            version,
            content_data,
            list(dict.fromkeys([*(generated.warnings or []), *content_data.get("warnings", [])])),
            model_name=generated.model_name,
            provider_execution_reference=generated.provider_execution_reference,
        )
        db.flush()
        context.update(
            1,
            total=1,
            message="Application material ready",
            usage={
                "input_characters": len(str(version.source_resume_snapshot))
                + len(str(version.job_snapshot))
            },
        )
        return jsonable_encoder(material_repository.material_response(db, identity, material))

    return {
        "job_search": job_search,
        "provider_job_import": provider_import,
        "job_list_discover": list_discover,
        "job_list_import": list_import,
        "resume_parse": resume_parse,
        "job_draft": job_draft,
        "job_analyze": job_analyze,
        "resume_job_match": resume_job_match,
        "bulk_resume_job_match": bulk_match,
        "interview_prep": interview_prep,
        "application_material_generation": application_material,
    }


__all__ = ["APIFY_INDEED_ACTOR_ID", "build_operation_handlers"]

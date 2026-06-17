from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.resume_job_match.router import get_resume_job_matcher
from app.modules.resume_job_match.schemas import (
    ResumeJobMatchRequest,
    ResumeJobMatchResponse,
    SupportedRequirement,
    UnsupportedRequirement,
)


class FakeMatcher:
    def compare(self, request: ResumeJobMatchRequest) -> ResumeJobMatchResponse:
        assert "FastAPI" in request.resume_text
        assert "PostgreSQL" in request.job_description_text
        return ResumeJobMatchResponse(
            id=None,
            match_score=7,
            summary="Good backend match with one infrastructure gap.",
            matched_skills=["Python", "FastAPI"],
            missing_skills=["Kubernetes"],
            matched_keywords=["API", "PostgreSQL"],
            missing_keywords=["Kubernetes"],
            supported_requirements=[
                SupportedRequirement(
                    requirement="Build APIs",
                    resume_evidence="Built FastAPI services.",
                    confidence=0.9,
                )
            ],
            unsupported_requirements=[
                UnsupportedRequirement(
                    requirement="Operate Kubernetes workloads",
                    reason="No Kubernetes evidence found.",
                )
            ],
            recommended_resume_updates=["Mention PostgreSQL work more clearly if accurate."],
        )


def create_test_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_resume_job_matcher] = lambda: FakeMatcher()
    return TestClient(app)


def test_resume_job_match_returns_score_and_skills() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={
            "resume_text": "Built FastAPI services with Python.",
            "job_description_text": "Build APIs using PostgreSQL and Kubernetes.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_score"] == 7
    assert payload["score_scale"] == "0-10"
    assert payload["matched_skills"] == ["Python", "FastAPI"]
    assert payload["missing_skills"] == ["Kubernetes"]
    assert payload["supported_requirements"][0]["confidence"] == 0.9
    assert payload["unsupported_requirements"][0]["requirement"] == "Operate Kubernetes workloads"


def test_resume_job_match_rejects_empty_inputs() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/resume-job-matches",
        json={"resume_text": "", "job_description_text": ""},
    )

    assert response.status_code == 422

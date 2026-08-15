from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import create_app
from app.modules.guest_trials.models import GuestDocument, GuestResumeProfile, GuestSearchCriterion, GuestTrial
from app.modules.guest_trials.models import GuestMatchCandidate, GuestMatchResult, GuestProviderAttempt
from app.modules.guest_trials.service import purge_expired_guest_trial_batch, purge_expired_guest_trials
from app.modules.guest_trials.rate_limit import GuestRateLimiter, GuestRateLimitPolicy
from app.modules.profiles.schemas import ResumeData
from app.modules.jobs.schemas import IndeedJobSearchResult
from app.modules.resume_job_match.schemas import ResumeJobMatchResponse
import app.modules.guest_trials.router as guest_router


class StubResumeParser:
    def parse(self, _resume_text: str) -> ResumeData:
        return ResumeData(
            headline="Mobile Engineer",
            summary="Builds supported mobile products.",
            projects=["Built and launched a Flutter application used by 20 testers."],
            skills=["Dart", "Flutter", "REST APIs"],
        )


class RetryResumeParser(StubResumeParser):
    def __init__(self) -> None:
        self.calls = 0

    def parse(self, resume_text: str) -> ResumeData:
        self.calls += 1
        if self.calls == 1:
            raise HTTPException(status_code=502, detail="provider internals must not leak")
        return super().parse(resume_text)


class StubJobSearchProvider:
    def __init__(self, results: list[IndeedJobSearchResult] | None = None, *, fail_first: bool = False) -> None:
        self.results = results or []
        self.fail_first = fail_first
        self.calls = 0

    def search(self, *, keyword: str, location: str, max_results: int) -> list[IndeedJobSearchResult]:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise HTTPException(status_code=504, detail="provider details")
        assert keyword
        assert location
        return self.results[:max_results]


class StubResumeJobMatcher:
    def __init__(self, *, fail_calls: int = 0) -> None:
        self.fail_calls = fail_calls
        self.calls = 0

    def compare(self, request) -> ResumeJobMatchResponse:
        self.calls += 1
        if self.calls <= self.fail_calls:
            raise HTTPException(status_code=502, detail="matcher details")
        job_text = request.job_description_text or ""
        score = 9 if "Senior" in job_text else 6
        return ResumeJobMatchResponse(
            match_score=score,
            summary=f"Candidate evidence supports this {score}/10 match.",
            matched_skills=["Python"],
            missing_skills=["Kubernetes"] if score < 9 else [],
            provider_model_name="stub-matcher",
            provider_execution_reference=f"match-{self.calls}",
        )


def create_test_client(
    storage_root: Path | None = None,
    *,
    parser=None,
    guest_rate_policy: GuestRateLimitPolicy | None = None,
    search_provider=None,
    matcher=None,
) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_db():
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app = create_app()
    if storage_root is not None:
        app.state.runtime = app.state.runtime.__class__(
            **{**app.state.runtime.__dict__, "document_storage_dir": str(storage_root)}
        )
    if parser is not None:
        app.dependency_overrides[guest_router.get_guest_resume_parser] = lambda: parser
    if guest_rate_policy is not None:
        app.state.guest_rate_limiter = GuestRateLimiter(guest_rate_policy)
    if search_provider is not None:
        app.dependency_overrides[guest_router.get_apify_indeed_client] = lambda: search_provider
    if matcher is not None:
        app.dependency_overrides[guest_router.get_guest_resume_job_matcher] = lambda: matcher
    app.dependency_overrides[get_db_session] = override_db
    return TestClient(app), session_factory


def _create_trial(client: TestClient) -> dict:
    response = client.post("/api/v1/guest-trials")
    assert response.status_code == 201
    return response.json()


def _headers(trial: dict) -> dict[str, str]:
    return {"Authorization": f"Guest {trial['guest_credential']}"}


def _ready_guest(client: TestClient) -> dict:
    trial = _create_trial(client)
    assert client.put(
        "/api/v1/guest-trials/current/profile",
        headers=_headers(trial),
        json={
            "resume_data": {
                "experience": ["Built and improved Python APIs used by 500 customers."],
                "skills": ["Python", "SQL", "REST APIs"],
            }
        },
    ).status_code == 200
    assert client.put(
        "/api/v1/guest-trials/current/criteria",
        headers=_headers(trial),
        json={"keyword": "Backend Engineer", "location": "Remote"},
    ).status_code == 200
    return trial


def test_guest_secret_is_returned_once_and_stored_only_as_hash() -> None:
    client, session_factory = create_test_client()
    created = _create_trial(client)

    assert created["public_id"]
    assert created["guest_secret"]
    assert created["guest_secret"] in created["guest_credential"]
    assert client.get("/api/v1/guest-trials/current").status_code == 401
    assert client.get(
        "/api/v1/guest-trials/current",
        headers={"Authorization": f"Bearer {created['guest_credential']}"},
    ).status_code == 401

    with session_factory() as db:
        stored = db.scalar(select(GuestTrial))
        assert stored is not None
        assert stored.secret_hash != created["guest_secret"]
        assert created["guest_secret"] not in str(stored.__dict__)


def test_guest_profile_criteria_and_readiness_restore_without_account() -> None:
    client, _session_factory = create_test_client()
    created = _create_trial(client)
    headers = _headers(created)

    profile = client.put(
        "/api/v1/guest-trials/current/profile",
        headers=headers,
        json={
            "resume_data": {
                "projects": ["Built and launched a Flutter application used by 20 student testers."],
                "skills": ["Dart", "Flutter", "REST APIs"],
            }
        },
    )
    assert profile.status_code == 200
    assert profile.json()["readiness"]["ready"] is True
    assert profile.json()["readiness"]["pathway"] == "early_career"

    criteria = client.put(
        "/api/v1/guest-trials/current/criteria",
        headers=headers,
        json={"keyword": "Mobile Engineer", "location": "Seattle, WA"},
    )
    assert criteria.status_code == 200

    restored = client.get("/api/v1/guest-trials/current", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["profile"]["readiness"]["ready"] is True
    assert restored.json()["criteria"] == {
        **criteria.json(),
    }
    assert client.get("/api/v1/guest-trials/current/readiness", headers=headers).json()["ready"] is True


def test_guest_credentials_are_isolated() -> None:
    client, _session_factory = create_test_client()
    first = _create_trial(client)
    second = _create_trial(client)

    assert client.put(
        "/api/v1/guest-trials/current/criteria",
        headers=_headers(first),
        json={"keyword": "Backend Engineer", "location": "Remote"},
    ).status_code == 200
    assert client.get("/api/v1/guest-trials/current", headers=_headers(second)).json()["criteria"] is None

    tampered = f"{first['public_id']}.{second['guest_secret']}"
    assert client.get(
        "/api/v1/guest-trials/current",
        headers={"Authorization": f"Guest {tampered}"},
    ).status_code == 401


def test_guest_resume_upload_is_redacted_isolated_and_replaced(tmp_path: Path) -> None:
    client, session_factory = create_test_client(tmp_path)
    first = _create_trial(client)
    second = _create_trial(client)

    upload = client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=_headers(first),
        files={
            "file": (
                "../resume.txt",
                b"Jane Example\njane@example.com\n206-555-1212\n\nBuilt Python APIs for retail customers.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["file_name"] == "resume.txt"
    assert "jane@example.com" not in body["extracted_text_preview"]
    assert "206-555-1212" not in body["extracted_text_preview"]
    assert body["requires_profile_confirmation"] is True
    assert client.get("/api/v1/guest-trials/current", headers=_headers(second)).json()["resume_import"] is None

    with session_factory() as db:
        document = db.scalar(select(GuestDocument))
        assert document is not None
        first_storage_path = Path(document.storage_path)
        assert first_storage_path.is_file()
        assert tmp_path.resolve() in first_storage_path.resolve().parents
        assert "guest_trials" in first_storage_path.parts
        assert "jane@example.com" not in document.extracted_text

    replacement = client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=_headers(first),
        files={"file": ("resume-v2.txt", b"Built and shipped a second resume version.", "text/plain")},
    )
    assert replacement.status_code == 200
    assert first_storage_path.exists() is False

    with session_factory() as db:
        documents = list(db.scalars(select(GuestDocument)).all())
        assert len(documents) == 1
        replacement_path = Path(documents[0].storage_path)
        assert replacement_path.is_file()

    assert client.delete("/api/v1/guest-trials/current", headers=_headers(first)).status_code == 204
    assert replacement_path.exists() is False


def test_guest_resume_upload_returns_suggestions_without_confirming_profile(tmp_path: Path) -> None:
    client, session_factory = create_test_client(tmp_path, parser=StubResumeParser())
    created = _create_trial(client)
    response = client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=_headers(created),
        files={"file": ("resume.txt", b"Built Flutter applications and REST APIs.", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["parse_status"] == "succeeded"
    assert response.json()["suggestions"]["headline"] == "Mobile Engineer"
    assert response.json()["parse_warning"] is None
    assert client.get("/api/v1/guest-trials/current", headers=_headers(created)).json()["profile"] is None
    with session_factory() as db:
        document = db.scalar(select(GuestDocument))
        assert document is not None
        assert document.parser_provenance == {
            "parser_version": "resume-parser-v1",
            "provider": "openai",
            "model": client.app.state.runtime.openai_model,
            "outcome": "succeeded",
        }


def test_guest_resume_parse_failure_is_safe_and_retryable(tmp_path: Path) -> None:
    parser = RetryResumeParser()
    client, _session_factory = create_test_client(tmp_path, parser=parser)
    created = _create_trial(client)
    uploaded = client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=_headers(created),
        files={"file": ("resume.txt", b"Built Flutter applications and REST APIs.", "text/plain")},
    )

    assert uploaded.status_code == 200
    assert uploaded.json()["parse_status"] == "failed"
    assert "provider internals" not in uploaded.text
    assert uploaded.json()["suggestions"]["skills"] == []

    retried = client.post("/api/v1/guest-trials/current/resume-import/retry", headers=_headers(created))
    assert retried.status_code == 200
    assert retried.json()["parse_status"] == "succeeded"
    assert retried.json()["suggestions"]["skills"] == ["Dart", "Flutter", "REST APIs"]


def test_guest_creation_and_parse_attempts_are_rate_limited(tmp_path: Path) -> None:
    policy = GuestRateLimitPolicy(create_ip_limit=1, parse_trial_limit=1, parse_ip_limit=10, window_seconds=3600)
    client, _session_factory = create_test_client(tmp_path, parser=StubResumeParser(), guest_rate_policy=policy)
    created = _create_trial(client)
    assert client.post("/api/v1/guest-trials").status_code == 429

    uploaded = client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=_headers(created),
        files={"file": ("resume.txt", b"Built Flutter applications and REST APIs.", "text/plain")},
    )
    assert uploaded.status_code == 200
    retry = client.post("/api/v1/guest-trials/current/resume-import/retry", headers=_headers(created))
    assert retry.status_code == 429
    assert int(retry.headers["Retry-After"]) > 0


def test_expired_trials_are_rejected_and_purged_with_private_data(tmp_path: Path) -> None:
    client, session_factory = create_test_client(tmp_path)
    created = _create_trial(client)
    headers = _headers(created)
    assert client.put(
        "/api/v1/guest-trials/current/profile",
        headers=headers,
        json={"resume_data": {"experience": ["A sufficiently detailed temporary work history entry."]}},
    ).status_code == 200
    assert client.post(
        "/api/v1/guest-trials/current/resume-import",
        headers=headers,
        files={"file": ("resume.txt", b"Private temporary resume content for cleanup.", "text/plain")},
    ).status_code == 200

    with session_factory() as db:
        trial = db.scalar(select(GuestTrial))
        assert trial is not None
        trial.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    assert client.get("/api/v1/guest-trials/current", headers=headers).status_code == 401

    with session_factory() as db:
        document = db.scalar(select(GuestDocument))
        assert document is not None
        storage_path = Path(document.storage_path)
        assert storage_path.exists()
        assert purge_expired_guest_trials(db, storage_root=str(tmp_path)) == 1
        db.commit()
        assert db.scalar(select(GuestTrial)) is None
        assert db.scalar(select(GuestResumeProfile)) is None
        assert db.scalar(select(GuestDocument)) is None
        assert storage_path.exists() is False


def test_guest_can_delete_trial_immediately() -> None:
    client, session_factory = create_test_client()
    created = _create_trial(client)
    headers = _headers(created)
    assert client.put(
        "/api/v1/guest-trials/current/criteria",
        headers=headers,
        json={"keyword": "Designer", "location": "Portland, OR"},
    ).status_code == 200

    assert client.delete("/api/v1/guest-trials/current", headers=headers).status_code == 204
    assert client.get("/api/v1/guest-trials/current", headers=headers).status_code == 401
    with session_factory() as db:
        assert db.scalar(select(GuestTrial)) is None
        assert db.scalar(select(GuestSearchCriterion)) is None


def test_guest_purge_batch_is_bounded_dry_runnable_and_idempotent(tmp_path: Path) -> None:
    client, session_factory = create_test_client(tmp_path)
    first = _create_trial(client)
    second = _create_trial(client)
    with session_factory() as db:
        trials = list(db.scalars(select(GuestTrial).order_by(GuestTrial.id)).all())
        for index, trial in enumerate(trials):
            trial.expires_at = datetime.now(timezone.utc) - timedelta(minutes=2 - index)
        db.commit()

    with session_factory() as db:
        dry_run = purge_expired_guest_trial_batch(db, storage_root=str(tmp_path), limit=1, dry_run=True)
        assert dry_run.eligible == 1
        assert dry_run.purged == 0
        assert dry_run.dry_run is True
        assert len(list(db.scalars(select(GuestTrial)).all())) == 2

        first_pass = purge_expired_guest_trial_batch(db, storage_root=str(tmp_path), limit=1)
        db.commit()
        assert first_pass.purged == 1
        assert db.scalar(select(GuestTrial).where(GuestTrial.public_id == first["public_id"])) is None
        assert db.scalar(select(GuestTrial).where(GuestTrial.public_id == second["public_id"])) is not None

        second_pass = purge_expired_guest_trial_batch(db, storage_root=str(tmp_path), limit=10)
        db.commit()
        assert second_pass.purged == 1
        assert purge_expired_guest_trial_batch(db, storage_root=str(tmp_path), limit=10).eligible == 0


def test_guest_purge_blocks_untrusted_storage_path_and_reports_missing_file(tmp_path: Path) -> None:
    client, session_factory = create_test_client(tmp_path)
    unsafe_trial = _create_trial(client)
    missing_trial = _create_trial(client)
    outside_file = tmp_path / "must-not-delete.txt"
    outside_file.write_text("not guest storage", encoding="utf-8")
    missing_path = tmp_path / "guest_trials" / missing_trial["public_id"] / "already-gone.txt"

    with session_factory() as db:
        trials = {item.public_id: item for item in db.scalars(select(GuestTrial)).all()}
        for trial in trials.values():
            trial.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.add(
            GuestDocument(
                guest_trial_id=trials[unsafe_trial["public_id"]].id,
                file_name="unsafe.txt",
                content_type="text/plain",
                size_bytes=1,
                sha256="a" * 64,
                storage_path=str(outside_file),
                extracted_text="temporary",
                parse_status="pending",
            )
        )
        db.add(
            GuestDocument(
                guest_trial_id=trials[missing_trial["public_id"]].id,
                file_name="missing.txt",
                content_type="text/plain",
                size_bytes=1,
                sha256="b" * 64,
                storage_path=str(missing_path),
                extracted_text="temporary",
                parse_status="pending",
            )
        )
        db.commit()

    with session_factory() as db:
        result = purge_expired_guest_trial_batch(db, storage_root=str(tmp_path), limit=10)
        db.commit()
        assert result.eligible == 2
        assert result.purged == 1
        assert result.files_missing == 1
        assert result.failed_trials == 1
        assert outside_file.read_text(encoding="utf-8") == "not guest storage"
        assert db.scalar(select(GuestTrial).where(GuestTrial.public_id == unsafe_trial["public_id"])) is not None
        assert db.scalar(select(GuestTrial).where(GuestTrial.public_id == missing_trial["public_id"])) is None


def test_guest_match_returns_only_best_candidate_and_consumes_search_once() -> None:
    provider = StubJobSearchProvider(
        [
            IndeedJobSearchResult(
                external_id="1",
                title="Backend Engineer",
                company="Example One",
                location="Remote",
                source_url="https://jobs.example/1",
                raw_description_text="Build Python services.",
            ),
            IndeedJobSearchResult(
                external_id="2",
                title="Senior Backend Engineer",
                company="Example Two",
                location="Seattle, WA",
                source_url="https://jobs.example/2",
                raw_description_text="Senior engineer building Python services.",
            ),
        ]
    )
    matcher = StubResumeJobMatcher()
    client, session_factory = create_test_client(search_provider=provider, matcher=matcher)
    trial = _ready_guest(client)
    headers = {**_headers(trial), "Idempotency-Key": "guest-search-1"}

    response = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "result_ready"
    assert body["provider_search_state"] == "consumed"
    assert body["result"]["title"] == "Senior Backend Engineer"
    assert body["result"]["match_score"] == 9
    assert body["result"]["job_description"] == "Senior engineer building Python services."
    assert body["result"]["result_context"] == "Best usable match from this guest search"
    assert "candidates" not in body
    assert provider.calls == 1
    assert matcher.calls == 2

    repeated = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["result"] == body["result"]
    assert provider.calls == 1
    assert matcher.calls == 2
    with session_factory() as db:
        assert len(list(db.scalars(select(GuestMatchCandidate)).all())) == 2
        assert len(list(db.scalars(select(GuestMatchResult)).all())) == 1
        attempt = db.scalar(select(GuestProviderAttempt))
        assert attempt is not None
        assert attempt.state == "consumed"


def test_failed_guest_search_releases_allowance_and_can_retry() -> None:
    provider = StubJobSearchProvider(
        [
            IndeedJobSearchResult(
                title="Backend Engineer",
                company="Example",
                source_url="https://jobs.example/retry",
                raw_description_text="Build Python services.",
            )
        ],
        fail_first=True,
    )
    client, session_factory = create_test_client(search_provider=provider, matcher=StubResumeJobMatcher())
    trial = _ready_guest(client)
    headers = {**_headers(trial), "Idempotency-Key": "retryable-search"}

    failed = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert failed.status_code == 503
    assert "provider details" not in failed.text
    failed_status = client.get("/api/v1/guest-trials/current/match", headers=_headers(trial)).json()
    assert failed_status["provider_search_state"] == "released"
    assert failed_status["retryable"] is True

    retried = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["provider_search_state"] == "consumed"
    assert provider.calls == 2
    with session_factory() as db:
        attempts = list(db.scalars(select(GuestProviderAttempt)).all())
        assert len(attempts) == 1
        assert attempts[0].state == "consumed"


def test_matcher_failure_reuses_consumed_candidates_without_new_search() -> None:
    provider = StubJobSearchProvider(
        [
            IndeedJobSearchResult(
                title="Backend Engineer",
                company="Example",
                source_url="https://jobs.example/matcher-retry",
                raw_description_text="Build Python services.",
            )
        ]
    )
    matcher = StubResumeJobMatcher(fail_calls=1)
    client, _session_factory = create_test_client(search_provider=provider, matcher=matcher)
    trial = _ready_guest(client)
    headers = {**_headers(trial), "Idempotency-Key": "matcher-retry"}

    failed = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert failed.status_code == 503
    status_after_failure = client.get("/api/v1/guest-trials/current/match", headers=_headers(trial)).json()
    assert status_after_failure["provider_search_state"] == "consumed"
    assert status_after_failure["error_code"] == "matcher_unavailable"

    retried = client.post("/api/v1/guest-trials/current/match", headers=headers)
    assert retried.status_code == 200
    assert retried.json()["result"]["match_score"] == 6
    assert provider.calls == 1
    assert matcher.calls == 2


def test_unusable_guest_search_response_does_not_consume_trial() -> None:
    provider = StubJobSearchProvider(
        [IndeedJobSearchResult(title="Incomplete listing", company="Example", source_url=None)]
    )
    client, session_factory = create_test_client(search_provider=provider, matcher=StubResumeJobMatcher())
    trial = _ready_guest(client)
    response = client.post(
        "/api/v1/guest-trials/current/match",
        headers={**_headers(trial), "Idempotency-Key": "unusable-search"},
    )

    assert response.status_code == 503
    status_body = client.get("/api/v1/guest-trials/current/match", headers=_headers(trial)).json()
    assert status_body["provider_search_state"] == "released"
    assert status_body["error_code"] == "no_usable_jobs"
    with session_factory() as db:
        attempt = db.scalar(select(GuestProviderAttempt))
        assert attempt is not None
        assert attempt.state == "released"
        assert attempt.failure_category == "unusable_response"


def test_guest_match_requires_candidate_evidence_and_criteria() -> None:
    provider = StubJobSearchProvider()
    client, _session_factory = create_test_client(search_provider=provider, matcher=StubResumeJobMatcher())
    trial = _create_trial(client)
    assert client.put(
        "/api/v1/guest-trials/current/profile",
        headers=_headers(trial),
        json={"resume_data": {"target_roles": ["Backend Engineer"]}},
    ).status_code == 200
    response = client.post(
        "/api/v1/guest-trials/current/match",
        headers={**_headers(trial), "Idempotency-Key": "not-ready"},
    )
    assert response.status_code == 422
    assert provider.calls == 0

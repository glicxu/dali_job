# Issues Identified

Status checked on 2026-07-08 after the us3 deployment work.

## Summary

| Severity | Issue | Current status |
| --- | --- | --- |
| High | Local auth can still fall back to a known JWT secret | Fixed |
| High | Scraping/AI helper endpoints bypass API auth | Fixed |
| High | GitHub CI likely fails on clean checkout | Still relevant |
| Medium | Job-cache URL dedupe is race-prone | Fixed |

## 1. Local auth can still fall back to a known JWT secret

Severity: High

Current status: Superseded and fixed.

As of migration `20260803_0026`, DaliJob no longer issues JWT bearer tokens. Local authentication uses high-entropy opaque session identifiers; only their SHA-256 hashes are stored in `auth_sessions`. Browser credentials are sent in `HttpOnly` cookies and are individually revocable. `DALIJOB_JWT_SECRET` is no longer a runtime requirement. Session expiry, revocation, email verification, password reset, soft-deleted users, and CSRF boundaries have automated tests.

## 2. Scraping/AI helper endpoints bypass API auth

Severity: High

Current status: Fixed.

These endpoints now depend on `get_current_identity`:

- `server/app/modules/jobs/router.py:128` exposes `POST /api/v1/jobs/draft`.
- `server/app/modules/jobs/router.py:166` exposes `POST /api/v1/jobs/import-list/discover`.
- `server/app/modules/resume_job_match/router.py:153` exposes `POST /api/v1/resume-job-matches/job-url-extract`.

Nearby routes do use auth:

- `server/app/modules/jobs/router.py:122`, `141`, `200`, and later routes include `Depends(get_current_identity)`.
- `server/app/modules/resume_job_match/router.py:168` and later routes include `Depends(get_current_identity)`.

Impact after fix:

Unauthenticated callers receive `401` before URL fetching/rendering or OpenAI parsing can run.

Completed fix:

Added:

```python
identity: AuthenticatedIdentity = Depends(get_current_identity)
```

to all three endpoints. The endpoint bodies do not use `identity`; the dependency is enough to enforce auth.

Add tests:

- In `auth_mode = local`, each route returns `401` without a valid session.
- Each route succeeds with a valid session and mutating routes require the CSRF header.

## 3. GitHub CI likely fails on clean checkout

Severity: High

Current status: Still relevant.

`requirements.txt:1` contains:

```text
-e ../DaliCommonLib
```

The GitHub workflow only checks out this repo before installing requirements:

- `.github/workflows/ci.yml:13` checks out `dali_job`.
- `.github/workflows/ci.yml:20` runs `python -m pip install -r requirements.txt`.
- The same pattern repeats at `.github/workflows/ci.yml:28`, `35`, `59`, and `66`.

Impact:

A clean GitHub runner will not have `../DaliCommonLib`, so server test, migration, and OpenAPI jobs are expected to fail during dependency installation.

Recommended fix options:

- Publish/package `DaliCommonLib` and pin it by version.
- Add `DaliCommonLib` as a git submodule and update CI to initialize submodules.
- Add an explicit second checkout step into `../DaliCommonLib`.
- Replace the editable path with a VCS requirement if this repo should build standalone from GitHub.

Preferred short-term fix:

Use a second checkout step in each Python CI job:

```yaml
- uses: actions/checkout@v4
  with:
    repository: glicxu/DaliCommonLib
    path: ../DaliCommonLib
```

## 4. Job-cache URL dedupe is race-prone

Severity: Medium

Current status: Fixed.

Current model:

- `server/app/modules/jobs/models.py:44` defines `jobs_cache.source_url_hash` with a unique index.
- `server/app/db/migrations/versions/20260713_0016_unique_jobs_cache_source_url_hash.py` collapses duplicate cache hashes and creates the unique index for upgraded schemas.

Current repository flow:

- `server/app/modules/jobs/repository.py:147` reads by source URL hash.
- `server/app/modules/jobs/repository.py:253` defines `get_or_create_cache_job()`.
- `server/app/modules/jobs/repository.py` normalizes the source URL before hashing and storing it.
- `server/app/modules/jobs/repository.py` reuses an active cache row when one already exists.
- `server/app/modules/jobs/repository.py` reactivates a soft-deleted cache row when the same URL is imported again.
- `server/app/modules/jobs/repository.py` wraps cache creation in a nested transaction and re-reads the winning row after an `IntegrityError`.

Impact:

Concurrent imports of the same normalized URL should now converge on one `jobs_cache` row. Existing duplicates are collapsed by the migration before the unique index is created.

Recommended fix:

Completed fix:

Added a unique index around `jobs_cache.source_url_hash`, normalized source URLs before hashing, and handled `IntegrityError` by re-reading and reusing the existing cache row.

Implementation notes:

- MySQL allows multiple `NULL` values in a unique index, so nullable `source_url_hash` can remain compatible if text-only jobs are not deduped by URL.
- Soft-deleted rows are explicitly reactivated on re-import rather than creating another cache row for the same URL.
- The migration updates `user_saved_jobs.jobs_cache_id` and `job_resume_matches.jobs_cache_id` to point duplicate references at the keeper row, then nulls the duplicate hash values before creating the unique index.

Add tests:

- Sequential duplicate URL imports reuse the same cache row.
- Simulated integrity conflict re-reads the existing cache row.
- Soft-deleted cache rows are reactivated on re-import.

## Verification status

Current local server tests pass:

```text
87 passed, 1 warning
```

These tests include coverage for local auth secret enforcement, default-secret rejection, dev-auth behavior, unauthenticated helper route rejection, valid-token access to the helper routes, job-cache unique metadata, sequential URL reuse, conflict reuse, and soft-deleted cache reactivation.

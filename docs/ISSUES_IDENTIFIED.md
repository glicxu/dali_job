# Issues Identified

Status checked on 2026-07-08 after the us3 deployment work.

## Summary

| Severity | Issue | Current status |
| --- | --- | --- |
| High | Local auth can still fall back to a known JWT secret | Partially mitigated, still relevant |
| High | Scraping/AI helper endpoints bypass API auth | Still relevant |
| High | GitHub CI likely fails on clean checkout | Still relevant |
| Medium | Job-cache URL dedupe is race-prone | Still relevant |

## 1. Local auth can still fall back to a known JWT secret

Severity: High

Current status: Partially mitigated, still relevant.

The original config-file risk has been reduced:

- `server/config.example.ini` no longer contains `jwt_secret = change-me`.
- The example now documents that JWT signing secret is read from `DALIJOB_JWT_SECRET`.
- Production us3 uses `/data/dali/prod/config/dali_job.env` for `DALIJOB_JWT_SECRET`.

However, the code still contains a hardcoded fallback:

- `server/app/modules/auth/dependencies.py:16` defines `DEFAULT_AUTH_SECRET`.
- `server/app/modules/auth/dependencies.py:40` defines `get_auth_secret()`.
- `server/app/modules/auth/dependencies.py:45` still falls back to `[dali_job_auth].jwt_secret` or `DEFAULT_AUTH_SECRET`.
- `server/config.example.ini:12` still sets `auth_mode = local`.

Impact:

If a shared or production-like environment runs with `auth_mode = local` but without `DALIJOB_JWT_SECRET`, bearer tokens can be forged using the documented fallback secret.

Recommended fix:

Fail startup or token creation in `local` auth mode unless `DALIJOB_JWT_SECRET` is present and is not one of the known default/documentation values. Keep permissive fallback only for explicit `auth_mode = dev`.

Add tests:

- Local auth mode without `DALIJOB_JWT_SECRET` returns a startup/config error.
- Local auth mode rejects `DEFAULT_AUTH_SECRET`.
- Dev auth mode still works without JWT secret if that behavior is intentionally preserved.

## 2. Scraping/AI helper endpoints bypass API auth

Severity: High

Current status: Still relevant.

These endpoints still do not depend on `get_current_identity`:

- `server/app/modules/jobs/router.py:128` exposes `POST /api/v1/jobs/draft`.
- `server/app/modules/jobs/router.py:166` exposes `POST /api/v1/jobs/import-list/discover`.
- `server/app/modules/resume_job_match/router.py:153` exposes `POST /api/v1/resume-job-matches/job-url-extract`.

Nearby routes do use auth:

- `server/app/modules/jobs/router.py:122`, `141`, `200`, and later routes include `Depends(get_current_identity)`.
- `server/app/modules/resume_job_match/router.py:168` and later routes include `Depends(get_current_identity)`.

Impact:

Unauthenticated callers can trigger URL fetching/rendering and, for `/jobs/draft`, OpenAI parsing. This creates abuse/cost risk and conflicts with the client-side expectation that login is required.

Recommended fix:

Add:

```python
identity: AuthenticatedIdentity = Depends(get_current_identity)
```

to all three endpoints. The endpoint bodies do not need to use `identity`; the dependency is enough to enforce auth.

Add tests:

- In `auth_mode = local`, each route returns `401` without a bearer token.
- Each route succeeds with a valid bearer token.

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

Current status: Still relevant.

Current model:

- `server/app/modules/jobs/models.py:44` defines `jobs_cache.source_url_hash` with `index=True`, not a uniqueness constraint.

Current repository flow:

- `server/app/modules/jobs/repository.py:147` reads by source URL hash.
- `server/app/modules/jobs/repository.py:253` defines `get_or_create_cache_job()`.
- `server/app/modules/jobs/repository.py:264` performs read-before-insert.
- `server/app/modules/jobs/repository.py:211` inserts the new cache row.

Impact:

Concurrent imports of the same normalized URL can create duplicate `jobs_cache` rows. Those duplicates can then lead to duplicate user-saved jobs or inconsistent cache reuse.

Recommended fix:

Add a uniqueness constraint around normalized URL hash for active cache rows and handle `IntegrityError` by re-reading the existing row.

Implementation notes:

- MySQL allows multiple `NULL` values in a unique index, so nullable `source_url_hash` can remain compatible if text-only jobs are not deduped by URL.
- If soft-deleted rows should not block re-import, use a generated active key or a composite strategy that accounts for `deleted_at`.
- Add a migration for the unique constraint and a cleanup/backfill step if duplicates already exist.

Add tests:

- Sequential duplicate URL imports reuse the same cache row.
- Simulated integrity conflict re-reads the existing cache row.
- Soft-deleted cache-row behavior is explicit.

## Verification status

Current local focused tests pass:

```text
13 passed, 1 warning
```

These focused tests cover auth secret env preference, DB-backed provider secret lookup, and Apify route behavior. They do not close the findings above unless the recommended code and CI changes are implemented.

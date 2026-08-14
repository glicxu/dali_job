# DaliJob Architecture Review

- **Review date:** August 14, 2026
- **Reviewed revision:** `79e3464f35a444ecfdf38742e000fc5c23745edc` (`main`)
- **Environment:** US3 production deployment
- **Audience:** Engineering and operations
- **Status:** Action required on critical findings

## Executive Summary

DaliJob has a sound modular-monolith foundation. The FastAPI backend is organized by business domain, the Next.js client has a coherent API boundary, authentication includes production startup validation, and the data model distinguishes shared job-source data from user-owned edits and decisions. Application tracking, document provenance, managed-operation records, and migration/readiness checks are all meaningful strengths.

The review found two critical production risks:

1. The deployed client bundle was built without `NEXT_PUBLIC_API_BASE_URL` and contains the fallback `http://127.0.0.1:5010/api/v1`. A production browser will therefore attempt authenticated API calls against its own loopback interface instead of the DaliJob API.
2. The database connection URI is written to production logs at `INFO` level by DaliCommonLib. Because the URI contains credentials, the credential should be treated as exposed.

The next highest priorities are to make managed operations truly durable, reduce database-session pressure, ensure account deletion covers stored files, and make builds reproducible. These changes should precede broad feature expansion.

## Scope and Method

This review covered:

- Application structure and module boundaries.
- Client-to-server configuration and the deployed client bundle.
- Authentication and database-session behavior.
- Long-running managed operations.
- Data ownership, tenant isolation, deletion, and file lifecycle.
- Build, CI, release, migration, deployment, and rollback mechanics.
- Code concentration and maintainability hotspots.

The assessment combined source inspection, build artifact inspection, test results, migration/readiness checks, and US3 deployment verification. It did not include penetration testing, load testing, disaster-recovery testing, or a cloud infrastructure audit.

## Architecture at a Glance

```text
Browser / Next.js client
        |
        | HTTPS JSON API + session/CSRF cookies
        v
Apache reverse proxy
        |
        +--> FastAPI modular monolith
                |
                +--> Auth and domain repositories
                +--> Managed-operation execution
                +--> Provider integrations (OpenAI, Apify, URL import)
                +--> SQLAlchemy / Alembic
                |       |
                |       +--> Relational database
                |
                +--> Local document storage
```

The design is appropriate for the current product stage, provided that deployment configuration, secret handling, and background execution are hardened.

## Findings Summary

| Priority | Finding | Primary consequence |
|---|---|---|
| Critical | Production client bundle targets loopback API | Authenticated production workflows can fail in the browser |
| Critical | Database credentials are emitted to logs | Credential exposure and unauthorized database access risk |
| High | Managed operations are not durably dispatched | Work can be lost on restart, deploy, or process failure |
| High | Protected requests can open two database sessions | Pool exhaustion and inconsistent transaction boundaries |
| High | Account deletion does not purge stored files | Sensitive user documents may remain after deletion |
| High | Python dependencies and release inputs are not reproducible | Builds can drift and deployments can fail unexpectedly |
| Medium | Tenant integrity relies primarily on repository filters | A missed filter can create cross-tenant references |
| Medium | Several modules are oversized and tightly coupled | Changes are harder to review, test, and evolve safely |

## Detailed Findings

### 1. Production Client Bundle Targets a Loopback API

**Priority:** Critical

The client build in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs `npm run build` without defining `NEXT_PUBLIC_API_BASE_URL`. In [`client/lib/config.ts`](../client/lib/config.ts), the non-local fallback is still `http://127.0.0.1:5010/api/v1`. Inspection of the deployed JavaScript bundle confirmed that the loopback URL was compiled into the production artifact and that the production API URL was absent.

**Impact**

- The HTML shell and static assets can load successfully while authenticated API calls fail.
- Each user's browser attempts to contact port `5010` on the user's own computer.
- A local service listening on that port could receive requests intended for DaliJob.
- A successful server-side health check does not detect this client-side failure mode.

**Recommendation**

- Make the browser use a same-origin path such as `/api/v1` where possible, with Apache routing that path to FastAPI.
- If an absolute URL is required, provide `NEXT_PUBLIC_API_BASE_URL` explicitly in the release build job.
- Fail the production build when the value is missing or resolves to localhost/loopback.
- Add an artifact test that scans emitted JavaScript for `localhost`, `127.0.0.1`, and other forbidden development endpoints.
- Rebuild and redeploy after correcting the configuration.

**Exit criteria**

- The production bundle contains only the intended production or same-origin API target.
- An authenticated browser smoke test succeeds from a machine other than the server.
- CI rejects production bundles containing loopback API URLs.

### 2. Database Credentials Are Emitted to Production Logs

**Priority:** Critical

Production logs contain the full database connection URI because the application logs at `INFO` and DaliCommonLib logs engine creation using the unredacted URI. The credential value is intentionally omitted from this document.

**Impact**

- Anyone with access to the affected logs may obtain database credentials.
- Log forwarding, backups, support bundles, or copied diagnostics can broaden exposure.
- Retention of old logs can preserve access after application code is fixed.

**Recommendation**

1. Change the shared database library to render credentials as redacted before logging, or remove the URI from the log message entirely.
2. Rotate the affected production database credential after the logging fix is deployed.
3. Identify, purge, or tightly restrict access to existing logs and copies that contain the old value.
4. Add an automated log-safety test using a credential-shaped sentinel value.
5. Review other configuration logging for API keys, tokens, session secrets, and provider credentials.

**Exit criteria**

- Database startup logs contain no password, token, or complete credential-bearing URI.
- The exposed credential has been rotated and the old credential no longer authenticates.
- Retained log locations have been reviewed and remediated.

### 3. Managed Operations Are Persisted but Not Durably Dispatched

**Priority:** High

[`server/app/modules/operations/router.py`](../server/app/modules/operations/router.py) records operations in the database and then schedules execution through FastAPI `BackgroundTasks`. This improves status visibility but does not provide a durable queue. If the API process restarts after the operation is committed but before or during execution, no independent worker is responsible for resuming it. Stale-operation handling marks abandoned work as failed rather than providing durable delivery.

The execution path in [`server/app/modules/operations/service.py`](../server/app/modules/operations/service.py) also keeps a database session open while provider and network work runs. That makes long operations consume scarce database connections.

**Impact**

- Deploys, crashes, and process recycling can lose accepted work.
- Scaling API replicas creates ambiguous work ownership.
- Slow provider calls can hold database connections for long periods.
- Retry and cancellation semantics are limited by in-process execution.

**Recommendation**

- Introduce a durable queue and a separately supervised worker process.
- Commit the operation record and enqueue it using an outbox pattern or another atomic handoff.
- Use short database transactions: claim work, release the connection, perform external work, then persist progress/result in a new transaction.
- Add leases, heartbeats, idempotency, bounded retries, and dead-letter handling.
- Keep the existing managed-operation API as the user-facing status contract.

**Exit criteria**

- An accepted operation survives an API restart and is completed or retried by a worker.
- Provider wait time does not hold a database connection.
- Duplicate delivery produces one logical result.

### 4. Protected Requests Can Open Two Database Sessions

**Priority:** High

Authentication obtains a session through `get_auth_db_session` in [`server/app/modules/auth/dependencies.py`](../server/app/modules/auth/dependencies.py), while most domain handlers independently request `get_db_session` from [`server/app/db/session.py`](../server/app/db/session.py). A single protected request can therefore hold two database sessions and connections.

**Impact**

- Effective connection demand can approach twice the request concurrency.
- The small production connection pool is more likely to exhaust under load.
- Authentication and domain changes do not naturally share one transaction boundary.

**Recommendation**

- Establish one request-scoped session dependency and reuse it for authentication and domain work.
- Make transaction ownership explicit at the service boundary.
- Add pool metrics and a concurrency test that includes authenticated requests.

**Exit criteria**

- A protected request uses one request-scoped session unless a documented exception requires otherwise.
- Load testing shows bounded pool use with acceptable wait time and no pool timeouts.

### 5. Account Deletion Does Not Purge Stored Files

**Priority:** High

[`server/app/modules/auth/account_deletion.py`](../server/app/modules/auth/account_deletion.py) comprehensively anonymizes and soft-deletes relational records, but it does not remove the underlying uploaded document files from storage. File/database failures can also create orphaned files because the filesystem and database are not transactional together.

**Impact**

- Resume and career documents may remain on disk after the account is presented as deleted.
- Orphaned files can accumulate outside normal access paths.
- Privacy and retention behavior may differ from user expectations.

**Recommendation**

- Define whether account deletion means immediate purge, delayed purge, or recoverable soft deletion.
- Queue file deletion only after the database transaction commits successfully.
- Track purge state and retries in durable storage.
- Add a reconciliation task that detects database rows with missing files and unreferenced files on disk.
- Document backup retention and deletion guarantees.

**Exit criteria**

- Account deletion has an explicit, tested file-retention policy.
- Stored files reach a verifiable purged state within the documented period.
- Reconciliation reports and safely handles orphaned files.

### 6. Build and Release Inputs Are Not Fully Reproducible

**Priority:** High

[`requirements-runtime.txt`](../requirements-runtime.txt) lists top-level Python dependencies without version pins or hashes. A release built later can therefore resolve different packages from the same commit. The release workflow also depends on a separate private DaliCommonLib checkout; current GitHub checks cannot obtain it because the required `DALI_COMMON_LIB_TOKEN` secret is unavailable. The release artifact does not carry every operational dependency, including the readiness script and the shared library itself.

The client lockfile is now synchronized, but the broader release dependency graph remains split across repositories and runtime assumptions.

**Impact**

- Identical source commits can produce different runtime behavior.
- CI can fail before application tests run.
- Deployment may depend on mutable or preinstalled server state.
- Rollback validation is harder because artifacts are not fully self-contained.

**Recommendation**

- Generate locked, hashed Python dependency files from an intentional source manifest.
- Pin the exact DaliCommonLib revision and make CI credentials available through the approved secret mechanism.
- Prefer an immutable, self-contained release artifact or container image.
- Include readiness/migration tooling required by the deployment runbook.
- Record source revisions, dependency lock digests, configuration schema version, and SBOMs in the release manifest.

**Exit criteria**

- Two clean builds of the same revision resolve identical dependency versions and produce equivalent artifacts.
- All required CI jobs pass using repository-managed configuration and approved secrets.
- A fresh host can deploy the artifact without relying on an undocumented shared-library installation.

### 7. Tenant Integrity Relies Primarily on Repository Filters

**Priority:** Medium

Repositories consistently scope queries by user or workspace, which is good application-layer discipline. However, many relationships are enforced through independent foreign keys rather than composite constraints that guarantee all linked records belong to the same tenant.

**Impact**

- A missed ownership predicate or future maintenance error can create cross-tenant references that remain valid to the database.
- Repairing inconsistent tenant relationships becomes operationally difficult.

**Recommendation**

- Inventory all tenant-owned relationships and define the required ownership invariant for each one.
- Add composite unique keys and foreign keys where practical, or use database triggers for invariants that cannot be expressed directly.
- Retain repository-level authorization checks for defense in depth.
- Add negative tests that attempt to join records across users and workspaces.

**Exit criteria**

- Critical cross-tenant relationships are rejected by the database as well as by application code.

### 8. Large Modules Increase Coupling and Review Risk

**Priority:** Medium

Several files concentrate a large amount of behavior:

- [`client/lib/api.ts`](../client/lib/api.ts): approximately 1,844 lines.
- [`client/components/JobsManager.tsx`](../client/components/JobsManager.tsx): approximately 1,723 lines.
- [`client/components/ApplicationTracker.tsx`](../client/components/ApplicationTracker.tsx): approximately 1,331 lines.
- [`server/app/modules/resume_job_match/job_url_import.py`](../server/app/modules/resume_job_match/job_url_import.py): approximately 2,730 lines.

Some server-side workflows also call router-level functions, which blurs the boundary between HTTP handling and reusable application services.

**Impact**

- Unrelated changes collide in the same files.
- Unit testing requires more setup and mocking.
- HTTP concerns, orchestration, persistence, and provider-specific logic are harder to evolve independently.

**Recommendation**

- Split the client API layer by domain while preserving a small shared transport module.
- Extract stateful UI workflows into domain hooks and smaller presentational components.
- Separate URL safety, fetching, extraction, normalization, and provider adapters in job import.
- Move orchestration into application services; routers should validate HTTP input, invoke a service, and map the result to HTTP output.
- Refactor incrementally alongside feature work rather than through a single broad rewrite.

## Architectural Strengths

The review also identified important strengths worth preserving:

- **Domain-oriented backend structure.** Modules for jobs, applications, interviews, documents, profiles, reports, operations, and authentication provide a clear starting boundary.
- **Production authentication guardrails.** Startup validation rejects unsafe production authentication modes and cookie/session policies are intentionally handled.
- **Clear job-data ownership model.** Shared cached source data is separated from private saved-job state and user edits.
- **Historical provenance.** Match snapshots and generated-material versioning improve auditability and prevent later edits from silently rewriting history.
- **Allowlisted assistant actions.** Ask Scout limits executable behaviors instead of treating arbitrary model output as trusted commands.
- **URL import defenses.** The importer includes SSRF-oriented validation and security tests.
- **Migration and readiness discipline.** Alembic history, readiness validation, release metadata, and rollback retention provide a useful operational baseline.
- **Broad automated coverage.** The deployed revision passed the available server, client, lint, build, audit, migration, readiness, and route checks outside the CI secret failure.

## Target Architecture

The recommended near-term architecture remains a modular monolith, with two operational additions: a durable worker and immutable releases.

```text
                         +----------------------+
Browser ---------------->| Apache / same origin |
                         +----------+-----------+
                                    |
                      +-------------+-------------+
                      |                           |
                      v                           v
             Next.js static assets       FastAPI application
                                                  |
                         +------------------------+------------------+
                         |                        |                  |
                         v                        v                  v
                 Relational database       Durable queue      File/object store
                         ^                        |
                         |                        v
                         +---------------- Worker process
                                  short transactions
```

Recommended boundaries:

- **HTTP layer:** authentication, input validation, status codes, and response mapping.
- **Application services:** use-case orchestration and transaction boundaries.
- **Domain/repository layer:** tenant-scoped persistence and invariants.
- **Provider adapters:** OpenAI, Apify, URL fetching, email, and future integrations.
- **Worker:** durable execution of provider-backed or otherwise long-running operations.
- **Release artifact:** compiled client, server code, locked dependencies, migrations, readiness tooling, and provenance metadata.

## Remediation Roadmap

### Phase 0: Immediate Production Safety

1. Correct the client API base URL and rebuild/redeploy US3.
2. Redact the database URI at the shared-library boundary.
3. Rotate the exposed database credential.
4. Review and remediate affected log retention locations.
5. Add a browser-level authenticated production smoke test.

### Phase 1: Release Reliability

1. Restore the DaliCommonLib credential or replace the cross-repository dependency mechanism.
2. Pin Python dependencies and capture the exact shared-library revision.
3. Make the release artifact self-contained.
4. Add forbidden-development-endpoint and secret-leak scans to CI.
5. Require all release checks before deployment.

### Phase 2: Runtime Resilience

1. Consolidate authentication and domain access onto one request-scoped database session.
2. Add connection-pool telemetry and authenticated concurrency tests.
3. Introduce a durable queue and worker for managed operations.
4. Release database connections while waiting on external providers.
5. Add leases, heartbeats, idempotency, retry limits, and recovery tests.

### Phase 3: Data Lifecycle and Integrity

1. Implement durable file purge and orphan reconciliation.
2. Document account, file, log, and backup retention behavior.
3. Add database-enforced tenant relationship constraints where practical.
4. Expand negative cross-tenant tests.

### Phase 4: Maintainability

1. Split the client API module by domain.
2. Decompose the largest UI managers into hooks and focused components.
3. Extract URL-import responsibilities into small services/adapters.
4. Remove router-to-router calls in favor of application services.

## Decision Guidance

Feature development can continue after Phase 0, but provider-heavy capabilities should not expand until durable execution is in place. Any feature that stores additional sensitive documents should also wait for an explicit, tested purge lifecycle. The modular-monolith deployment model itself does not need to change; the priority is to make its configuration, background work, connection use, and release inputs reliable.

## Conclusion

DaliJob is structurally capable of supporting its current scope. Its primary risks are operational rather than a fundamental domain-design failure. Fixing the compiled API endpoint and credential logging should be treated as immediate production work. The next engineering investment should create reproducible releases and a durable execution boundary, followed by data-lifecycle enforcement and incremental module decomposition.

No source-code changes were made as part of this review.

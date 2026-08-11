# DaliJob Production Readiness Tracker

Status updated on 2026-08-04. The authentication/audit and administrator-role migrations are implemented locally and must be applied and verified before deployment.

## Purpose

This document is the source of truth for deciding whether DaliJob is ready for public registration and production use. It tracks operational and safety gates, not the broader product roadmap.

Use the following documents for adjacent concerns:

- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for product use cases and delivery order.
- [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) for the detailed capability inventory.
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for the target production operating model.
- [US3_PROD_DEPLOYMENT_PLAN.md](US3_PROD_DEPLOYMENT_PLAN.md) for the current us3 topology.
- [DATA_LIFECYCLE.md](DATA_LIFECYCLE.md) for the intended retention, export, and deletion contract.

An implemented feature is not automatically production-ready. A gate passes only when its acceptance criteria have current evidence from tests and, where applicable, production readback.

## Current Release Decision

| Release level | Decision | Reason |
| --- | --- | --- |
| Internal testing on production infrastructure | **Ready** | The current application, database, TLS routing, and provider configuration are healthy. |
| Private alpha | **Not planned** | Enrollment will use public registration with mandatory email verification instead of invites or an allowlist. |
| Public registration release | **Not ready** | Identity recovery and revocable sessions are implemented locally, but migration/deployment verification, SMTP, hosted CI, runtime supervision, and accepted deferred risks remain open. |

### Decision rule

- A public release requires every `P0` and `P1` item to be `Passed`, unless a written, dated exception is approved by the product and operations owners.
- `Deferred` is not equivalent to `Passed`.

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `Passed` | Acceptance criteria are satisfied and current evidence is linked or recorded. |
| `Partial` | A meaningful control exists, but the release gate is not fully met. |
| `Blocked` | Required control is missing or known to be unsafe. |
| `In progress` | Work has started but has not passed verification. |
| `Not started` | No implementation evidence exists. |
| `Deferred` | Deliberately excluded from the current release; rationale and approver are required. |

## Verified Production Baseline

| Check | Status | Evidence from 2026-07-17 |
| --- | --- | --- |
| Source and production provenance | `Passed` | Local `main`, `origin/main`, and us3 deployment marker all reported `95cca3f`. |
| Server tests | `Passed` | `136 passed`, with one dependency deprecation warning. |
| Client production build | `Passed` | Next.js 15.5.19 production build completed on Windows and us3. |
| Database readiness | `Passed` | `/api/v1/health/db` reported `current_revision=20260717_0024` and `database_ready=true`. |
| API and client runtime | `Passed` | API port `5020` and client port `3020` are bound only to `127.0.0.1`; both returned healthy responses. |
| Apache/TLS routing | `Passed` | Production vhost returned `200`; HSTS, frame denial, and content-type protection are present. Certbot renewal timer is active. |
| Provider credentials | `Passed` | OpenAI and Apify credentials resolved as configured without exposing their values. |
| Node runtime dependency audit | `Passed` | `npm audit --omit=dev --audit-level=high` reported zero known vulnerabilities. |
| Python environment consistency | `Passed` | `pip check` reported no broken requirements. This does not replace vulnerability scanning or dependency locking. |
| Real route traffic | `Passed` | Apache access logs showed browser loads of `/profile`, `/analytics`, `/documents`, and `/applications` after deployment. |

### Local hardening verification (2026-08-03)

The ready-now portions of SEC-001, AUTH-001, WEB-001, REL-001, FILE-001, and DEP-001 have been implemented and verified locally. This is implementation evidence, not a replacement for the production-vhost, hosted-CI, or deployment smoke checks that remain open below.

| Check | Result |
| --- | --- |
| Server tests | `177 passed`; one existing Starlette `TestClient` deprecation warning |
| Server lint | Ruff passed with no findings |
| Python dependency audit | No known vulnerabilities in `requirements-runtime.txt` |
| Client lint and tests | ESLint passed; `2` browser-policy tests passed |
| Node production dependency audit | No known vulnerabilities after updating Next.js and pinning patched `sharp` and PostCSS versions |
| Client production build | Next.js 15.5.22 build passed |
| Migration history | Linear, with one head at `20260810_0028`; deployment remains pending |
| OpenAPI contract | Regenerated from the current application; CI now fails on future drift |

## Readiness Gate Summary

| Gate | Area | Status | Required for | Blocking gap IDs |
| --- | --- | --- | --- | --- |
| G-01 | Live runtime and database | `Passed` | Public | None |
| G-02 | Network-fetch safety | `Partial` | Public | SEC-001 |
| G-03 | Identity and session safety | `In progress` | Public | AUTH-001, AUTH-002 |
| G-04 | Data backup and recovery | `Deferred` | Public | DR-001 |
| G-05 | Observability and supervision | `Partial` | Public | OPS-001, OPS-002 |
| G-06 | Reproducible CI and release | `Blocked` | Public | REL-001, QA-001 |
| G-07 | Sensitive-file handling | `Partial` | Public | FILE-001 |
| G-08 | Privacy and user data rights | `Deferred` | Public | GOV-001 |
| G-09 | Browser security policy | `Partial` | Public | WEB-001 |
| G-10 | Provider cost controls | `Partial` | Public or multi-instance | OPS-003 |

## Prioritized Gap Tracker

| ID | Priority | Track | Status | Owner role | Required for |
| --- | --- | --- | --- | --- | --- |
| SEC-001 | P0 | Backend security | `Partial` | Backend | Public |
| AUTH-001 | P0 | Identity/security | `In progress` | Backend | Public |
| AUTH-002 | P0 | Identity/product | `In progress` | Backend + Product | Public |
| DR-001 | P0 | Data durability | `Deferred` | SRE/DBA | Public |
| OPS-001 | P0 | Observability | `Partial` | SRE | Public |
| OPS-002 | P0 | Runtime supervision | `Partial` | SRE | Public |
| REL-001 | P0 | CI/release | `Partial` | Platform | Public |
| GOV-001 | P0 | Privacy/data rights | `Deferred` | Product + Backend | Public |
| FILE-001 | P1 | File security | `Partial` | Backend + SRE | Public |
| WEB-001 | P1 | Browser security | `Partial` | Frontend + SRE | Public |
| QA-001 | P1 | End-to-end quality | `Blocked` | QA/Engineering | Public |
| OPS-003 | P1 | Provider controls | `Partial` | Backend + SRE | Public or multi-instance |
| AUD-001 | P1 | Security auditability | `Partial` | Backend + SRE | Public |
| DEP-001 | P1 | Supply chain | `Partial` | Platform | Public |

## Gap Details And Acceptance Criteria

### SEC-001 - Revalidate every network destination used by job imports

**Original finding:** [`validate_public_job_url`](../server/app/modules/resume_job_match/job_url_import.py) validated the initially resolved hostname, but `urlopen` could automatically follow redirects without revalidating every hop. The Playwright fallback permitted most subrequests and navigation without applying the same public-address check. DNS could also change between validation and connection.

**Current implementation:** Static and rendered job imports now use one destination policy. It permits only public HTTP/HTTPS destinations on standard ports, resolves and validates every destination, and connects to the validated IP while retaining the original hostname for HTTP `Host` and TLS verification. Redirects are handled explicitly. Playwright frames and subrequests are routed through the same pinned-IP fetcher, and WebSockets are disabled.

**Risk:** An authenticated user can potentially turn a job-import operation into a request toward internal or link-local services. Registration is currently public, so authentication alone is not a sufficient trust boundary.

**Acceptance criteria:**

- [x] Disable automatic redirects or revalidate the scheme, hostname, resolved address, and destination port on every redirect hop.
- [x] Apply equivalent validation to Playwright top-level navigation, redirects, frames, and subrequests.
- [x] Reject URLs containing embedded credentials and reject nonstandard ports unless explicitly allowed.
- [x] Bound redirects, response bytes, render time, and total subrequests.
- [x] Add tests for redirects to loopback/private/link-local targets, public-to-private redirect chains, alternate IP encodings, and DNS-rebinding behavior.
- [ ] Run focused tests and a non-destructive production smoke test. Focused tests passed locally on 2026-07-22; production smoke testing remains pending.

**Local verification evidence (2026-08-03):** `21 passed` in `tests/test_job_url_import_security.py`; `177 passed` in the complete server test suite. The only full-suite warning is the existing Starlette `TestClient` dependency deprecation warning.

### AUTH-001 - Add authentication abuse controls and safer sessions

**Finding:** Login and registration have no dedicated throttling or lockout. Access tokens live in browser `localStorage`, last seven days, and cannot be individually revoked. Provider rate limiting does not protect authentication endpoints.

**Risk:** Password guessing and account-creation abuse are insufficiently controlled. A browser script injection can steal a long-lived bearer token.

**Current implementation:** Login and registration use configurable, process-local sliding-window limits for both source IP and normalized account identifier. Rejected requests return a generic `429` with `Retry-After`; security logs contain a hashed account prefix rather than the submitted email address. Browser authentication now uses opaque database sessions, `HttpOnly` cookies, CSRF validation, bounded idle/absolute lifetimes, and server-side revocation. The browser keeps only a non-secret UI session marker in `localStorage`. A shared limiter is required before horizontally scaling the API.

**Acceptance criteria:**

- [x] Add per-IP and per-account throttling for login and registration, with safe `429` behavior and monitoring.
- [x] Define enrollment policy: public registration with mandatory email verification; no invite-only or allowlist mode.
- [x] Replace `localStorage` bearer credentials with opaque database sessions in `HttpOnly`, `SameSite=Lax` cookies (`Secure` in production) plus double-submit CSRF protection.
- [x] Support server-side session revocation and invalidate sessions on logout, password change, account disablement, and account soft deletion.
- [x] Add tests for throttling, revocation, expiry, inactive/deleted users, single-use tokens, and CSRF/session-theft boundaries.

**Local verification evidence (2026-08-03):** Focused auth/config tests and the complete `177`-test server suite passed. Browser lint/tests/build also passed. Deployment migration, SMTP delivery, and production browser smoke verification remain open.

### AUTH-002 - Add account verification and recovery

**Current implementation:** Registration sends a one-hour, single-use verification link. Forgot-password responses do not reveal whether an account exists; reset links are single-use and revoke every session. The Account page supports password-confirmed soft deletion. SMTP is mandatory in production, while local development uses a file outbox. The support procedure is documented in `OPERATIONS_RUNBOOK.md`.

**Acceptance criteria:**

- [x] Verify account email ownership before login.
- [x] Add a time-limited, single-use password-reset flow without account enumeration.
- [x] Add a support procedure for lost access and compromised accounts.
- [ ] Audit recovery and credential-change events without logging secrets or reset tokens.

**Deployment requirement:** Apply migrations through `20260810_0028`, configure production SMTP and the public client URL, then run focused auth, administrator-boundary, tutorial-onboarding, and browser smoke tests. Audit producers currently cover administrator report updates and controlled CLI role changes; broader security-event coverage remains under AUD-001.

### DR-001 - Implement and prove backup and restore

**Decision (2026-08-03): Deferred.** The product owner chose to hold database/document backup work for a later production-readiness cycle. This is an accepted open durability risk and is not `Passed`.

**Finding:** No DaliJob-specific MySQL backup, document-storage backup, or restore job was found on us3. The only current release backup is a source archive; it does not protect the database, uploaded documents, or the prior compiled client build.

**Acceptance criteria:**

- [ ] Agree and document RPO and RTO targets.
- [ ] Back up the `jobs` schema on a schedule and retain encrypted copies outside the us3 failure domain.
- [ ] Back up `/data/dali/prod/storage/dali_job/documents` with matching retention and encryption controls.
- [ ] Monitor backup age and failures.
- [ ] Complete a restore drill into an isolated environment and verify database/document consistency.
- [ ] Record the restore date, duration, restored revision, object counts, and operator in the verification log below.

### OPS-001 - Persist application logs and activate alerts

**Current implementation:** FastAPI writes rotating structured JSON records to `api.log`, assigns/returns request IDs, and writes unhandled/HTTP-5xx alerts to a local `alerts.log`. Paths, size, and retention count are configuration-driven. The current product decision intentionally keeps alerts local; external paging and infrastructure alerting remain open.

**Acceptance criteria:**

- [ ] Persist structured API and client logs with rotation, retention, and restricted permissions. API logging is implemented; deployed Next.js stdout/stderr capture remains an operations task.
- [ ] Add a request/correlation ID across Apache, Next.js, FastAPI, managed operations, and provider logs.
- [ ] Add alerts for health/readiness failure, 5xx rate, latency, provider failures, operation backlog/staleness, disk/memory pressure, certificate renewal, and backup age/failure.
- [ ] Prove one test alert reaches the named on-call destination.
- [x] Document a minimum incident runbook and log-query procedure.

`OPERATIONS_RUNBOOK.md` now documents local queries and incident triage, but this gate remains partial until deployment capture and external health/resource alerts are proved.

### OPS-002 - Supervise service health, not only listening ports

**Finding:** The existing nanny restarts missing processes and checks ports `5020` and `3020`. A wedged service that still owns its port is considered healthy, and deployments depend on manual process replacement.

**Acceptance criteria:**

- [ ] Supervise the API using `/api/v1/health/db` and the client using an HTTP readiness probe.
- [ ] Configure restart backoff, start limits, resource limits, and durable stdout/stderr capture.
- [ ] Verify automatic recovery from API and client process termination.
- [ ] Verify behavior when the database is reachable but behind the expected Alembic revision.

### REL-001 - Make CI and releases reproducible

**Finding:** `requirements.txt` depends on editable `../DaliCommonLib`, while GitHub Actions checks out only DaliJob. Python packages are otherwise unpinned. Production currently uses the clean but separately deployed `DaliCommonLib` commit `4902676`, which is not recorded in the DaliJob release marker. `npm run lint` prompts for initial configuration and is not CI-safe. The OpenAPI job rewrites the contract but does not fail on a diff.

**Current implementation:** CI now has noninteractive lint, test, migration-history, client-build, API-contract, dependency-audit, and secret-scan jobs. The contract job fails on OpenAPI drift. A release-manifest generator records source provenance, the configured DaliCommonLib revision, dependency-file digests, the Next build ID, and the Alembic head. The workflow includes a pinned private DaliCommonLib checkout, but hosted execution still depends on configuring and validating the repository token. Python dependencies are split by runtime/test purpose but are not yet reproducibly locked with hashes.

**Acceptance criteria:**

- [ ] Package or explicitly check out and pin `DaliCommonLib` in CI and the release manifest.
- [ ] Lock Python runtime and test dependencies with hashes or an equivalent reproducible mechanism.
- [x] Make server lint, server tests, migration validation, client lint, client tests, client build, and contract verification noninteractive CI jobs.
- [x] Make OpenAPI generation fail when the checked-in contract is stale.
- [x] Produce a release manifest containing DaliJob commit, dependency-file digests, client build ID, expected Alembic head, and the DaliCommonLib state (`unmanaged-local-dependency` until that dependency decision is revisited).
- [x] Produce a versioned CI release artifact and provide scripted API/database/client readback.
- [ ] Keep and verify the previous API/client artifacts plus a database-compatible rollback or roll-forward plan.

The artifact retention and roll-forward database policy are documented in `RELEASE_AND_ROLLBACK.md`. Verification on the deployment host remains open. Per product decision, private DaliCommonLib packaging/checkout is not a current implementation target.

**Local verification evidence (2026-08-03):** Ruff, Bandit, `177` server tests, ESLint, client tests, migration-history validation, OpenAPI generation, production client build, SBOM generation, release-manifest generation, and release ZIP generation passed. A hosted GitHub Actions run remains pending.

### GOV-001 - Enforce privacy, export, deletion, and AI disclosure

**Decision (2026-08-03): Deferred.** Privacy policy, export, hard deletion, and retention/purge automation are explicitly future work. Account soft deletion is implemented but does not satisfy this gate.

**Finding:** The lifecycle contract is documented, but account/workspace export and hard deletion are not implemented. Uploaded resumes are sensitive, soft-deleted files have no purge worker, and no production privacy policy or AI disclosure was found.

**Acceptance criteria:**

- [ ] Publish privacy, retention, and AI-processing disclosures before public enrollment.
- [ ] Implement authenticated account/workspace export with expiring downloads and audit events.
- [ ] Implement account deletion across SQL data, uploaded files, generated artifacts, and outstanding download tickets.
- [ ] Implement retention and purge jobs for soft-deleted records, files, expired tickets, and completed operation payloads.
- [ ] Verify export completeness and deletion using a seeded test account in a production-like environment.

### FILE-001 - Add a safe file-processing boundary

**Existing control:** Uploads are authenticated, limited to declared PDF/plain-text content types, capped at 8 MB, assigned generated storage names, and downloaded through short-lived tickets.

**Current implementation:** PDF and plain-text uploads are now checked independently of the submitted extension. PDF signature, strict parsing, encryption, page-count, extracted-text, and byte limits are enforced. Text uploads reject PDF signatures, invalid UTF-8, binary/control-heavy content, and oversized payloads. Filenames are sanitized before metadata storage, malformed document uploads are rejected before writing, and stored files use an allowlisted suffix.

**Remaining gap:** No malware scanner or quarantine boundary exists. Parsing is still performed in the API process, and production document directories are group-writable (`775`).

**Decision (2026-08-03): Deferred boundary work.** Malware scanning, quarantine, and isolated parsing were excluded for the current small deployment. Existing signature, format, and resource-limit validation stays enabled.

**Acceptance criteria:**

- [x] Validate file signatures and parsed format independently of the submitted MIME type and extension.
- [ ] Quarantine uploads until scanning and parsing complete; never execute active content.
- [ ] Add malware scanning or isolate conversion/parsing in a restricted worker/container.
- [ ] Tighten document directory permissions to the minimum required service account access.
- [ ] Add tests for MIME spoofing, malformed PDFs, decompression/resource exhaustion, and unsafe filenames.

**Local verification evidence (2026-07-22):** `19` focused document/resume tests passed, including MIME spoofing, malformed PDF, size/page/text limits, invalid text, and unsafe filename cases. Malware and isolated-parser tests remain pending the scanner/worker decision.

### WEB-001 - Complete browser security policy

**Existing control:** HTTPS, HSTS, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff` are active.

**Current implementation:** Next.js now emits a production CSP plus Referrer, Permissions, content-type, framing, DNS-prefetch, and opener policies, and disables `X-Powered-By`. Development-only script and localhost connection allowances are excluded from production policy. Production server configuration rejects localhost, credentialed, non-HTTPS, and non-origin CORS values and disables the origin regex.

**Remaining gap:** The generated headers and CORS policy have local automated coverage, but their behavior still needs to be read back through the deployed public vhost and reverse proxy.

**Acceptance criteria:**

- [x] Add and test a restrictive Content Security Policy compatible with Next.js and required providers.
- [x] Add Referrer Policy and Permissions Policy; remove unnecessary server-identification headers.
- [x] Disable the localhost CORS regex in production and allow only intended production origins.
- [ ] Add automated header and CORS tests against the public vhost.

**Local verification evidence (2026-07-22):** Two client policy tests and the focused server configuration/CORS tests passed. Public-vhost verification remains pending deployment.

### QA-001 - Add critical browser-level end-to-end release tests

**Finding:** Server/API coverage is strong and the client builds, but the client has no automated test script and the implementation plan still records browser E2E coverage as missing.

**Acceptance criteria:**

- [ ] Automate registration/login for an isolated test environment.
- [ ] Cover resume upload/profile creation, manual job creation, URL import, matching, application creation, material attachment, interview workflow, analytics, logout, and cross-user isolation.
- [ ] Cover provider unavailable, invalid file, stale operation, migration-not-ready, and authorization failure paths.
- [ ] Run a minimal smoke subset after deployment and retain results with the release record.

### OPS-003 - Make provider limiting durable before scaling out

**Existing control:** Provider calls have in-process per-user and per-IP minute limits and structured outcome logging.

**Current decision:** DaliJob remains explicitly single-instance. Limits reset on process restart; a shared limiter is required before this decision changes. Cost/quota alerts and budgets are not connected to a durable monitoring surface.

**Acceptance criteria:**

- [x] Keep the service single-instance until a shared limiter is implemented.
- [ ] Add provider budget/quota thresholds and alerts.
- [ ] Verify the effective client IP through Apache and trusted proxy handling.
- [ ] Load-test concurrent users and confirm limits fail safely without globally throttling unrelated users.

### AUD-001 - Complete security and data-access audit logging

**Existing control:** Application lifecycle events include actor identity, and application document-download authorization is recorded.

**Current implementation:** Migration `20260803_0026` creates a unified `audit_events` structure with actor, workspace, event type, subject, source, outcome, safe JSON metadata, and timestamp. Administrator report access and updates plus controlled CLI role assignments now write bounded audit metadata. Coverage of other sensitive workflows remains incomplete.

**Acceptance criteria:**

- [x] Define a storage structure for event type, actor, subject, timestamp, source, outcome, and safe metadata.
- [ ] Record login/recovery outcomes, file access, export/deletion, privileged support, provider-key changes, and release/migration actions.
- [ ] Prevent audit records from containing passwords, tokens, raw resumes, prompts, or provider response bodies.
- [ ] Protect audit retention from ordinary user deletion while honoring the documented legal policy.

### DEP-001 - Automate dependency and secret scanning

**Existing control:** Node production audit and Python dependency consistency passed on the current host.

**Current implementation:** CI runs `pip-audit` against runtime dependencies, `npm audit` against production dependencies, Gitleaks against full repository history, and Bandit against server security-sensitive patterns. The severity/failure policy and time-limited exception requirements are documented in `SECURITY_SCANNING.md`. Each versioned artifact includes generated Python and Node SBOM files. Python dependencies are not locked reproducibly.

**Acceptance criteria:**

- [x] Add Python and Node dependency vulnerability scanning to CI with a documented severity policy.
- [x] Add secret scanning and fail on newly committed credentials.
- [x] Add targeted static checks for Python server security-sensitive patterns; focused SSRF and frontend policy tests cover the principal custom network/browser boundaries.
- [x] Produce and retain Python and Node SBOMs with each release artifact.

**Local verification evidence (2026-08-03):** `pip-audit`, Bandit, and the production `npm audit` reported no blocking findings after updating Next.js/PostCSS. Gitleaks execution remains to be proven by the hosted CI run.

## Items That Are Not Current Readiness Blockers

The following remain product-roadmap work unless the release scope promises them:

- Shared Dalifin identity and cross-product single sign-on.
- Email and calendar integrations.
- Workspace sharing and role-based collaboration.
- Additional job-provider plugins.
- Full DOCX/PDF rendering beyond the currently supported document workflow.
- Multi-instance API deployment, provided the single-instance limitation is explicit and shared provider limiting is completed before scaling.

## Release Verification Checklist

Run this checklist for every production candidate. Never print secret values into the release record.

### Source and CI

- [ ] Worktree is clean and the intended commit matches `origin/main`.
- [ ] All required CI jobs pass on a clean runner.
- [ ] Release manifest records DaliJob, DaliCommonLib, dependency lock, client build, and Alembic versions.
- [ ] Server tests, client tests, browser smoke tests, and contract verification pass.

### Database and storage

- [ ] A current backup exists and its age is within the agreed RPO.
- [ ] Migration preflight confirms one Alembic head and the intended upgrade path.
- [ ] Production migration reaches the expected revision.
- [ ] `/api/v1/health/db` reports `database_ready=true` and matching current/expected revisions.
- [ ] Document storage is writable only by the intended service identity and backup age is healthy.

### Runtime and public routing

- [ ] API and client start from the recorded release artifact.
- [ ] Localhost API/client health checks pass.
- [ ] Public HTTPS root, authenticated API smoke flow, and `/applications` route pass.
- [ ] `https://dalifin.com/job_match` redirects to the intended host.
- [ ] Security headers and restrictive CORS are verified on the public vhost.
- [ ] Error logs and dashboards show no deployment regression.

### Recovery

- [ ] Previous application artifacts remain available.
- [ ] Rollback or roll-forward steps are compatible with the migrated schema.
- [ ] On-call owner and incident channel are recorded.

## Verification Log

Add one row per production release or formal readiness review.

| Date | DaliJob commit | Database revision | Decision | Verified by | Evidence/notes |
| --- | --- | --- | --- | --- | --- |
| 2026-07-17 | `95cca3f` | `20260717_0024` | Internal ready; private alpha conditional; public not ready | Codex review | 136 server tests passed; production client build passed; API/DB healthy; TLS and providers ready; blockers recorded above. |

## Decision Log

Use this section for approved exceptions or changes to release criteria.

| Date | Decision | Rationale | Owner/approver | Review date |
| --- | --- | --- | --- | --- |
| 2026-07-17 | Treat current us3 deployment as internal testing, not public-production approval. | Live runtime is healthy, but P0 security, recovery, observability, release, and data-governance gates remain open. | Pending assignment | Before private-alpha enrollment |
| 2026-08-03 | Use public registration with mandatory email verification; no invite-only/private-alpha enrollment. | Registration remains accessible while email ownership is proved before account use. | Product owner | Before public deployment |
| 2026-08-03 | Use opaque revocable server sessions with secure cookies and CSRF protection. | Browser-readable seven-day bearer credentials are not an acceptable public-session boundary. | Product owner | Annual security review |
| 2026-08-03 | Soft-delete accounts after password confirmation and revoke all sessions. | Immediate account disablement is required; hard deletion/purge remains part of deferred governance work. | Product owner | With GOV-001 |
| 2026-08-03 | Keep DaliJob single-instance and keep alerts in rotating local files for now. | Shared limiting and external monitoring are unnecessary for current scale but required before horizontal scaling/public operations maturity. | Product owner | Before multi-instance deployment |
| 2026-08-03 | Defer backups, malware isolation, and privacy/retention automation. | Product owner accepted these as later work for the current small deployment; deferred is not passed. | Product owner | Before public release approval |
| 2026-08-03 | Use versioned artifacts, retain at least two successful releases, and roll database changes forward. | This avoids unsafe automatic schema downgrade and gives a defined application rollback boundary. | Product owner | Every release |
| 2026-08-03 | Create the audit event schema without event producers. | Preserve the intended contract while postponing data population and retention enforcement. | Product owner | Before AUD-001 can pass |

## Maintenance Rules

- Update this tracker in the same pull request that closes or changes a gap.
- Link concrete test, configuration, runbook, dashboard, or production-readback evidence before setting an item to `Passed`.
- Re-open a passed gate when its evidence is stale, the architecture changes, or production behavior contradicts it.
- Review all P0/P1 items before every public release and at least quarterly while the service is active.
- Keep roadmap capability status out of this file unless it changes a production safety boundary.

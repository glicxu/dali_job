# DaliJob Production Readiness Tracker

Production was reviewed on 2026-07-17 against deployed application commit `95cca3f`. On 2026-07-20, a versioned worktree candidate based on `f725192` was deployed to us3 after clean host-side verification. Because that candidate contains uncommitted implementation changes, it is identified by its deployment marker and artifact SHA-256 rather than represented as a clean Git commit. This runtime validation does not change the private-alpha or public-release decision below.

## Purpose

This document is the source of truth for deciding whether DaliJob is ready for a controlled private alpha or a public production release. It tracks operational and safety gates, not the broader product roadmap.

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
| Internal testing on production infrastructure | **Conditional** | Runtime health is verified, but public registration must be disabled or restricted to an explicit allowlist before continued testing on an internet-reachable host. |
| Controlled private alpha | **Not ready** | SEC-001, AUTH-001, DR-001, OPS-001, OPS-002, and REL-001 must all pass before enrollment. |
| Public production release | **Not ready** | Security, identity recovery, privacy rights, monitoring, backup/restore, and automated release gates remain incomplete. |

### Decision rule

- Gap rows in the Prioritized Gap Tracker are authoritative; the gate table is a roll-up and cannot weaken a gap's `Required for` value.
- Internet-reachable internal testing requires registration to be disabled or restricted to an explicit allowlist, even before private alpha.
- A private alpha requires every gap marked **Private alpha** in the `Required for` column to be `Passed`.
- A public release requires every `P0` and `P1` gap to be `Passed`, unless a written, dated exception is approved by named product and operations owners.
- An unassigned owner or pending approval is not an approved exception.
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

## Recorded Production Baseline

These are point-in-time observations from 2026-07-17, not evidence for a later release candidate. The review summary is recorded below, but a durable evidence bundle was not linked. Future release records must link retained CI output, command output, configuration readback, or monitoring evidence as applicable.

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

## Latest Deployment Readback (2026-07-20)

| Check | Result | Evidence |
| --- | --- | --- |
| Candidate provenance | `Passed with limitation` | Marker `f725192-wt-20260720T164600Z`; artifact SHA-256 `d0ddb359a99431523055a1e669480ce37c818cffa2bb2c934d54c10c781038ad`. The candidate is based on `f725192` but is not a clean Git commit. |
| Clean us3 build and tests | `Passed` | Fresh Python environment: `pip check`, linear migration history, and `138 passed`. Fresh npm install: lint, 3 unit tests, Next.js production build, and production dependency audit with zero known vulnerabilities. |
| Database migration/readiness | `Passed` | Alembic upgrade completed as a no-op; `/api/v1/health/db` reported current and expected revision `20260717_0024` with `database_ready=true`. |
| Runtime and public routing | `Passed` | API/client listen on `127.0.0.1:5020` and `127.0.0.1:3020`; public `/`, `/auth`, `/jobs`, `/match`, `/materials`, and both health endpoints returned `200`. `https://dalifin.com/job_match` returned `302` to the public application and then `200`. |
| New API surface | `Passed` | Live OpenAPI contains `/api/v1/application-materials/versions/{version_id}/render`. |
| Supervision recovery | `Passed after operational correction` | The long-running nanny had stale in-memory configuration (`managed_count=16`). It was restarted, loaded all 18 services, detected the stopped DaliJob API, and restored it. |
| Rollback readiness | `Passed` | Complete prior runtime tree retained at `/home/dali-op/dali/dali_job_previous_95cca3f_20260720T164800Z`; no database downgrade is required because the schema revision did not change. |

This is deployment readback, not a durable evidence bundle and not approval of the remaining release gaps.

## Readiness Gate Summary

| Gate | Area | Status | Required for | Blocking gap IDs |
| --- | --- | --- | --- | --- |
| G-01 | Live runtime and database | `Passed` | Private alpha, Public | None |
| G-02 | Network-fetch safety | `Blocked` | Private alpha, Public | SEC-001 |
| G-03a | Authentication and session safety | `Blocked` | Private alpha, Public | AUTH-001 |
| G-03b | Identity verification and recovery | `Blocked` | Public | AUTH-002 |
| G-04 | Data backup and recovery | `Blocked` | Private alpha, Public | DR-001 |
| G-05 | Observability and supervision | `Blocked` | Private alpha, Public | OPS-001, OPS-002 |
| G-06a | Reproducible CI and release | `Partial` | Private alpha, Public | REL-001 |
| G-06b | Browser end-to-end release tests | `Partial` | Public | QA-001 |
| G-07 | Sensitive-file handling | `Partial` | Public | FILE-001 |
| G-08 | Privacy and user data rights | `Blocked` | Public | GOV-001 |
| G-09 | Browser security policy | `Partial` | Public | WEB-001 |
| G-10 | Provider cost controls | `Partial` | Public or multi-instance | OPS-003 |

## Readiness Closure Plan

This plan closes gates in dependency order. It does not add email, calendar, shared identity, collaboration, or additional provider work to the release scope.

### Phase 0 - Contain the current internet-reachable deployment

**Goal:** Make continued internal testing acceptable while longer-lived controls are built.

- [ ] Disable public self-registration or restrict enrollment to an explicit server-side allowlist.
- [ ] Name accountable product, backend, platform, SRE/DBA, and incident-response owners.
- [ ] Record the on-call destination and the durable location for release evidence.
- [ ] Commit the currently deployed worktree changes, reconcile them with `origin/main`, and replace the worktree deployment with an artifact tied to a clean commit.
- [ ] Record the enrollment decision and responsible approver in the Decision Log.

**Exit criterion:** The live host is no longer accepting uncontrolled enrollment, release provenance is unambiguous, and operational ownership is recorded. Until then, the deployment remains conditional internal testing only.

### Phase 1 - Establish the repeatable release foundation

**Goal:** Ensure every later security or operational change can be tested, deployed, evidenced, and rolled back consistently.

| Order | Gap | Deliverable | Required evidence |
| --- | --- | --- | --- |
| 1.1 | REL-001 | Lock Python dependencies; generate a release manifest; build a versioned artifact; automate preflight, deployment, readback, and rollback retention. | First successful hosted CI run, dependency-lock digest, artifact digest, manifest, deployment log, and production readback. |
| 1.2 | DEP-001 subset | Add Python/Node vulnerability scanning, secret scanning, and the agreed severity policy to CI. | Retained clean-run output and documented exception process. |
| 1.3 | OPS-001 foundation | Persist restricted, rotated API/client logs and propagate request IDs across the request path. | Production log samples with sensitive values redacted and a verified cross-service request trace. |

**Exit criterion:** A clean commit produces one identifiable artifact through hosted CI, the artifact can be promoted with retained evidence, and production activity can be traced without relying on `/tmp` logs.

### Phase 2 - Close the private-alpha safety gates

**Goal:** Satisfy every gap whose `Required for` value is **Private alpha**.

Work can proceed concurrently within this phase, but all five workstreams must finish before enrollment:

| Workstream | Gaps | Implementation focus | Completion proof |
| --- | --- | --- | --- |
| Network boundary | SEC-001 | Validate every redirect and browser request destination; bind scheme, address, port, size, subrequest, and time limits. | Adversarial unit/integration tests plus a non-destructive deployed smoke test. |
| Enrollment and sessions | AUTH-001 | Add login/registration throttling, enforce invite/allowlist enrollment, shorten and protect sessions, and support revocation. | Abuse, expiry, revocation, inactive-user, and session-boundary tests; production configuration readback. |
| Data recovery | DR-001 | Define RPO/RTO; back up MySQL and documents outside the us3 failure domain; monitor backup age. | Successful isolated restore drill with revision, object counts, elapsed time, and operator recorded. |
| Monitoring and supervision | OPS-001, OPS-002 | Add actionable alerts and health-based supervision with backoff, limits, and durable logs. | Test alert reaches the named on-call destination; API/client termination recovery and migration-not-ready behavior are verified. |
| Release completion | REL-001 | Retain manifests, CI output, readback, rollback proof, and the completed checklist for the candidate. | A durable evidence bundle linked from the Verification Log. |

**Exit criterion:** SEC-001, AUTH-001, DR-001, OPS-001, OPS-002, and REL-001 are all `Passed`, every checkbox in their acceptance criteria has linked evidence, and no private-alpha exception is implicit or ownerless.

### Phase 3 - Run the private-alpha release drill

**Goal:** Prove the controls together on one clean candidate before inviting users.

- [ ] Run hosted CI from a clean commit and retain all required job results.
- [ ] Verify migration history and both a fresh-schema and previous-revision upgrade path.
- [ ] Deploy the versioned artifact using the scripted workflow.
- [ ] Run localhost health, public routing, authenticated application-flow, and minimal browser smoke tests.
- [ ] Exercise API/client recovery and verify alert delivery.
- [ ] Confirm current database and document backups, then verify the retained rollback artifact is schema-compatible.
- [ ] Complete the Release Verification Checklist and add one fully evidenced Verification Log row.
- [ ] Obtain an explicit, dated private-alpha decision from the named product and operations owners.

**Exit criterion:** One candidate satisfies the complete private-alpha checklist with current evidence and explicit approval. Evidence from different candidates must not be combined to manufacture a pass.

### Phase 4 - Close public-release gates

**Goal:** Add the user-protection and scale controls required before public enrollment.

Recommended order:

1. Implement account verification and recovery (AUTH-002).
2. Implement export, deletion, retention, purge, privacy, and AI disclosures together with the audit model (GOV-001 and AUD-001).
3. Harden file validation, quarantine, scanning/isolation, and storage permissions (FILE-001).
4. Enforce CSP, Referrer Policy, Permissions Policy, restrictive production CORS, and header tests (WEB-001).
5. Complete critical UC-01-UC-05 browser journeys, cross-user isolation, and failure-path coverage (QA-001).
6. Add shared provider limiting or explicitly retain the single-instance constraint; add budgets and quota alerts (OPS-003).
7. Complete static security checks and retain an SBOM for the release (DEP-001).
8. Run the full release drill again and obtain an explicit public-release decision.

**Exit criterion:** Every P0 and P1 gap is `Passed`, or a named product and operations owner has approved a written, dated exception. All public promises and disclosures match implemented behavior.

### Status and evidence rules

- Move a gap to `In progress` only when an owner and active implementation are recorded.
- Move a gap to `Passed` only when every acceptance checkbox is complete and its retained evidence is linked.
- Update the gate summary, gap tracker, verification checklist, Verification Log, and Decision Log in the same change that alters a release decision.
- Re-run affected acceptance tests after architecture, dependency, deployment, or production-configuration changes.
- Do not count deferred roadmap items as readiness work or use them to delay closure of the listed gates.

## Prioritized Gap Tracker

| ID | Priority | Track | Status | Owner role | Required for |
| --- | --- | --- | --- | --- | --- |
| SEC-001 | P0 | Backend security | `Blocked` | Backend | Private alpha |
| AUTH-001 | P0 | Identity/security | `Blocked` | Backend | Private alpha |
| AUTH-002 | P0 | Identity/product | `Blocked` | Backend + Product | Public |
| DR-001 | P0 | Data durability | `Blocked` | SRE/DBA | Private alpha |
| OPS-001 | P0 | Observability | `Blocked` | SRE | Private alpha |
| OPS-002 | P0 | Runtime supervision | `Partial` | SRE | Private alpha |
| REL-001 | P0 | CI/release | `Partial` | Platform | Private alpha |
| GOV-001 | P0 | Privacy/data rights | `Blocked` | Product + Backend | Public |
| FILE-001 | P1 | File security | `Partial` | Backend + SRE | Public |
| WEB-001 | P1 | Browser security | `Partial` | Frontend + SRE | Public |
| QA-001 | P1 | End-to-end quality | `Partial` | QA/Engineering | Public |
| OPS-003 | P1 | Provider controls | `Partial` | Backend + SRE | Public or multi-instance |
| AUD-001 | P1 | Security auditability | `Partial` | Backend + SRE | Public |
| DEP-001 | P1 | Supply chain | `Partial` | Platform | Public |

## Gap Details And Acceptance Criteria

### SEC-001 - Revalidate every network destination used by job imports

**Finding:** [`validate_public_job_url`](../server/app/modules/resume_job_match/job_url_import.py) validates the initially resolved hostname, but `urlopen` can automatically follow redirects without revalidating every hop. The Playwright fallback permits most subrequests and navigation without applying the same public-address check. DNS can also change between validation and connection.

**Risk:** An authenticated user can potentially turn a job-import operation into a request toward internal or link-local services. Registration is currently public, so authentication alone is not a sufficient trust boundary.

**Acceptance criteria:**

- [ ] Disable automatic redirects or revalidate the scheme, hostname, resolved address, and destination port on every redirect hop.
- [ ] Apply equivalent validation to Playwright top-level navigation, redirects, frames, and subrequests.
- [ ] Reject URLs containing embedded credentials and reject nonstandard ports unless explicitly allowed.
- [ ] Bound redirects, response bytes, render time, and total subrequests.
- [ ] Add tests for redirects to loopback/private/link-local targets, public-to-private redirect chains, alternate IP encodings, and DNS-rebinding behavior.
- [ ] Run focused tests and a non-destructive production smoke test.

### AUTH-001 - Add authentication abuse controls and safer sessions

**Finding:** Login and registration have no dedicated throttling or lockout. Access tokens live in browser `localStorage`, last seven days, and cannot be individually revoked. Provider rate limiting does not protect authentication endpoints.

**Risk:** Password guessing and account-creation abuse are insufficiently controlled. A browser script injection can steal a long-lived bearer token.

**Acceptance criteria:**

- [ ] Add per-IP and per-account throttling for login and registration, with safe `429` behavior and monitoring.
- [ ] Define an enrollment policy for private alpha: invite-only, allowlist, or verified email.
- [ ] Replace seven-day `localStorage` bearer tokens with a documented short-lived access/session design. Prefer `HttpOnly`, `Secure`, `SameSite` cookies where compatible with the architecture.
- [ ] Support server-side session revocation and invalidate sessions when an account is disabled or credentials change.
- [ ] Add tests for throttling, revocation, expiry, inactive users, and session theft boundaries.

### AUTH-002 - Add account verification and recovery

**Finding:** The current local-auth flow has registration and login only. Email verification, password reset, recovery, and administrative account-support procedures are absent.

**Acceptance criteria:**

- [ ] Verify account email ownership or keep public registration disabled.
- [ ] Add a time-limited, single-use password-reset flow without account enumeration.
- [ ] Add a support procedure for lost access and compromised accounts.
- [ ] Audit recovery and credential-change events without logging secrets or reset tokens.

### DR-001 - Implement and prove backup and restore

**Finding:** No DaliJob-specific MySQL backup, document-storage backup, or restore job was found on us3. The only current release backup is a source archive; it does not protect the database, uploaded documents, or the prior compiled client build.

**Acceptance criteria:**

- [ ] Agree and document RPO and RTO targets.
- [ ] Back up the `jobs` schema on a schedule and retain encrypted copies outside the us3 failure domain.
- [ ] Back up `/data/dali/prod/storage/dali_job/documents` with matching retention and encryption controls.
- [ ] Monitor backup age and failures.
- [ ] Complete a restore drill into an isolated environment and verify database/document consistency.
- [ ] Record the restore date, duration, restored revision, object counts, and operator in the verification log below.

### OPS-001 - Persist application logs and activate alerts

**Finding:** Apache access/error logs are persisted and rotated, but the intended DaliJob API/client service log directories are empty. The current processes write startup output to temporary files under `/tmp`. No DaliJob error, latency, provider-failure, disk, memory, or backup alerts were found.

**Acceptance criteria:**

- [ ] Persist structured API and client logs with rotation, retention, and restricted permissions.
- [ ] Add a request/correlation ID across Apache, Next.js, FastAPI, managed operations, and provider logs.
- [ ] Add alerts for health/readiness failure, 5xx rate, latency, provider failures, operation backlog/staleness, disk/memory pressure, certificate renewal, and backup age/failure.
- [ ] Prove one test alert reaches the named on-call destination.
- [ ] Document a minimum incident runbook and log-query procedure.

### OPS-002 - Supervise service health, not only listening ports

**Finding:** The existing nanny restarts missing processes and checks ports `5020` and `3020`. A wedged service that still owns its port is considered healthy, and deployments depend on manual process replacement.

**Acceptance criteria:**

- [ ] Supervise the API using `/api/v1/health/db` and the client using an HTTP readiness probe.
- [ ] Configure restart backoff, start limits, resource limits, and durable stdout/stderr capture.
- [ ] Verify automatic recovery from API and client process termination.
- [ ] Verify behavior when the database is reachable but behind the expected Alembic revision.

### REL-001 - Make CI and releases reproducible

**Finding:** CI now explicitly checks out pinned `DaliCommonLib` commit `4902676`, runs separate server lint/tests, MySQL migration paths, client lint/unit/browser tests, build, and fails on a stale OpenAPI contract. The repository must configure `DALI_COMMON_LIB_TOKEN` and retain a successful hosted run. Python runtime packages remain unlocked, and versioned release artifacts, manifests, rollback evidence, and production readback are still missing.

**Acceptance criteria:**

- [x] Package or explicitly check out and pin `DaliCommonLib` in CI.
- [ ] Record the pinned `DaliCommonLib` revision in the release manifest.
- [ ] Lock Python runtime and test dependencies with hashes or an equivalent reproducible mechanism.
- [x] Make server lint, server tests, migration validation, client lint, client tests, client build, and contract verification noninteractive CI jobs.
- [x] Make OpenAPI generation fail when the checked-in contract is stale.
- [ ] Produce a release manifest containing DaliJob commit, DaliCommonLib commit/version, dependency-lock digest, client build ID, and expected Alembic head.
- [ ] Deploy from a versioned artifact or scripted release workflow with preflight checks and production readback.
- [ ] Keep and verify the previous API/client artifacts plus a database-compatible rollback or roll-forward plan.
- [ ] Retain a release evidence bundle containing CI links/output, deployment logs, production readback, and the completed verification checklist.

### GOV-001 - Enforce privacy, export, deletion, and AI disclosure

**Finding:** The lifecycle contract is documented, but account/workspace export and hard deletion are not implemented. Uploaded resumes are sensitive, soft-deleted files have no purge worker, and no production privacy policy or AI disclosure was found.

**Acceptance criteria:**

- [ ] Publish privacy, retention, and AI-processing disclosures before public enrollment.
- [ ] Implement authenticated account/workspace export with expiring downloads and audit events.
- [ ] Implement account deletion across SQL data, uploaded files, generated artifacts, and outstanding download tickets.
- [ ] Implement retention and purge jobs for soft-deleted records, files, expired tickets, and completed operation payloads.
- [ ] Verify export completeness and deletion using a seeded test account in a production-like environment.

### FILE-001 - Add a safe file-processing boundary

**Existing control:** Uploads are authenticated, limited to declared PDF/plain-text content types, capped at 8 MB, assigned generated storage names, and downloaded through short-lived tickets.

**Remaining gap:** The declared MIME type is client-controlled, file signatures are not verified, and no malware/quarantine boundary exists. Production document directories are group-writable (`775`).

**Acceptance criteria:**

- [ ] Validate file signatures and parsed format independently of the submitted MIME type and extension.
- [ ] Quarantine uploads until scanning and parsing complete; never execute active content.
- [ ] Add malware scanning or isolate conversion/parsing in a restricted worker/container.
- [ ] Tighten document directory permissions to the minimum required service account access.
- [ ] Add tests for MIME spoofing, malformed PDFs, decompression/resource exhaustion, and unsafe filenames.

### WEB-001 - Complete browser security policy

**Existing control:** HTTPS, HSTS, `X-Frame-Options: DENY`, and `X-Content-Type-Options: nosniff` are active.

**Remaining gap:** No Content Security Policy, Referrer Policy, or Permissions Policy was observed. Next.js advertises `X-Powered-By`. Production CORS still accepts localhost through the default origin regex in addition to `https://jobmatch.dalifin.com`.

**Acceptance criteria:**

- [ ] Add and test a restrictive Content Security Policy compatible with Next.js and required providers.
- [ ] Add Referrer Policy and Permissions Policy; remove unnecessary server-identification headers.
- [ ] Disable the localhost CORS regex in production and allow only intended production origins.
- [ ] Add automated header and CORS tests against the public vhost.

### QA-001 - Add critical browser-level end-to-end release tests

**Finding:** Server/API coverage is strong, client unit tests now cover authentication behavior, and a Playwright smoke test covers registration, authenticated navigation, and logout. The complete resume, job, matching, application, material, interview, analytics, isolation, and failure-path browser suite remains incomplete.

**Acceptance criteria:**

- [x] Automate registration/login for an isolated test environment.
- [ ] Cover resume upload/profile creation, manual job creation, URL import, matching, application creation, material attachment, interview workflow, analytics, logout, and cross-user isolation.
- [ ] Cover provider unavailable, invalid file, stale operation, migration-not-ready, and authorization failure paths.
- [ ] Run a minimal smoke subset after deployment and retain results with the release record.

### OPS-003 - Make provider limiting durable before scaling out

**Existing control:** Provider calls have in-process per-user and per-IP minute limits and structured outcome logging.

**Remaining gap:** Limits reset on process restart and are not shared between instances. Cost/quota alerts and budgets are not connected to a durable monitoring surface.

**Acceptance criteria:**

- [ ] Keep the service single-instance until a shared limiter is implemented, or move limits to a durable shared store.
- [ ] Add provider budget/quota thresholds and alerts.
- [ ] Verify the effective client IP through Apache and trusted proxy handling.
- [ ] Load-test concurrent users and confirm limits fail safely without globally throttling unrelated users.

### AUD-001 - Complete security and data-access audit logging

**Existing control:** Application lifecycle events include actor identity, and application document-download authorization is recorded.

**Remaining gap:** There is no unified audit log for authentication, recovery, direct document access, export/deletion, administrative support, configuration, and release actions.

**Acceptance criteria:**

- [ ] Define audited event types, actor, subject, timestamp, source, outcome, and safe metadata.
- [ ] Record login/recovery outcomes, file access, export/deletion, privileged support, provider-key changes, and release/migration actions.
- [ ] Prevent audit records from containing passwords, tokens, raw resumes, prompts, or provider response bodies.
- [ ] Protect audit retention from ordinary user deletion while honoring the documented legal policy.

### DEP-001 - Automate dependency and secret scanning

**Existing control:** Node production audit and Python dependency consistency passed on the current host.

**Remaining gap:** CI does not run dependency vulnerability scans, secret scans, static security checks, or produce a software bill of materials. Python versions are not locked.

**Acceptance criteria:**

- [ ] Add Python and Node dependency vulnerability scanning to CI with a documented severity policy.
- [ ] Add secret scanning and fail on newly committed credentials.
- [ ] Add targeted static checks for FastAPI, subprocess/network fetches, unsafe deserialization, and frontend injection sinks.
- [ ] Produce and retain an SBOM for each release.

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

- [ ] Every gap required for the intended release level is `Passed`, or has a written, dated exception approved by named product and operations owners.
- [ ] Enrollment mode matches the release level; registration is disabled or explicitly allowlisted for internet-reachable internal testing and private alpha.
- [ ] A durable evidence-bundle location is recorded in the Verification Log.

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

| Date | Tracker commit | Application commit | DaliCommonLib commit | Database revision | Decision | Verified by | Evidence/notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-17 | `f725192` | `95cca3f` | `4902676` | `20260717_0024` | Internal conditional; private alpha not ready; public not ready | Codex review; accountable human not recorded | 136 server tests passed; production client build passed; API/DB healthy; TLS and providers ready. Durable evidence bundle not linked; do not reuse this row for a later candidate. |
| 2026-07-20 | `f725192` | `f725192-wt-20260720T164600Z` | `4902676` | `20260717_0024` | Deployed for internal validation; private alpha not ready; public not ready | Codex deployment verification; accountable human not recorded | Artifact SHA-256 `d0ddb359a99431523055a1e669480ce37c818cffa2bb2c934d54c10c781038ad`; clean us3 build/tests passed; public health and route smoke passed; nanny recovery corrected and verified; rollback tree retained. Candidate contains uncommitted changes and no durable evidence-bundle location is recorded. |

## Decision Log

Use this section for release decisions, approved exceptions, or changes to release criteria. A row marked as not approved records the current risk decision but does not authorize a release or exception.

| Date | Decision | Rationale | Owner/approver | Review date |
| --- | --- | --- | --- | --- |
| 2026-07-17 | Treat current us3 deployment as conditional internal testing, not private-alpha or public-production approval. Disable or allowlist registration before continued internet-reachable testing. | Live runtime is healthy, but registration is public and P0 security, recovery, observability, release, and data-governance gates remain open. | Not approved; named product and operations owners required | Before further internet-reachable testing |

## Maintenance Rules

- Update this tracker in the same pull request that closes or changes a gap.
- Link concrete test, configuration, runbook, dashboard, or production-readback evidence before setting an item to `Passed`.
- Re-open a passed gate when its evidence is stale, the architecture changes, or production behavior contradicts it.
- Review all P0/P1 items before every public release and at least quarterly while the service is active.
- Keep roadmap capability status out of this file unless it changes a production safety boundary.

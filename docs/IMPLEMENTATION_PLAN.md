# DaliJob Implementation Plan

Status reviewed on 2026-07-14.

## Purpose

This plan turns the business and architecture reviews into an executable build sequence. It is organized around complete user outcomes first, then the platform and operations work required to deliver those outcomes safely.

The existing [implementation checklist](IMPLEMENTATION_CHECKLIST.md) remains the detailed capability inventory. This document defines priority, scope, dependencies, acceptance criteria, and release boundaries.

## Planning Decision: Split The Use Cases First

DaliJob should not be implemented as one broad "career management" feature. Split it into independently testable use cases so that each release leaves the product usable:

| ID | Use case | User outcome | Current state |
| --- | --- | --- | --- |
| UC-01 | Establish a private career workspace | Register, sign in, and access only owned data | Implemented; hardening remains |
| UC-02 | Build a reusable resume foundation | Import, review, create, edit, and select resume profiles | Implemented |
| UC-03 | Build a candidate job pipeline | Manually add, paste, import, search, analyze, and save jobs | Implemented; failure handling remains |
| UC-04 | Decide where to apply | Compare a resume with jobs and review evidence and gaps | Implemented; result versioning remains |
| UC-05 | Track an application | Convert a saved job into an application and maintain its status/history | Implemented; current migration head must be applied per environment |
| UC-06 | Manage application materials | Attach exact resume and document versions to an application | Implemented |
| UC-07 | Manage next actions | Record tasks, deadlines, follow-ups, and reminders | Implemented for in-app reminders |
| UC-08 | Prepare for interviews | Create interview records and generate reviewable preparation material | Not implemented |
| UC-09 | Learn from outcomes | Review funnel, response, interview, offer, and source metrics | Not implemented |

Ops/admin use cases are separate from candidate workflows:

| ID | Operations use case | Outcome |
| --- | --- | --- |
| OP-01 | Secure production behavior | Unsafe auth modes, cross-user access, and unprotected costly actions fail closed |
| OP-02 | Control provider cost and reliability | Provider calls are limited, measured, diagnosable, and recoverable |
| OP-03 | Build and release repeatably | A clean checkout can pass CI, migrate, deploy, and be verified |
| OP-04 | Govern sensitive data | Retention, access audit, export, deletion, and backup rules are enforceable |
| OP-05 | Support the service | Failures can be diagnosed without exposing provider secrets or unrelated user data |

## Implementation Track Split

The implementation backlog must keep two explicit tracks:

- **User track:** job-seeker screens, user-owned APIs, and workflows that directly deliver UC-01 through UC-09.
- **Ops/admin track:** deployment, configuration, secrets, migrations, provider controls, monitoring, support diagnostics, and data-governance work that delivers OP-01 through OP-05.

Work from both tracks may ship in the same release when one enables the other, but it must remain separately scoped and testable. A user story must not contain hidden deployment or provider-administration work, and an ops/admin story must not introduce candidate-facing behavior without a linked user use case.

An ops/admin use case does not imply an admin UI. CLI, configuration, deployment automation, database tooling, logs, and restricted support queries remain appropriate until repeated operational demand justifies a first-class admin product.

## Product And Data Boundaries

All implementation work must preserve one central rule: shared source facts and user-owned decisions are different data.

- `jobs_cache` contains reusable source/provider data only.
- `user_saved_jobs` contains a user's relationship to a job.
- `user_edited_jobs` contains private manual entries and corrections.
- `resume_profiles` contains user-owned structured resume facts.
- `job_resume_matches` contains a comparison against exact resume and job inputs.
- `applications` contains the user's real application workflow and must not be folded into saved-job state.
- Future document attachments point to immutable document versions, not mutable logical documents.

Manual entry and pasted text remain supported fallbacks. OpenAI, Apify, scraping, email, and calendar integrations accelerate a workflow but must not be prerequisites for it.

## Delivery Plan

### Phase 0: Protect The Current MVP While Preserving Change

Implementation status: partially completed on 2026-07-14. UX-01, SEC-01, DATA-01, and the current single-server OPS-01 scope are complete. CI-01 and automated deployment migration-readiness work remain deferred.

Use cases: UC-01 through the implemented UC-05 slice, OP-01 through OP-03.

Goal: create a safe experimentation boundary around the implemented resume, job, matching, and application-tracking workflows without treating the current product or architecture as final.

Phase 0 establishes security, privacy, data-ownership, and build-reproducibility invariants only. APIs, schemas, workflows, UI structure, providers, deployment topology, and background-work technology remain provisional unless a later decision explicitly promotes them to stable contracts.

Flexibility rules:

- Use the smallest reversible implementation that protects the invariant.
- Prefer configuration and replaceable adapters over product-wide frameworks.
- Test observable safety and ownership behavior, not incidental UI structure or internal implementation details.
- Keep schema changes additive or easily migratable while the domain model is still evolving.
- Record provisional decisions and their replacement conditions; do not present them as permanent architecture.
- Defer generalized infrastructure until more than one concrete use case needs it or production evidence justifies it.

#### User track

1. [x] **UX-01: Complete degraded-mode paths** - Implemented 2026-07-14.
   - [x] On parse or extraction failure, retain entered data and offer retry or manual paste/edit.
   - [x] Ensure saved jobs can still be created and used when providers are unavailable.
   - [x] Preserve the user outcome without standardizing the final screen flow or component structure.

#### Ops/admin track

1. [ ] **CI-01: Make clean-checkout CI reproducible** - Deferred by the project owner; the private `DaliCommonLib` checkout will be addressed later.
   - [ ] Use the simplest documented method to provide `DaliCommonLib` to Python CI jobs; an explicit checkout is acceptable until the library's packaging strategy is settled.
   - [ ] Run server tests, migration checks, OpenAPI checks, client lint/tests, and client build as separate visible jobs.
   - [x] Document the current dependency provenance and make clear that it is replaceable.

2. [ ] **DB-01: Enforce migration readiness** - The readiness endpoint is implemented for head `20260715_0021`; deployment enforcement remains deferred.
   - [ ] Verify that the configured database is at the current Alembic head during deployment.
   - [x] Report the current and expected migration revisions through `/api/v1/health/db`.
   - [ ] Test both a fresh database upgrade and an upgrade from the previous supported revision.
   - [x] Keep schema migration commands in the release procedure so new code is not served against missing tables.

3. [x] **SEC-01: Enforce production startup policy** - Implemented 2026-07-14.
   - [x] Reject production startup when `auth_mode` is `dev` or `disabled`.
   - [x] Continue rejecting missing, empty, or known-default local JWT secrets.
   - [x] Add a lightweight authorization inventory for every non-health `/api/v1` route and test the protected boundary without freezing route or response design.

4. [x] **DATA-01: Enforce shared-versus-private job ownership** - Implemented 2026-07-14.
   - [x] Accept shared cache writes only from source extraction or provider-normalization paths.
   - [x] Store user edits and manual jobs in `user_edited_jobs`.
   - [x] Add cross-user tests proving that one user's edits cannot change another user's view of cached source data.
   - [x] Treat the ownership rule as stable while allowing table shapes, service boundaries, and repository implementations to evolve.

5. [x] **OPS-01: Add provider guardrails** - Implemented for the current single-server deployment on 2026-07-14.
   - [x] Start with one minimal structured provider-call record containing provider, feature, user, duration, outcome, and available usage units.
   - [x] Add configurable limits at the narrowest existing provider entry points; begin with simple per-user or per-IP limits and add broader quota accounting only when usage requires it.
   - [x] Return actionable timeout, quota, extraction, and parse errors without leaking secrets.
   - [x] Do not introduce a full operations dashboard, generalized provider framework, or background queue in this phase.

Exit criteria:

- [ ] A clean CI runner builds and tests the server and client without an undeclared sibling checkout.
- [ ] Deployment verifies that the configured database is at the expected Alembic head before the release is considered ready.
- [x] Production refuses unsafe auth configuration.
- [x] Auth, ownership, provider-limit, and shared-cache isolation tests pass.
- [x] Provider failures produce a recoverable user path rather than a generic 500.
- [ ] Current UC-01 through UC-05 smoke tests pass end to end, including automated migration readiness for the application tracker.
- [x] Phase 0 tests protect the invariants above without making provisional APIs, schemas, or UI details costly to change.

### Phase 1: Preserve User Control And Historical Meaning

Implementation status: completed in the application and documented on 2026-07-14. Account/workspace export and hard-deletion execution remain future worker-backed implementation; this phase defines their contract in `DATA_LIFECYCLE.md`.

Use cases: UC-01 through UC-04, OP-04.

Goal: ensure current data can be deleted or interpreted later now that applications depend on saved jobs and future features will depend on historical matches.

#### User track

1. [x] **DATA-02: Add archive and deletion controls**
   - [x] Add owner-scoped document deletion and saved-job archive/delete actions.
   - [x] Show dependency warnings before a resume profile or document used by another record is removed.
   - [x] Prevent deletion of a saved job while an application references it; require the application relationship to be resolved or retain the saved job as archived history.

2. [x] **MATCH-01: Preserve understandable match history**
   - [x] Display when a saved match is older than the current resume or job data.
   - [x] Let the user run a new match without overwriting the historical result.

#### Ops/admin track

1. [x] **DATA-02 support: Enforce safe record lifecycle**
   - [x] Add server-owned resume-profile dependency checks and orphan prevention.
   - [x] Add a server-owned saved-job dependency check that rejects deletion while an application references the saved job.
   - [x] Define whether soft-deleted shared cache records may be reactivated and keep that behavior server-owned.

2. [x] **MATCH-01 support: Version match inputs**
   - [x] Store immutable match-time snapshots of resume JSON and effective job JSON, or link to explicit immutable versions.
   - [x] Store model, prompt/schema version, timestamp, and provider execution reference.

3. [x] **PRIV-01: Define data lifecycle**
   - [x] Document retention for uploaded files, extracted text, provider payloads, and AI outputs.
   - [x] Add account/workspace export and deletion design, including asynchronous cleanup and audit requirements.

Exit criteria:

- [x] Users can archive or delete supported owned records without creating orphan references.
- [x] Attempts to delete a saved job referenced by an application are rejected with an actionable dependency message.
- [x] Historical matches remain explainable after resume or job edits.
- [x] The retention/export/deletion contract is documented and covered by repository tests where implemented.

### Phase 2: Complete And Harden The Application Tracker Vertical Slice

Implementation status: code complete on 2026-07-14. Configured-environment migration verification and browser-level end-to-end coverage remain open release checks.

User use case: UC-05. Ops/admin support: OP-01, OP-03, and OP-05.

Goal: finish the implemented initial slice so the core career-search loop has durable lifecycle rules, safe dependencies, and a release-ready migration path.

Current implementation:

- Application tables, owner-scoped APIs, tracker/detail UI, notes, timeline events, status history, tasks, and task due dates are implemented.
- Migration `20260714_0019` adds the final lifecycle vocabulary, interview stage, and concurrency-safe active-duplicate guard.
- `GET /api/v1/health/db` reports `503 not_ready` until the configured database is at the current migration head.

#### User track

- [x] Preserve the tracker list, application detail view, notes, tasks, and timeline workflow.
- [x] Add filtering by lifecycle status and optional application stage.
- [x] Keep "Create application" tied to a saved job; a saved job remains distinct from its application.
- [x] Complete owner-scoped list/filter, update, archive, restore, and status-transition behavior through the client.
- [x] Warn when a duplicate active application exists and require explicit confirmation before creating another one for the same saved job.

#### Ops/admin track

- [x] Retain `applications`, `application_status_history`, `application_events`, `application_notes`, and `application_tasks`.
- [x] Use `interested`, `applied`, `interviewing`, `offer`, `accepted`, `rejected`, and `withdrawn` as lifecycle statuses.
- [x] Add nullable `stage`: `recruiter_contact`, `assessment`, `phone_screen`, `technical_interview`, or `final_interview`.
- [x] Keep document readiness outside lifecycle status.
- [x] Represent archival only through `archived_at`; remove `archived` from lifecycle status.
- [x] Enforce allowed lifecycle transitions in the server and expose allowed next states to the client.
- [x] Prevent accidental duplicate active applications with a server check and database uniqueness guard; allow explicit duplicates and new attempts after terminal/archive outcomes.
- [x] Reject deletion of a `user_saved_jobs` row while any application references it.
- [x] Add migration, owner-authorization, transition, duplicate, dependency, event, and readiness tests.

Out of scope for this phase:

- Email-driven status changes.
- Calendar sync.
- AI-generated documents.
- Advanced analytics.
- Shared workspaces or collaboration roles.

Acceptance criteria:

- [x] A user can create from a saved job and must confirm an active duplicate.
- [x] Every status change appends an event containing old status, new status, actor, and time.
- [x] Invalid transitions are rejected by server rules.
- [x] Lifecycle status, interview stage, document readiness, and archival state remain separate concepts.
- [x] A saved job referenced by an application cannot be deleted.
- [x] User A cannot list, read, change, or infer User B's application records.
- [x] The tracker and detail page work without AI or provider access.
- [x] Local configured database is at `20260715_0022`; `/api/v1/health/db` reports `database_ready: true`.
- [ ] API contract, repository, migration, client, and browser-level end-to-end tests cover the complete slice. Server/API tests and the production client build pass; browser-level end-to-end coverage remains.

### Phase 3: Add Application Materials And Next Actions

Implementation status: completed in code on 2026-07-15. The local configured database was verified at head `20260715_0022`.

Use cases: UC-06 and UC-07.

Goal: make each application operationally complete without introducing external integrations.

#### User track

1. [x] **DOC-01: Immutable application attachments**
   - [x] Add attach, detach, list, and download flows for submitted resumes, cover letters, and supporting material.
   - [x] Show the exact version attached to the application.

2. [x] **TASK-01: Tasks and reminders**
   - [x] Preserve application task title, due time, and completion behavior.
   - [x] Add task type, optional reminder time, task filtering, reminder dismissal, and rescheduling.
   - [x] Surface overdue and upcoming actions on the dashboard and application detail page.
   - [x] Keep reminders in-app; external notifications remain a later integration.

#### Ops/admin track

- [x] Add `application_documents` linking an application to an exact `document_version_id` and attachment purpose.
- [x] Enforce owner checks and record attachment and one-time download-ticket audit data.
- [x] Put downloads behind five-minute, one-time opaque tickets; storage paths are never returned to the client.
- [x] Extend task persistence and indexes with task type, reminder, dismissal, and update state without external notification infrastructure.

Acceptance criteria:

- [x] The application shows exactly which immutable document version was submitted.
- [x] Replacing a document creates a new version and does not alter historical attachments.
- [x] Users can create, complete, reschedule, and filter application tasks.
- [x] Dashboard next-step logic includes overdue and upcoming application actions.
- [x] Local configured database is at `20260715_0022`; `/api/v1/health/db` reports `database_ready: true`.

### Phase 4: Move Costly Work Behind A Managed Execution Boundary

Implementation status: completed in code on 2026-07-15. The local configured database was verified at head `20260715_0022`.

User use cases: UC-03, UC-04, and future UC-08. Ops/admin use cases: OP-02 and OP-05.

Goal: prevent provider latency and failures from controlling API request lifecycles.

#### User track

- [x] Show durable progress for current searches, imports, parsing, and matching; keep the same contract available for later interview preparation.
- [x] Allow the user to leave and return without losing operation state.
- [x] Show a useful failure reason and safe retry action.

#### Ops/admin track

- [x] Define a provider-neutral AI interface and normalized job-search provider interface.
- [x] Add background execution for bulk import, provider search, parsing, and bulk matching, with a reusable handler boundary for later interview preparation.
- [x] Store queued/running/succeeded/failed/cancelled state, progress, attempts, errors, model/actor, prompt version, and usage.
- [x] Add idempotency keys and bounded retries for safe operations.
- [x] Add polling first; introduce push updates only if polling becomes inadequate.
- [x] Add operations views or queries for failed work and provider health without exposing full secrets.

Acceptance criteria:

- [x] Expensive UI workflows enqueue through `/api/v1/operations/*` and return a durable operation ID promptly.
- [x] Refreshing the UI does not lose progress or create duplicate provider work.
- [x] Failed work can be retried safely and shows a useful user-facing reason.
- [x] Provider-specific data stays behind normalized server contracts.
- [x] Local configured database is at `20260715_0022`; `/api/v1/health/db` reports `database_ready: true`.

### Phase 5: Add Interview Preparation

Implementation status: completed in code on 2026-07-15. The local configured database was verified at head `20260715_0022`.

User use case: UC-08. Ops/admin support: OP-02 and OP-05.

Goal: help a user prepare from application-owned context after the tracker and async execution model are stable.

#### User track

- [x] Interview records with application, type, schedule, stage, outcome, and private notes.
- [x] Prep request using an exact resume profile snapshot, effective saved-job snapshot, and optional company notes.
- [x] Reviewable outputs: study priorities, likely questions, evidence-backed talking points, and skill gaps.

#### Ops/admin track

- [x] Prompt/model/version provenance and explicit warnings when source evidence is absent.
- [x] Provider usage, failure, and latency records for preparation jobs.
- [x] Support-safe retry diagnostics that exclude resume and interview content from routine logs.

Acceptance criteria:

- [x] Interview records work without AI.
- [x] Generated preparation is linked to exact inputs and can be regenerated without overwriting earlier output.
- [x] Output never silently adds unsupported resume claims; exact resume evidence is verified server-side.
- [x] Provider failure does not block interview scheduling or notes.
- [x] Local configured database is at `20260715_0022`; `/api/v1/health/db` reports `database_ready: true`.

### Phase 6: Add Outcome Analytics

Implementation status: completed in code on 2026-07-15. The local configured database was verified at head `20260715_0023`.

User use case: UC-09. Ops/admin support: OP-04 and OP-05.

Goal: show descriptive metrics only after application and outcome data exists.

#### User track

- [x] Applications by status and date range.
- [x] Response, interview, offer, rejection, and withdrawal rates.
- [x] Time from applied to first response and interview.
- [x] Source and exact attached resume-version performance with sample size shown.

#### Ops/admin track

- [x] Define and version metric formulas, denominators, time zones, and event-source rules.
- [x] Add reproducible aggregation tests and support diagnostics for stale or incomplete analytics.
- [x] Keep candidate analytics isolated from global service-usage and provider-cost reporting.

Acceptance criteria:

- [x] Metrics are derived from application events, application-time source snapshots, and exact historical document versions.
- [x] Definitions and denominators are visible and tested.
- [x] Small samples are labeled; the product does not present weak correlations as recommendations.
- [x] Local configured database is at `20260715_0023`; `/api/v1/health/db` reports `database_ready: true`.

### Phase 7: Add Resume Tailoring And External Integrations Only After The Core Loop Is Stable

User use cases: UC-06 through UC-09. Ops/admin support: OP-01, OP-02, OP-04, and OP-05.

#### User track

Candidate sequence:

1. Email classification that proposes reviewable application events.
2. Calendar sync for confirmed interviews and reminders.
3. Resume tailoring and cover-letter generation tied to exact application/document versions.
4. Additional job-source providers behind normalized interfaces.

#### Ops/admin track

Integration controls:

- OAuth credentials are encrypted, revocable, and never exposed to the client.
- Inbound email classifications propose changes; they do not silently mutate application status.
- Every integration can be disconnected without breaking manual workflows.
- Universal scraping, shared workspaces, and a large admin console remain deferred until supported by demonstrated demand.

## Dependency And Release Sequence

| Phase | User track | Ops/admin track |
| --- | --- | --- |
| 0 | Recoverable current MVP workflows | CI, migration readiness, production auth, ownership enforcement, provider guardrails |
| 1 | Archive/delete controls and understandable match history | Referential integrity, snapshots, retention/export/deletion policy |
| 2 | Complete and harden the implemented application tracker and detail workflow | Lifecycle/stage separation, duplicate prevention, transitions, authorization, dependency protection, audit, migration readiness |
| 3 | Attachments and completion of tasks/in-app reminders | Version enforcement, signed access, access audit, reminder persistence |
| 4 | Durable progress and retry experience | Background execution, provider abstraction, idempotency, failure operations |
| 5 | Interviews and preparation | AI provenance, provider usage, safe diagnostics |
| 6 | Candidate outcome analytics | Metric governance, aggregation integrity, data isolation |
| 7 | Resume tailoring and connected user workflows | AI provenance, OAuth security, revocation, provider health, integration audit |

```text
Phase 0 safe experimentation boundary
    -> Phase 1 history and user control
        -> Phase 2 application tracker completion and hardening
            -> Phase 3 application documents and reminder completion
                -> Phase 4 managed provider work
                    -> Phase 5 interview preparation
            -> Phase 6 outcome analytics
                -> Phase 7 resume tailoring and external integrations
```

Phase 6 depends on stable application events, but it does not need to wait for interview-preparation AI. Phase 4 may be pulled forward when real request latency or volume creates operational pain; its data model must still support the later phases.

## Definition Of Done By Track

### User track

- The job seeker can complete the stated outcome through the client without database or CLI intervention.
- The workflow remains usable through its documented manual or degraded path when an optional provider fails.
- Client, API-contract, and critical browser-flow tests pass.
- User-facing errors explain the next safe action.
- Product documentation and OpenAPI reflect the delivered behavior.

### Ops/admin track

- The server owns authorization, validation, state transitions, and data-boundary rules.
- Schema migration and downgrade or rollback implications are reviewed.
- Unit, repository, authorization, isolation, and operational failure tests pass.
- Sensitive values and user content are excluded from routine logs and diagnostics.
- Metrics, limits, errors, and support diagnostics exist for cost-bearing work.
- Deployment verification covers health, migration state, configuration safety, and rollback readiness.

### Release gate

A release that links a user use case to ops/admin support is complete only when both track definitions are satisfied. The ops/admin track may finish independently when it improves safety or operability without changing candidate behavior.

## Current Executable Backlog

UX-01, SEC-01, DATA-01, and the single-server OPS-01 guardrails are implemented. The current application migration was applied and verified. CI-01 and automated DB-01 release verification are intentionally deferred and remain required before a public or repeatable production release.

### Ops/admin track

1. CI-01 clean-checkout dependency and job separation when private `DaliCommonLib` CI access is addressed.
2. DB-01 automated migration-head verification for fresh, upgraded, and deployed databases before repeatable production releases.
3. Replace in-process provider limits with a shared limiter before running multiple server instances.

### User track

1. MATCH-01 understandable, version-aware match history.
2. UC-05 application tracker completion: lifecycle/stage separation, duplicate confirmation, transition enforcement, saved-job deletion protection, filtering, and user-flow tests.

Complete the minimum Phase 0 ops/admin gates before treating the implemented application tracker as release-ready, but manage and review the two backlogs separately.

Each backlog item should become a small issue or pull request with its own acceptance criteria. Do not split a vertical slice into server-only and client-only milestones that leave no usable outcome.

# DaliJob Implementation Plan

Status reviewed on 2026-07-13.

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
| UC-05 | Track an application | Convert a saved job into an application and maintain its status/history | Not implemented |
| UC-06 | Manage application materials | Attach exact resume and document versions to an application | Partially implemented at document-library level |
| UC-07 | Manage next actions | Record tasks, deadlines, follow-ups, and reminders | Not implemented |
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
- Future `applications` contain the user's real application workflow and must not be folded into saved-job state.
- Future document attachments point to immutable document versions, not mutable logical documents.

Manual entry and pasted text remain supported fallbacks. OpenAI, Apify, scraping, email, and calendar integrations accelerate a workflow but must not be prerequisites for it.

## Delivery Plan

### Phase 0: Protect The Current MVP While Preserving Change

Use cases: UC-01 through UC-04, OP-01 through OP-03.

Goal: create a safe experimentation boundary around the implemented resume, job, and matching funnel without treating the current product or architecture as final.

Phase 0 establishes security, privacy, data-ownership, and build-reproducibility invariants only. APIs, schemas, workflows, UI structure, providers, deployment topology, and background-work technology remain provisional unless a later decision explicitly promotes them to stable contracts.

Flexibility rules:

- Use the smallest reversible implementation that protects the invariant.
- Prefer configuration and replaceable adapters over product-wide frameworks.
- Test observable safety and ownership behavior, not incidental UI structure or internal implementation details.
- Keep schema changes additive or easily migratable while the domain model is still evolving.
- Record provisional decisions and their replacement conditions; do not present them as permanent architecture.
- Defer generalized infrastructure until more than one concrete use case needs it or production evidence justifies it.

#### User track

1. **UX-01: Complete degraded-mode paths**
   - On parse or extraction failure, retain entered data and offer retry or manual paste/edit.
   - Ensure saved jobs can still be created and used when providers are unavailable.
   - Preserve the user outcome without standardizing the final screen flow or component structure.

#### Ops/admin track

1. **CI-01: Make clean-checkout CI reproducible**
   - Use the simplest documented method to provide `DaliCommonLib` to Python CI jobs; an explicit checkout is acceptable until the library's packaging strategy is settled.
   - Run server tests, migration checks, OpenAPI checks, client lint/tests, and client build as separate visible jobs.
   - Document the current dependency provenance and make clear that it is replaceable.

2. **SEC-01: Enforce production startup policy**
   - Reject production startup when `auth_mode` is `dev` or `disabled`.
   - Continue rejecting missing, empty, or known-default local JWT secrets.
   - Add a lightweight authorization inventory for every non-health `/api/v1` route and test the protected boundary without freezing route or response design.

3. **DATA-01: Enforce shared-versus-private job ownership**
   - Accept shared cache writes only from source extraction or provider-normalization paths.
   - Store user edits and manual jobs in `user_edited_jobs`.
   - Add cross-user tests proving that one user's edits cannot change another user's view of cached source data.
   - Treat the ownership rule as stable while allowing table shapes, service boundaries, and repository implementations to evolve.

4. **OPS-01: Add provider guardrails**
   - Start with one minimal structured provider-call record containing provider, feature, user, duration, outcome, and available usage units.
   - Add configurable limits at the narrowest existing provider entry points; begin with simple per-user or per-IP limits and add broader quota accounting only when usage requires it.
   - Return actionable timeout, quota, extraction, and parse errors without leaking secrets.
   - Do not introduce a full operations dashboard, generalized provider framework, or background queue in this phase.

Exit criteria:

- A clean CI runner builds and tests the server and client without an undeclared sibling checkout.
- Production refuses unsafe auth configuration.
- Auth, ownership, provider-limit, and shared-cache isolation tests pass.
- Provider failures produce a recoverable user path rather than a generic 500.
- Current UC-01 through UC-04 smoke tests pass end to end.
- Phase 0 tests protect the invariants above without making provisional APIs, schemas, or UI details costly to change.

### Phase 1: Preserve User Control And Historical Meaning

Use cases: UC-01 through UC-04, OP-04.

Goal: ensure current data can be deleted or interpreted later before applications depend on it.

#### User track

1. **DATA-02: Add archive and deletion controls**
   - Add owner-scoped document deletion and saved-job archive/delete actions.
   - Show dependency warnings before a resume profile or document used by another record is removed.

2. **MATCH-01: Preserve understandable match history**
   - Display when a saved match is older than the current resume or job data.
   - Let the user run a new match without overwriting the historical result.

#### Ops/admin track

1. **DATA-02 support: Enforce safe record lifecycle**
   - Add server-owned resume-profile dependency checks and orphan prevention.
   - Define whether soft-deleted shared cache records may be reactivated and keep that behavior server-owned.

2. **MATCH-01 support: Version match inputs**
   - Store immutable match-time snapshots of resume JSON and effective job JSON, or link to explicit immutable versions.
   - Store model, prompt/schema version, timestamp, and provider execution reference.

3. **PRIV-01: Define data lifecycle**
   - Document retention for uploaded files, extracted text, provider payloads, and AI outputs.
   - Add account/workspace export and deletion design, including asynchronous cleanup and audit requirements.

Exit criteria:

- Users can archive or delete supported owned records without creating orphan references.
- Historical matches remain explainable after resume or job edits.
- The retention/export/deletion contract is documented and covered by repository tests where implemented.

### Phase 2: Deliver The Application Tracker Vertical Slice

User use case: UC-05. Ops/admin support: OP-01, OP-03, and OP-05.

Goal: close the core career-search loop by turning a saved job into a trackable application.

#### User track

- Add a tracker page grouped or filtered by status.
- Add an application detail page with job summary, current status, notes, and timeline.
- Add a "Create application" action from a saved job; a saved job remains distinct from its application.
- Provide owner-scoped create, read, list/filter, update, archive, and status-transition behavior through the client.

#### Ops/admin track

- `applications` table with `id`, owner/workspace keys, `user_saved_job_id`, status, applied date, next-action date, notes, timestamps, and soft-delete/archive state.
- `application_status_history` table for immutable status transitions and `application_events` for the broader timeline and user notes.
- Use the status vocabulary already defined in `DATABASE_DESIGN.md`: `saved`, `planning`, `resume_tailored`, `cover_letter_ready`, `applied`, `recruiter_contact`, `oa_scheduled`, `oa_completed`, `phone_screen`, `technical_interview`, `final_interview`, `offer`, `accepted`, `rejected`, and `withdrawn`.
- Add migrations, owner-authorization tests, transition-rule tests, structured audit events, and support-safe failure diagnostics.

Out of scope for this phase:

- Email-driven status changes.
- Calendar sync.
- AI-generated documents.
- Advanced analytics.
- Shared workspaces or collaboration roles.

Acceptance criteria:

- A user can create an application from a saved job and cannot create an accidental duplicate active application without confirmation.
- Every status change produces an immutable event containing old status, new status, actor, and time.
- Invalid transitions are rejected by server rules, not only hidden by the client.
- User A cannot list, read, change, or infer User B's application records.
- The tracker and detail page work without AI or provider access.
- API contract, repository, migration, client, and end-to-end tests cover the complete slice.

### Phase 3: Add Application Materials And Next Actions

Use cases: UC-06 and UC-07.

Goal: make each application operationally complete without introducing external integrations.

#### User track

1. **DOC-01: Immutable application attachments**
   - Add attach, detach, list, and download flows for submitted resumes, cover letters, and supporting material.
   - Show the exact version attached to the application.

2. **TASK-01: Tasks and reminders**
   - Add application tasks with type, due time, completion state, and optional reminder time.
   - Surface overdue and upcoming actions on the dashboard and application detail page.
   - Start with in-app reminders; external notifications are a later integration.

#### Ops/admin track

- Add `application_documents` linking an application to an exact `document_version_id` and attachment purpose.
- Enforce owner checks and record document-access audit events.
- Move storage behind signed URLs or an equivalent short-lived authorization boundary before broad public use.
- Add task/reminder persistence, due-time indexes, and support diagnostics without introducing external notification infrastructure.

Acceptance criteria:

- The application shows exactly which immutable document version was submitted.
- Replacing a document creates a new version and does not alter historical attachments.
- Users can create, complete, reschedule, and filter application tasks.
- Dashboard next-step logic includes overdue and upcoming application actions.

### Phase 4: Move Costly Work Behind A Managed Execution Boundary

User use cases: UC-03, UC-04, and future UC-08. Ops/admin use cases: OP-02 and OP-05.

Goal: prevent provider latency and failures from controlling API request lifecycles.

#### User track

- Show durable progress for searches, imports, parsing, matching, and later interview preparation.
- Allow the user to leave and return without losing operation state.
- Show a useful failure reason and safe retry action.

#### Ops/admin track

- Define a provider-neutral AI interface and normalized job-search provider interface.
- Add background execution for bulk import, provider search, parsing, bulk matching, and later interview preparation.
- Store queued/running/succeeded/failed/cancelled state, progress, attempts, errors, model/actor, prompt version, and usage.
- Add idempotency keys and bounded retries for safe operations.
- Add polling first; introduce push updates only if polling becomes inadequate.
- Add operations views or queries for failed work and provider health without exposing full secrets.

Acceptance criteria:

- Expensive endpoints return a durable operation ID promptly.
- Refreshing the UI does not lose progress or create duplicate provider work.
- Failed work can be retried safely and shows a useful user-facing reason.
- Provider-specific data stays behind normalized server contracts.

### Phase 5: Add Interview Preparation

User use case: UC-08. Ops/admin support: OP-02 and OP-05.

Goal: help a user prepare from application-owned context after the tracker and async execution model are stable.

#### User track

- Interview records with application, type, schedule, stage, outcome, and private notes.
- Prep request using an exact resume version/snapshot, job version/snapshot, and optional company notes.
- Reviewable outputs: study priorities, likely questions, evidence-backed talking points, and skill gaps.

#### Ops/admin track

- Prompt/model/version provenance and explicit warnings when source evidence is absent.
- Provider usage, failure, and latency records for preparation jobs.
- Support-safe retry diagnostics that exclude resume and interview content from routine logs.

Acceptance criteria:

- Interview records work without AI.
- Generated preparation is linked to exact inputs and can be regenerated without overwriting earlier output.
- Output never silently adds unsupported resume claims.
- Provider failure does not block interview scheduling or notes.

### Phase 6: Add Outcome Analytics

User use case: UC-09. Ops/admin support: OP-04 and OP-05.

Goal: show descriptive metrics only after application and outcome data exists.

#### User track

- Applications by status and date range.
- Response, interview, offer, rejection, and withdrawal rates.
- Time from applied to first response and interview.
- Source and resume-version performance with sample size shown.

#### Ops/admin track

- Define and version metric formulas, denominators, time zones, and event-source rules.
- Add reproducible aggregation tests and support diagnostics for stale or incomplete analytics.
- Keep candidate analytics isolated from global service-usage and provider-cost reporting.

Acceptance criteria:

- Metrics are derived from application events and exact historical versions.
- Definitions and denominators are visible and tested.
- Small samples are labeled; the product does not present weak correlations as recommendations.

### Phase 7: Add External Integrations Only After The Core Loop Is Stable

User use cases: UC-07 through UC-09. Ops/admin support: OP-01, OP-02, OP-04, and OP-05.

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
| 0 | Recoverable current MVP workflows | CI, production auth, ownership enforcement, provider guardrails |
| 1 | Archive/delete controls and understandable match history | Referential integrity, snapshots, retention/export/deletion policy |
| 2 | Application tracker and detail workflow | Schema, transitions, authorization, audit, support diagnostics |
| 3 | Attachments, tasks, and in-app reminders | Version enforcement, signed access, access audit, reminder persistence |
| 4 | Durable progress and retry experience | Background execution, provider abstraction, idempotency, failure operations |
| 5 | Interviews and preparation | AI provenance, provider usage, safe diagnostics |
| 6 | Candidate outcome analytics | Metric governance, aggregation integrity, data isolation |
| 7 | Connected user workflows | OAuth security, revocation, provider health, integration audit |

```text
Phase 0 safe experimentation boundary
    -> Phase 1 history and user control
        -> Phase 2 application tracker
            -> Phase 3 documents and next actions
                -> Phase 4 managed provider work
                    -> Phase 5 interview preparation
            -> Phase 6 outcome analytics
                -> Phase 7 external integrations
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

## First Executable Backlog

### Ops/admin track

1. CI-01 clean-checkout dependency and job separation.
2. SEC-01 production startup policy and route authorization matrix.
3. DATA-01 shared cache/private edit enforcement.
4. OPS-01 provider usage logging, limits, and error mapping.

### User track

1. UX-01 parse/extraction retry and manual fallback.
2. MATCH-01 understandable, version-aware match history.
3. UC-05 application tracker behavior, UI, and user-flow tests.

Complete the minimum Phase 0 ops/admin gates before releasing the application tracker, but manage and review the two backlogs separately.

Each backlog item should become a small issue or pull request with its own acceptance criteria. Do not split a vertical slice into server-only and client-only milestones that leave no usable outcome.

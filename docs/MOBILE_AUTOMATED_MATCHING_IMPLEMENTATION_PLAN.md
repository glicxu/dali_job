# Mobile Automated Matching Implementation Plan

**Status:** Implementation in progress as of August 14, 2026
**Product direction:** Simple mobile onboarding with backend-driven recurring job search and resume matching
**Related review:** [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md)

## Implementation Progress

### Foundation slice — implemented August 14, 2026

- Created feature branch `mobile-automated-matching`.
- Added Alembic revision `20260814_0032` and registered `user_subscriptions`, `usage_ledger`, `search_schedules`, and `search_runs` in SQLAlchemy metadata.
- Added validated, versioned tier-entitlement configuration; approved defaults now allow 1, 3, and 5 successful provider searches per weekly period for Free, Starter, and Plus.
- Added automatic Free subscription assignment for new accounts and migration backfill for existing accounts.
- Added atomic, idempotent provider-search reservation, consumption, release, usage summary, and weekly period rollover behavior.
- Added tier and entitlement snapshots to usage records so later configuration changes do not rewrite history.
- Extended account deletion to cancel subscriptions and runs, pause schedules, and soft-delete automation records.
- Added focused automation tests.

### Schedule and dispatcher slice — implemented August 14, 2026

- Added authenticated entitlement, schedule CRUD, pause/resume/delete, run-list, and usage-summary API contracts.
- Enforced tier-specific active-criteria limits and minimum search intervals at the API boundary.
- Added a database dispatcher using locked due-schedule claims, occurrence idempotency, and quota reservation.
- Dispatcher output is limited to durable queued `managed_operations` and `search_runs`; it does not invoke providers.
- Quota-exhausted schedules are deferred to the next entitlement period without repeated provider attempts.
- Deleting a schedule cancels its queued run and operation and releases unconsumed quota.
- Added an operator CLI and release-contained module entry point for dispatching due schedules.
- Updated OpenAPI and database-readiness definitions.

### Durable worker foundation — implemented August 14, 2026

- Added bounded worker attempts, lease ownership, lease expiration, and heartbeat state to search runs.
- Added atomic queued/stale-run claiming with locked rows and duplicate-worker exclusion.
- Worker claims and commits before invoking its executor, so provider work runs without an open database session.
- Added short success/failure finalization transactions that synchronize search runs and managed operations.
- Quota remains reserved across retryable failures, is consumed after success or a confirmed provider call, and is released when a terminal failure occurs before any provider call.
- Added heartbeat extension, stale-lease recovery, conservative exhausted-attempt handling, and a bounded run-draining API for a future supervisor.
- Added safe generic error reporting that does not persist arbitrary exception details.

### Provider executor and persistence slice — implemented August 14, 2026

- Worker claims now include immutable keyword, location, resume, threshold, and result-limit snapshots.
- Added the production adapter for Apify search followed by OpenAI job parsing and resume matching.
- Provider work and heartbeat calls execute without retaining a request/database session.
- Added transactional result persistence that normalizes shared cache data, deduplicates source URLs, and saves only matches meeting the schedule threshold.
- Repeated provider results reuse existing saved jobs and exact resume/job snapshot matches instead of creating duplicates.
- Operation results retain IDs and safe warnings rather than raw resume or job artifacts.
- Added a supervised worker service with bounded draining, polling, leases, SIGINT/SIGTERM shutdown, and a one-pass operator mode.
- The complete server suite passes with 253 tests.

### In-app notification and match-inbox slice — implemented August 14, 2026

- Added Alembic revision `20260814_0033` for notification preferences and durable notification deliveries.
- Qualifying canonical jobs now create one in-app delivery per user, schedule, and job; retries and rediscovery reuse the existing delivery.
- Added notification-preference APIs with IANA timezone validation, digest mode, default threshold, and optional quiet hours.
- Added tenant-scoped match-inbox list, detail, and idempotent mark-read APIs with stable cursor pagination.
- Account deletion suppresses pending deliveries before soft-deleting notification data.
- Daily email delivery is enabled by default and can be disabled through notification preferences.

### Mobile session backend slice — implemented August 14, 2026

- Added Alembic revision `20260814_0034`, extending the shared session model with explicit browser/mobile types, device labels, token-family identifiers, and refresh expiry.
- Added opaque mobile bearer access tokens and hashed, single-use refresh-token records; reusable plaintext credentials are never persisted.
- Refresh rotation has a fixed family lifetime, row locking, replacement lineage, and reuse detection that revokes the entire device session.
- Added mobile login, refresh, device listing, device revocation, and current-device logout APIs.
- Password reset and account deletion revoke browser sessions, mobile access tokens, and every refresh token in the affected mobile families.
- Browser sessions retain cookie/CSRF enforcement; bearer-authenticated mobile writes do not depend on browser cookies.

### Mobile usage and automation contract slice — implemented August 14, 2026

- Added `GET /api/v1/account/usage` with current-period allowance totals and stable cursor pagination over auditable usage entries.
- Added tenant-scoped `GET /api/v1/automation/runs/{run_id}` and stable cursor pagination for the automation run list.
- New schedules use the user's notification-preference threshold when the request omits a threshold; explicit schedule values remain authoritative.
- Mobile device-session listing now uses stable descending-ID cursor pagination.

### Daily digest delivery slice — implemented August 14, 2026

- Qualifying matches now create idempotent pending email-delivery records when daily email is enabled.
- Added a separately supervised digest service and `scripts/send_notification_digests.py` entry point.
- Digest claims use delivery leases and stale-lease recovery; network delivery occurs without an open database session.
- Digest assembly respects each user's IANA timezone, the configured local digest hour, and optional quiet hours.
- Email content contains job details, score, concise rationale, and match/job links, but no resume content.
- Failed sends use bounded exponential retry, safe error storage, terminal failure state, and structured operational logging.
- Account deletion suppresses both pending and in-flight digest deliveries.

### Revised-resume manual rerun slice — implemented August 14, 2026

- Reused `POST /api/v1/resume-job-matches/saved-jobs` for user-selected past-job reruns rather than adding a duplicate mobile-only endpoint.
- Added immutable match provenance values: `direct_match`, `manual_rerun`, and `automated_search` through Alembic revision `20260814_0036`.
- A rerun after a resume revision creates a new match snapshot while preserving the prior resume/job snapshots and staleness history.
- Manual reruns create neither automatic inbox/email notifications nor weekly provider-search usage entries.

Not yet implemented: a native mobile UI, native deep-link routing, Apple/Google subscription validation, or deployment of the dispatcher/search-worker/digest-worker services.

## 1. Product Goal

Deliver a mobile-first DaliJob experience in which a user:

1. Creates and verifies an account.
2. Uploads and confirms a resume profile.
3. Defines one or more job-search criteria, subject to their tier.
4. Enables automatic searches.
5. Receives the first usable provider result as the single match for that automated run.
6. Reviews those matches in a simple mobile inbox.

The backend performs provider searches, deduplication, resume matching, quota enforcement, scheduling, and notification delivery. The mobile application is primarily an onboarding, configuration, and results client.

## 2. MVP Boundaries

### In scope

- First-party account registration, email verification, login, logout, recovery, and session revocation.
- Mobile-safe authentication based on short-lived access tokens and rotating refresh tokens.
- One confirmed resume profile per user for the initial release.
- Job-search criteria creation, editing, pausing, and deletion.
- Free, Starter, and Plus entitlement levels.
- Metered provider-search executions per weekly usage period.
- Durable periodic scheduling and execution.
- Job deduplication and automatic resume matching.
- One first-usable match per automated search, with an optional user-adjustable score floor.
- Email and in-app match notifications for the first release.
- A mobile match inbox with job details and match rationale.
- A Flutter/Dart client targeting iOS 13+ and Android API 24+.
- Apple App Store and Google Play subscription purchase and server-side entitlement validation.
- Operational controls for retries, quotas, schedules, and failed notifications.

### Deferred

- Push notifications through APNs or FCM.
- Multiple resume profiles in the mobile user experience.
- Application tracking and generated application materials in the mobile client.
- Interactive, user-initiated provider searches beyond an internal support/debug action.
- Offline editing beyond safe request retry and cached read-only results.
- Social login.
- Shared workspaces or team accounts.
- A general-purpose workflow engine or microservice decomposition.

Free is the no-purchase tier. Starter and Plus entitlement assignment will be driven by server-validated Apple App Store and Google Play subscriptions. Store integration must not trust tier claims supplied directly by a mobile client.

## 3. Architectural Decisions

### AD-01: Share the current backend

The mobile app will use the existing FastAPI `/api/v1` API and the current domain models. A separate mobile backend or duplicate database is not planned.

### AD-02: Preserve web authentication and add mobile sessions

The web client may continue using secure cookies and CSRF protection. Mobile clients will use short-lived access tokens with rotating, revocable refresh tokens stored in the device's secure credential store. The common identity dependency must resolve either session type into the same `AuthenticatedIdentity`.

Before implementation, compare the account and device-session behavior in `mobile_interprete`. Reuse its proven policy and concepts where compatible, but do not copy project-specific schema or secrets blindly.

### AD-03: Start with a database-backed scheduler and worker

The first version will use the existing relational database as the durable source of work. A small dispatcher claims due schedules and creates idempotent operations; a separately supervised worker claims and executes them. This avoids introducing Redis or Celery before workload evidence requires them.

FastAPI `BackgroundTasks` must not execute scheduled searches or matches.

### AD-04: Meter successful provider searches, not returned jobs or matches

One billable search unit represents one usable job-search provider response. A failed provider request is logged and does not consume quota. Retries retain the same reservation and cannot consume multiple units. A usable provider response is chargeable even if later internal persistence ultimately fails, because the provider work was successfully delivered.

### AD-05: Notify only on stable, deduplicated matches

A match notification is unique for a user, search criterion, and canonical job. Rediscovery or an automatic resume revision must not create another notification for the same past job. Confirmed resume revisions are used for future automated searches. A user may explicitly rerun selected past jobs against the revised resume to evaluate its effectiveness; that manual action creates a new analysis without behaving like a newly discovered automatic notification.

### AD-06: Daily email digest and in-app notifications first

The MVP sends a daily email digest and records qualifying matches in the in-app inbox. Email uses the existing delivery infrastructure and provides a channel without mobile push credentials. Push-device registration and APNs/FCM delivery are a later release.

## 4. Target Workflow

```text
User creates account and verifies email
        |
        v
User uploads resume -> parse -> user confirms profile
        |
        v
User creates criteria and enables automatic search
        |
        v
Dispatcher claims due schedule and reserves a search unit
        |
        v
Worker executes provider search
        |
        +--> failure: retry or release/consume quota by policy
        |
        v
Normalize and deduplicate jobs
        |
        v
Match new jobs against the confirmed resume snapshot
        |
        v
Persist matches and select scores at/above threshold
        |
        v
Create idempotent notification deliveries
        |
        +--> email delivery
        +--> in-app match inbox
```

## 5. Proposed Data Changes

Names are provisional until migration design review.

### `user_subscriptions`

Tracks the user's current entitlement assignment independently of future billing-provider details.

- `id`
- `user_id`
- `tier_code`: `free`, `starter`, or `plus`
- `status`: `active`, `past_due`, `cancelled`, or `expired`
- `period_started_at`
- `period_ends_at`
- `external_customer_reference`, nullable
- `external_subscription_reference`, nullable
- `created_at`, `updated_at`, `cancelled_at`

Initial implementation can create an active Free subscription during account registration.

### `usage_ledger`

Provides an auditable, idempotent record instead of relying only on a mutable counter.

- `id`
- `workspace_id`, `user_id`
- `subscription_id`
- `usage_type`: initially `provider_search`
- `units`
- `state`: `reserved`, `consumed`, or `released`
- `idempotency_key`
- `search_run_id`, nullable until the run is created
- `reason`
- `reserved_at`, `consumed_at`, `released_at`
- `created_at`, `updated_at`

Required constraints:

- Unique `(user_id, usage_type, idempotency_key)`.
- Positive units.
- Valid state transition enforcement in application services and tests.

### `search_schedules`

Associates recurring execution settings with an existing `job_search_criteria` record.

- `id`
- `workspace_id`, `user_id`
- `criterion_id`
- `resume_profile_id`
- `enabled`
- `interval_minutes`
- `minimum_match_score`
- `next_run_at`
- `last_claimed_at`, `last_completed_at`
- `consecutive_failure_count`
- `paused_reason`, nullable
- `created_at`, `updated_at`, `deleted_at`

Required constraints:

- At most one active schedule per criterion.
- Score bounded to the current match-score range.
- Schedule ownership consistent with criterion and resume ownership.
- `interval_minutes` cannot be smaller than the tier entitlement.

### `search_runs`

Captures one scheduled execution and its cost/result summary.

- `id`
- `schedule_id`
- `managed_operation_id`
- `status`: `queued`, `running`, `succeeded`, `failed`, or `cancelled`
- `scheduled_for`
- `provider`
- `jobs_discovered`, `jobs_new`, `jobs_matched`, `matches_notified`
- `error_code`, `error_message`
- `started_at`, `completed_at`, `created_at`, `updated_at`

The existing `managed_operations` table remains the detailed execution record. `search_runs` is the product and metering record. The corresponding `usage_ledger` row references `search_run_id`, avoiding a circular foreign-key dependency.

### `notification_preferences`

- `user_id`
- `email_enabled`
- `digest_mode`: initially `immediate` or `daily`
- `minimum_match_score`, used as the default for new schedules
- `timezone`
- `quiet_hours_start`, `quiet_hours_end`, nullable
- `created_at`, `updated_at`

### `notification_deliveries`

- `id`
- `workspace_id`, `user_id`
- `job_resume_match_id`
- `search_schedule_id`
- `channel`: initially `email` or `in_app`
- `status`: `pending`, `sent`, `failed`, `suppressed`, or `read`
- `idempotency_key`
- `attempt_count`, `next_attempt_at`
- `provider_reference`, nullable
- `error_code`, `error_message`, nullable
- `created_at`, `sent_at`, `read_at`, `updated_at`

Required constraint: unique `(user_id, channel, idempotency_key)`.

### Mobile sessions

Either extend the current `auth_sessions` model with an explicit session type and refresh-token family, or create `mobile_sessions`. Store only token hashes, rotation state, expiry, device label, last-used time, revocation time, and security metadata. Never store a reusable plaintext refresh token.

## 6. Entitlement Model

Exact commercial values remain open. The implementation must not hard-code them in route handlers.

| Entitlement | Free | Starter | Plus |
|---|---:|---:|---:|
| Successful provider searches per week | 1 | 3 | 5 |
| Maximum active criteria | TBD | TBD | TBD |
| Minimum schedule interval | TBD | TBD | TBD |
| Resume profiles available to automation | 1 initially | 1 initially | 1 initially |
| Email notifications | Yes | Yes | Yes |
| Push notifications | Deferred | Deferred | Deferred |

Tier definitions should be loaded through a validated, versioned configuration module initially. Each search run must retain the effective tier and entitlement snapshot used for its decision so later tier changes do not rewrite history.

Rules:

- New accounts receive Free automatically.
- Disabling or downgrading a subscription never deletes user data.
- When active criteria exceed a downgraded limit, keep them but pause excess schedules deterministically.
- A schedule without available quota is paused until the next period; it must not repeatedly create failed operations.
- Tier checks happen both when configuration is changed and immediately before work is claimed.
- Support adjustments are ledger entries, not direct counter edits.

## 7. Provisional API Surface

Existing resume, criteria, operation, job, and match endpoints should be reused where their contracts are client-neutral.

### Mobile authentication

- `POST /api/v1/auth/mobile/sessions`
- `POST /api/v1/auth/mobile/sessions/refresh`
- `GET /api/v1/auth/mobile/sessions`
- `DELETE /api/v1/auth/mobile/sessions/{session_id}`
- `DELETE /api/v1/auth/mobile/sessions/current`

Registration, verification, password recovery, and account deletion should share existing account services rather than duplicate business logic.

### Subscription and usage

- `GET /api/v1/account/entitlements`
- `GET /api/v1/account/usage`

Tier assignment remains restricted and is not exposed as a normal user-write endpoint until billing is designed.

### Automation

- `GET /api/v1/automation/schedules`
- `POST /api/v1/automation/schedules`
- `PATCH /api/v1/automation/schedules/{schedule_id}`
- `DELETE /api/v1/automation/schedules/{schedule_id}`
- `POST /api/v1/automation/schedules/{schedule_id}/pause`
- `POST /api/v1/automation/schedules/{schedule_id}/resume`
- `GET /api/v1/automation/runs`
- `GET /api/v1/automation/runs/{run_id}`
- `POST /api/v1/resume-job-matches/saved-jobs`, for selected past-job reruns

### Match inbox and notifications

- `GET /api/v1/match-inbox`
- `GET /api/v1/match-inbox/{match_id}`
- `POST /api/v1/match-inbox/{match_id}/read`
- `GET /api/v1/notification-preferences`
- `PUT /api/v1/notification-preferences`

All list endpoints require cursor-based or stable pagination before public mobile release. OpenAPI is the contract source for generated mobile models and client code.

## 8. Delivery Plan

### Phase 0: Resolve Preconditions and Product Decisions

**Goal:** remove known production hazards and settle the minimum rules needed for implementation.

- [ ] **SAFE-01:** Correct the production web API base URL and add a forbidden-loopback artifact check.
- [ ] **SAFE-02:** Redact database credentials in DaliCommonLib, rotate the affected credential, and remediate retained logs.
- [ ] **AUTH-00:** Compare DaliJob authentication with `mobile_interprete` user/device management and record the compatible session policy.
- [x] **PROD-01:** Select initial Free, Starter, and Plus search allowances. Approved August 14, 2026 as 1, 3, and 5 successful provider searches per week.
- [x] **PROD-02:** Select the default match threshold and whether users may change it. Approved August 14, 2026: process the first usable provider result, default the score floor to zero, and retain the user-adjustable floor for calibration.
- [x] **PROD-03:** Decide whether a resume update can trigger a second notification for the same job. Approved August 14, 2026: no automatic re-notification; future searches use the revision and users may manually rerun selected past jobs.
- [x] **PROD-04:** Define search-unit consumption for provider timeouts and uncertain provider responses. Approved August 14, 2026: failed provider requests are logged and not charged; only a usable provider response makes the reservation chargeable.
- [ ] **OPS-00:** Define beta tier-assignment and support procedures. Paid tiers will come from validated Apple/Google subscriptions; receipt validation, store events, grace periods, refunds, account linking, and support overrides remain to be designed.

**Exit criteria**

- Critical architecture-review findings are remediated or explicitly accepted by the owner.
- Authentication and quota policies have written decisions.
- The initial entitlement matrix is approved.

### Phase 1: Mobile Account and Setup Foundation

**Goal:** a mobile client can securely create an account and establish a valid automation profile.

- [ ] **AUTH-01:** Refactor account registration, verification, recovery, and deletion into client-neutral services.
- [ ] **AUTH-02:** Add mobile access/refresh sessions with rotation, reuse detection, revocation, and secure audit events.
- [ ] **AUTH-03:** Make the common identity dependency accept web or mobile sessions without weakening CSRF protection for cookie-authenticated requests.
- [ ] **AUTH-04:** Add per-account and per-IP limits for mobile login and refresh.
- [ ] **API-01:** Confirm resume-upload and criteria endpoints contain no browser-only assumptions.
- [ ] **API-02:** Add an onboarding-status endpoint that reports account verification, confirmed resume, criteria, tier, and automation readiness.
- [ ] **SDK-01:** Generate a typed mobile API client from OpenAPI and add contract drift checks.

**Tests**

- Refresh-token rotation and replay detection.
- Revocation of the current device and all devices.
- Cross-user access rejection.
- Resume upload, parsing failure, retry, and confirmation.
- Criteria ownership and validation.

**Exit criteria**

- A test mobile client can register, verify, sign in, upload a resume, create criteria, and revoke its device session.

### Phase 2: Entitlements and Auditable Usage

**Goal:** every user has a tier and provider-search usage is enforced consistently.

- [x] **TIER-01:** Add the subscription and usage-ledger migration. Implemented August 14, 2026.
- [x] **TIER-02:** Create a Free subscription during registration and backfill existing users. Implemented August 14, 2026.
- [x] **TIER-03:** Implement a single entitlement service used by routes, scheduler, and support tooling. Implemented for routes and the dispatcher August 14, 2026; support UI remains deferred.
- [x] **TIER-04:** Implement atomic reserve, consume, and release operations with idempotency. Implemented August 14, 2026.
- [ ] **TIER-05:** Add the entitlement and usage read APIs.
- [ ] **TIER-06:** Add a restricted CLI for tier assignment and auditable usage adjustments during beta.
- [x] **TIER-07:** Add period rollover behavior without resetting or rewriting the ledger. Implemented August 14, 2026.

**Tests**

- Concurrent reservations cannot exceed the allowance.
- Replayed requests do not consume multiple units.
- Period rollover uses the correct timezone-independent boundary.
- Downgrade and cancellation preserve data and pause excess work.
- Support adjustments remain auditable.

**Exit criteria**

- Search capacity can be reserved atomically under concurrency and reconciled from ledger records.

### Phase 3: Durable Scheduler and Automated Search

**Goal:** due searches execute without an active mobile session and survive API restarts.

- [ ] **AUTO-01:** Add search-schedule and search-run migrations with tenant-consistency constraints.
- [x] **AUTO-02:** Implement schedule CRUD and tier validation. Implemented August 14, 2026.
- [x] **AUTO-03:** Implement a dispatcher command that claims due schedules using database locking and creates idempotent runs. Implemented August 14, 2026.
- [x] **AUTO-04:** Implement a separately supervised worker that claims queued runs. Implemented August 14, 2026; environment service installation remains an operations task.
- [x] **AUTO-05:** Refactor search execution so provider wait time does not retain a database session. Implemented August 14, 2026.
- [x] **AUTO-06:** Normalize provider results and deduplicate them against shared job source data. Implemented August 14, 2026.
- [x] **AUTO-07:** Update `next_run_at` using explicit UTC calculations and a bounded catch-up policy. Implemented August 14, 2026.
- [x] **AUTO-08:** Add leases, heartbeats, retry limits, stale-run recovery, and graceful shutdown. Implemented August 14, 2026.
- [ ] **AUTO-09:** Add operational commands to pause all automation and retry or cancel a selected run.

**Tests**

- A queued run survives API and worker restarts.
- Two dispatchers cannot create duplicate runs for the same scheduled occurrence.
- Two workers cannot execute the same lease concurrently.
- Quota exhaustion pauses without provider calls.
- Provider failure follows the approved consume/release policy.
- Deleting an account or criterion prevents future execution.

**Exit criteria**

- A due schedule produces one durable run and one metered provider execution despite process restarts and duplicate dispatcher invocations.

### Phase 4: Automatic Matching and Notification Pipeline

**Goal:** new qualifying jobs produce exactly one useful notification.

- [ ] **MATCH-01:** Match only newly associated or materially changed jobs against the schedule's pinned resume snapshot.
- [x] **MATCH-02:** Persist match inputs, score, rationale, provider metadata, and prompt/schema versions. Implemented August 14, 2026.
- [x] **MATCH-03:** Apply the effective schedule/user threshold after matching. Implemented August 14, 2026 using the pinned schedule threshold; preference defaults for new schedules remain a follow-up.
- [x] **NOTIFY-01:** Add notification preference and delivery migrations. Implemented August 14, 2026.
- [x] **NOTIFY-02:** Create in-app delivery records idempotently for qualifying matches. Implemented August 14, 2026 using a conservative one-delivery-per-schedule-and-canonical-job key.
- [x] **NOTIFY-03:** Add email templates with job, score, concise rationale, and a deep link. Implemented August 14, 2026.
- [x] **NOTIFY-04:** Implement email retries, terminal failure state, suppression, and delivery observability. Implemented August 14, 2026 with delivery leases, safe errors, structured logs, and bounded retry; dashboard metrics remain an operations task.
- [x] **NOTIFY-05:** Implement timezone-aware daily digest assembly and delivery; immediate email is not part of the initial MVP. Implemented August 14, 2026.
- [x] **INBOX-01:** Add paginated match-inbox and mark-read APIs. Implemented August 14, 2026 with descending delivery-ID cursor pagination.

**Tests**

- Scores below threshold create no notification.
- Rediscovered jobs do not notify twice.
- Retried workers do not duplicate notifications or emails.
- Digest assembly respects timezone and quiet-hour policy.
- Email content contains no sensitive resume text or provider secrets.
- Account deletion suppresses pending deliveries.

**Exit criteria**

- A scheduled search can discover a job, produce a persisted match, and deliver one email/in-app notification above threshold.

### Phase 5: Mobile MVP

**Goal:** deliver the complete user journey through a small native client.

- [x] **MOB-01:** Select the mobile stack and establish development, staging, and production API environments. The Flutter/Dart Android and iOS project now supports compile-time environment/API configuration and requires HTTPS in release builds.
- [ ] **MOB-02:** Implement registration, verification, login, recovery, logout, and device management. The Flutter client now implements registration, login, recovery requests, session restoration, and current-device logout; verification-link handling and the device list/revocation UI remain.
- [x] **MOB-03:** Store refresh credentials only in the platform secure store; keep access tokens in memory where practical. Rotating refresh tokens use Android Keystore/iOS Keychain through `flutter_secure_storage`; access tokens remain in memory.
- [ ] **MOB-04:** Implement resume upload, parse status, failure recovery, and confirmation. PDF/TXT upload with parsed-profile application and manual profile fallback are implemented; parse preview/edit confirmation and explicit retry remain.
- [x] **MOB-05:** Implement criteria and automation settings. The mobile onboarding flow creates resume-linked criteria and enables or pauses a tier-compliant schedule.
- [x] **MOB-06:** Display tier allowance, current-period usage, and the next scheduled run. The Automation screen displays weekly allowance, availability, plan, schedule status, and next run.
- [ ] **MOB-07:** Implement match inbox, match details, external job link handling, and read state. Inbox, match detail rationale, and read state are implemented; opening external job links remains.
- [ ] **MOB-08:** Implement notification preferences.
- [ ] **MOB-09:** Add deep links from email into the authenticated match detail screen.
- [ ] **MOB-10:** Add accessible loading, empty, offline, expired-session, quota-exhausted, and provider-failure states.

**Exit criteria**

- A new user can complete onboarding and later receive and open an automatically generated match without using the web client.

### Phase 6: Beta Hardening and Launch

**Goal:** operate the workflow safely with real users and measurable cost.

- [ ] **SEC-01:** Complete mobile API threat modeling, token-leak review, tenant-negative tests, and log-secret scanning.
- [ ] **LOAD-01:** Run authenticated concurrency tests for scheduler, worker, session refresh, and inbox access.
- [ ] **COST-01:** Build dashboards for provider searches, matches, notifications, cost per active user, and quota denials by tier.
- [ ] **OPS-01:** Document scheduler/worker deployment, health checks, alerting, retry, support, and rollback procedures.
- [ ] **DATA-01:** Complete stored-file purge and orphan reconciliation before broad resume uploads.
- [ ] **REL-01:** Pin dependencies and produce a reproducible artifact containing worker and operational tooling.
- [ ] **BETA-01:** Roll out to internal users, then a bounded Free cohort, then paid-tier cohorts.
- [ ] **BETA-02:** Define launch gates for reliability, notification relevance, provider cost, and retention.

**Suggested launch gates**

- No known cross-tenant access path.
- No plaintext session or provider credential in database records or logs.
- At least 99% of due schedules are claimed within the target dispatch window.
- Duplicate notification rate is effectively zero under retry testing.
- Search usage reconciles with provider calls and subscription limits.
- Worker restart recovery is verified in staging.
- Account deletion has a verified file-purge outcome.

## 9. Implementation Order for the First Vertical Slice

The smallest useful internal demonstration should be built in this order:

1. Create Free subscription and configurable entitlement definitions.
2. Add one schedule for one existing criterion and resume profile.
3. Add atomic usage reservation.
4. Run the dispatcher and worker manually from CLI.
5. Execute one provider search and deduplicate results.
6. Match only the newly found jobs.
7. Save qualifying matches to an in-app inbox.
8. Send one idempotent email.
9. Expose status through existing web tooling or a minimal test client.
10. Add mobile sessions and the native UI after the backend slice is proven.

This sequence validates the highest-risk automation, cost, and relevance assumptions before investing heavily in mobile screens.

## 10. Observability Requirements

Every scheduled run should be traceable by `search_run_id`, `managed_operation_id`, `schedule_id`, and a non-sensitive user reference. Structured events should cover:

- Schedule claimed or skipped.
- Entitlement decision and ledger transition.
- Provider request outcome and usage units.
- Jobs discovered, normalized, duplicated, and newly saved.
- Match counts by threshold outcome without logging resume contents.
- Notification created, sent, suppressed, retried, or terminally failed.
- Lease recovery and duplicate-delivery prevention.

Metrics should include queue depth, oldest queued age, due-schedule delay, run duration, provider error rate, quota denial rate, jobs per search, qualifying matches per search, notification delivery latency, and estimated provider cost by tier.

## 11. Security and Privacy Requirements

- Do not log resume contents, access tokens, refresh tokens, database URIs, or provider secrets.
- Hash mobile refresh tokens and rotate them on every use.
- Revoke an entire token family on refresh-token reuse.
- Enforce user and workspace ownership at repository and database boundaries.
- Validate uploaded files by type, size, and content; store them outside public static paths.
- Keep notification emails concise and avoid including sensitive resume details.
- Apply SSRF protections to every URL fetched by scheduled work.
- Preserve exact resume and job snapshots used for each match.
- Ensure account deletion cancels schedules, revokes sessions, suppresses pending notifications, and enters documents into the purge workflow.

## 12. Open Product Decisions

These decisions block final estimates but do not block the first database/worker prototype:

1. Maximum active criteria per tier.
2. Minimum search frequency per tier.
3. Definition of a canonical duplicate job across providers.
4. Retention period for non-qualifying discovered jobs and failed run payloads.
5. Apple App Store and Google Play server-notification, receipt-validation, grace-period, refund, and cross-store account-linking policy.

## 13. Definition of MVP Complete

The MVP is complete when a verified mobile user on any configured tier can upload one resume, enable an allowed search schedule, consume auditable quota, receive new matches above the approved threshold, and review them in the app; the entire flow must survive API/worker restarts, avoid duplicate charges and notifications, respect tenant boundaries, and provide enough operational evidence to reconcile provider usage and diagnose failures safely.

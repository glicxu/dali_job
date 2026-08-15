# Guest Try-Out Experience Design

**Status:** Approved; implementation in progress
**Date:** August 14, 2026
**Related plan:** [MOBILE_AUTOMATED_MATCHING_IMPLEMENTATION_PLAN.md](MOBILE_AUTOMATED_MATCHING_IMPLEMENTATION_PLAN.md)

**Implementation progress:** Phase A's shared readiness evaluator, Phase B's guest persistence/upload/parsing/retention foundation, and Phase C's durable top-one matching backend are implemented. The Flutter client now includes signed-out entry, separate Keychain/Keystore guest credentials, trial restoration/deletion, resume upload or one free-form profile description, profile-readiness guidance, criteria, retry-aware matching, and the single result screen. Background execution, claim/conversion, and production UX/device testing remain future work.

## 1. Decision Summary

DaliJob should let a person experience one genuine resume-to-job match before creating an account. The trial must demonstrate candidate-to-job matching, not merely keyword-based job search.

An account is offered only after the result is available. The value proposition is that registration preserves the guest's profile, search criteria, result, and future automation so the user does not have to repeat completed work.

The trial has these boundaries:

- No account is required to begin or receive the first result.
- A profile-readiness gate prevents weak search-only experiences from being described as matching.
- A guest receives one successful provider-backed search and its single best usable match.
- Provider failures and unusable responses do not consume the trial.
- Recurring schedules, notifications, and subscription purchases require a verified account.
- Guest data expires and is deleted if it is not claimed.
- Registration or sign-in claims the guest work atomically.

## 2. Product Objective

The try-out should answer the prospective user's most important question:

> Can DaliJob understand my background well enough to find and explain a job that fits me?

The flow should establish this value before requesting credentials. Account creation is presented as a way to save valuable work and continue receiving matches, not as an administrative prerequisite.

### Success measures

- Percentage of guest trials that reach profile readiness.
- Percentage of ready profiles that start a match.
- Percentage of started matches that return a usable result.
- Time from opening the trial to viewing the result.
- Percentage of result viewers who save their work by registering or signing in.
- Percentage of claimed trials that enable recurring matching.
- Provider cost and abuse rate per claimed user.

## 3. Goals

- Demonstrate real candidate-to-job matching without an account.
- Require enough candidate evidence to produce a defensible rationale.
- Minimize repeated entry and preserve progress through registration and verification.
- Give users clear, actionable feedback when their profile is not ready.
- Bound provider cost and anonymous abuse.
- Protect resumes and other sensitive career information during the guest lifecycle.
- Reuse the existing profile, criteria, matching, entitlement, and notification domains after claim.

## 4. Non-Goals

- Anonymous recurring searches or notifications.
- Unlimited guest searches.
- Treating a LinkedIn URL as permission to scrape a profile.
- Requiring contact details, legal name, or demographic data for readiness.
- Building a complete resume editor inside the first trial.
- Purchasing Starter or Plus before account verification.
- Preserving an abandoned guest trial indefinitely.

## 5. Experience Principles

### Show value before asking for commitment

The user should see the best match and a concise explanation before encountering registration.
The trial executes the provider search and comparison immediately in the same flow. Weekly scheduling applies only after account conversion; a guest never waits for the next weekly run.

### Do not call search “matching”

Target role and location are search criteria. They are not sufficient candidate evidence. The readiness gate must prevent a trial from continuing until DaliJob has meaningful work, project, education, or skills evidence.

### Ask only for information that improves the result

The trial should not request email, password, notification preferences, subscription tier, or scheduling frequency before producing the first match.

### Preserve progress across conversion

Registration, email verification, or existing-account login must not discard or require re-entry of guest data.

### Explain uncertainty

The result should state which profile evidence influenced the score and identify important missing information. A thin but valid student profile should not be presented with the same confidence as a complete experienced-worker profile.

## 6. User Journey

```text
Try DaliJob
    |
    v
Create private guest session
    |
    v
Import or build candidate profile
    |
    v
Profile-readiness gate ---- not ready ----> Add the specific missing evidence
    |
    v
Enter target role and location
    |
    v
Run one provider search and evaluate candidates
    |
    v
Show the single best usable match and rationale
    |
    +----> Leave ----> Guest data expires and is deleted
    |
    v
“Save my profile and keep matching”
    |
    +----> Register and verify
    |          or
    +----> Sign in to an existing account
               |
               v
Atomically claim profile, criteria, and match
               |
               v
Offer recurring matching and notifications
```

### Entry screen

Primary action:

> Try a match without an account

Secondary action:

> Sign in

Before beginning, concise privacy text should state that the guest profile is private, used to produce the requested match, and automatically deleted if it is not saved.

### Profile acquisition

Offer these paths in priority order:

1. **Upload a resume:** PDF or supported text from device storage, iCloud, Google Drive, or another document provider.
2. **Don't have a resume?:** reveal one large free-form text input. Ask the user to describe their work, projects, education, accomplishments, and skills, and explain that more detail produces a better match.

Do not offer LinkedIn as a trial import choice. DaliJob cannot directly import a public LinkedIn URL, and asking users to export a PDF adds friction without improving this first-run experience.

### Guided profile intake

The trial must not present a multi-field form or a sequence of profile questions. It uses one text area, with a short example in the placeholder. The backend parses that text into the shared structured profile and applies the same readiness gate used for uploaded resumes.

Voice dictation remains available through the operating-system keyboard. AI structures the supplied text behind the scenes; the user sees readiness guidance rather than another editing form.

The same parsing call should recommend three to five realistic target-role titles grounded in the supplied evidence. Once the profile is ready, present those titles as quick choices while retaining one free-form “different role” input. Role recommendations do not search for jobs and do not consume provider-search quota.

## 7. Profile-Readiness Gate

### Purpose

Readiness measures whether the available candidate evidence supports a meaningful comparison with a job. It is not a resume-quality grade and must not reward personally identifying information.

### Supported readiness pathways

The gate must accommodate different career stages.

#### Experienced-worker pathway

- At least one role with meaningful responsibilities or outcomes.
- At least three usable skills, or skills that can be confidently derived from confirmed experience.
- At least one accomplishment, responsibility, or work sample with enough detail to compare against job requirements.

#### Early-career or career-transition pathway

- At least one substantial project, education program, certification, volunteer role, internship, or transferable-work experience.
- At least three usable skills.
- At least one concrete activity, outcome, or demonstrated capability.

Target role and location are required before search, but they do not count as candidate readiness.

### Readiness dimensions

| Dimension | Meaning | Example evidence |
| --- | --- | --- |
| Experience context | Where and in what capacity skills were used | Role, internship, project, education, volunteer work |
| Responsibilities | What the person actually did | Built, managed, analyzed, supported, designed |
| Outcomes | Evidence of impact or completion | Improved a metric, shipped a system, earned a credential |
| Skills | Capabilities that can be compared with requirements | Python, budgeting, customer support, project planning |
| Recency and detail | Enough context to avoid unsupported inference | Dates, scope, tools, team, domain |

### Gate behavior

The server returns:

- `ready`: whether matching may begin.
- `readiness_version`: versioned policy identifier.
- `pathway`: experienced, early-career, or undetermined.
- `evidence_summary`: safe counts and categories, not raw resume text.
- `missing_requirements`: actionable items.
- `warnings`: quality limitations that do not block matching.

Example:

```json
{
  "ready": false,
  "readiness_version": "profile-readiness-v1",
  "pathway": "experienced",
  "evidence_summary": {
    "experience_items": 1,
    "responsibility_items": 0,
    "outcome_items": 0,
    "skill_items": 2
  },
  "missing_requirements": [
    {
      "code": "experience_detail_required",
      "message": "Add what you did in your most recent role."
    },
    {
      "code": "skills_required",
      "message": "Add at least one more relevant skill."
    }
  ],
  "warnings": []
}
```

The UI should never show only a numeric readiness percentage. It should show what is sufficient, what is missing, and why the missing evidence matters.

### Deterministic and AI-assisted checks

The gate should be deterministic after profile normalization. AI may extract responsibilities, outcomes, and skills from uploaded content, but the final readiness decision must operate on validated structured fields and a versioned rule set.

This separation makes the policy testable, explainable, and stable across model changes.

## 8. Guest Match Contract

### Trial allowance

- One consumed guest provider search per abuse-control period.
- The result contains only the single highest-ranked usable match.
- A successful provider search consumes the trial only when it returns a usable search response.
- Provider timeout, provider failure, malformed response, or zero usable candidates does not consume the trial.
- Once a usable search response is obtained, its normalized candidates should be retained for bounded matching retries so a matcher failure does not repeat the search-provider charge.

### Match quality

The same production parser and matcher used for authenticated automation should be used for the trial. The result must persist immutable profile and job snapshots, prompt/schema versions, provider metadata, and safe failure information.

The result screen should include:

- Job title, company, and location.
- Match score using the existing 0–10 scale.
- Why the candidate appears to fit.
- Important gaps or uncertainties.
- Link to the original job.
- Clear indication that this was the best usable result from the trial search.

## 9. Conversion Experience

### Value-oriented prompt

Recommended primary call to action:

> Save my profile and keep matching

Supporting text:

> Keep this profile, search criteria, and match. DaliJob can continue searching automatically, so you will not have to enter them again.

Avoid leading with “Create account,” “Register,” or a list of password requirements.

### New account

1. User supplies email and password after viewing the result.
2. DaliJob creates an unverified account and sends verification.
3. The guest trial is placed in `claim_pending` and its expiry is extended.
4. Verification deep-links back into the mobile app or web client.
5. The verified session claims the guest trial in one transaction.
6. The claimed account receives the normal Free entitlement.
7. DaliJob offers, but does not silently enable, recurring matching and daily email.

### Existing account

If the email already exists, the user signs in. After authentication, DaliJob claims the guest work into that account.

The claim process must handle existing profiles and criteria without overwriting them. The guest objects should be added as new records with clear titles, then the user may choose defaults.

### Claim guarantees

- A guest trial can be claimed only once.
- Claim secrets are random, stored only as hashes, and bound to the guest session.
- Claiming requires a verified authenticated account.
- Retrying a completed claim is idempotent and returns the existing result mapping.
- Cross-account claims are rejected.
- The transaction either creates all owned records and marks the trial claimed, or creates none.

## 10. Guest Session And Security Model

### Guest credential

`POST /api/v1/guest-trials` creates:

- A random public trial ID.
- A high-entropy guest secret returned once to the client.
- A server-side hash of the secret.
- Issued, last-used, and expiry timestamps.
- Status: `active`, `matching`, `result_ready`, `claim_pending`, `claimed`, or `expired`.

The mobile app stores the guest secret in the platform secure store. The web client uses a secure, HttpOnly, SameSite cookie. Guest credentials must never be accepted as normal account bearer tokens.

### Authorization

Every guest resource is scoped to one guest trial. Object IDs alone never grant access. Repository methods require the verified guest identity, just as account-owned repositories require authenticated workspace identity.

### Abuse controls

- Rate-limit guest creation by IP and privacy-preserving device signal.
- Permit only one consumed guest search per device/IP abuse window by default.
- Apply stricter concurrency limits than authenticated traffic.
- Require a challenge only when risk signals warrant it; do not add CAPTCHA to every trial initially.
- Reject automated bulk profile creation and repeated claim cycling.
- Never trust a client-provided “trial unused” flag.
- Record safe reason codes without retaining raw IP addresses longer than operationally necessary.

## 11. Data Model

Guest data should remain separate from account-owned records until claim. Making `user_id` nullable throughout the existing schema would weaken ownership guarantees.

### `guest_trials`

- `id`: internal integer key.
- `public_id`: random opaque identifier, unique.
- `secret_hash`: hash of the guest secret.
- `status`.
- `readiness_version`.
- `provider_search_state`: available, reserved, consumed, or released.
- `created_at`, `last_used_at`, `expires_at`.
- `claim_pending_until`.
- `claimed_user_id`, nullable.
- `claimed_at`, nullable.
- `deleted_at`, nullable.

### `guest_resume_profiles`

- `guest_trial_id`, unique for MVP.
- Structured `resume_data` JSON.
- Optional transient document reference.
- Parser/model/schema provenance.
- Readiness pathway and evidence summary.
- Created and updated timestamps.

### `guest_search_criteria`

- `guest_trial_id`, unique for MVP.
- Keyword or target role.
- Location.
- Created and updated timestamps.

### `guest_match_results`

- `guest_trial_id`, unique for MVP.
- Optional shared `jobs_cache_id`.
- Profile and job snapshots.
- Match score and structured rationale.
- Provider, model, prompt, and schema provenance.
- Source URL.
- Created timestamp.

### `guest_provider_attempts`

- Guest trial and idempotency key.
- Provider feature.
- State: reserved, consumed, or released.
- Safe outcome and failure category.
- Timestamps.

Transient uploaded files should use a separate guest storage prefix and must not be copied into permanent user storage until claim.

## 12. API Outline

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/guest-trials` | Create a private guest session |
| `GET` | `/api/v1/guest-trials/current` | Restore status and progress |
| `POST` | `/api/v1/guest-trials/current/resume-import` | Upload and parse a guest resume |
| `PUT` | `/api/v1/guest-trials/current/profile` | Confirm or update structured profile |
| `GET` | `/api/v1/guest-trials/current/readiness` | Evaluate the readiness gate |
| `PUT` | `/api/v1/guest-trials/current/criteria` | Save target role and location |
| `POST` | `/api/v1/guest-trials/current/match` | Start the one-result trial operation |
| `GET` | `/api/v1/guest-trials/current/match` | Poll status or retrieve the result |
| `POST` | `/api/v1/guest-trials/current/claim-intent` | Extend expiry during registration |
| `POST` | `/api/v1/guest-trials/claim` | Claim data into the authenticated account |
| `DELETE` | `/api/v1/guest-trials/current` | Delete the guest trial immediately |

Guest mutation endpoints require the guest secret plus idempotency keys where retries could create work or consume provider capacity.

## 13. Claim Mapping

Claiming creates or reuses normal authenticated records:

| Guest record | Account-owned result |
| --- | --- |
| Guest structured profile | `resume_profiles` default only if the account has no default |
| Guest uploaded document | `documents` and its immutable version |
| Guest criteria | `job_search_criteria` |
| Shared normalized job | Existing or new `jobs_cache` plus `user_saved_jobs` |
| Guest result | `job_resume_matches` with original snapshots and provenance |
| Guest provider attempt | Audit/claim linkage; it must not consume the account's weekly allowance again |

The first recurring schedule is offered after claim. It is not created silently because enabling background provider work and notifications requires explicit user intent.

## 14. Privacy And Retention

- Default active guest lifetime: 24 hours after last use.
- Registration-started lifetime: extend up to 72 hours to allow email verification.
- Failed or abandoned uploads: delete from object storage when the trial expires.
- Claimed transient files: copy or promote to the user's protected document namespace, then remove the guest copy.
- Expired database content: purge raw resume/profile and match snapshots; retain only minimal aggregate abuse and cost metrics without resume text.
- Provide a visible “Delete my trial” action.
- Do not use guest resumes or match content for model training.
- Do not include resume content in logs, analytics, alerts, or notification payloads.
- Make retention text visible before upload, not only in a privacy policy.

Final retention periods require privacy review before public launch.

## 15. Failure And Recovery

| Failure | User experience | Charging behavior |
| --- | --- | --- |
| Resume parsing fails | Preserve upload; allow retry or guided manual confirmation | No guest search consumed |
| Profile not ready | Show specific missing evidence | No guest search consumed |
| Search provider fails or times out | Safe retry message | Release reservation |
| Search returns no usable jobs | Let user adjust criteria and retry | Release reservation |
| Match provider fails after usable search | Retry against retained candidates | Do not repeat search charge |
| App closes during operation | Restore from guest session and poll durable state | No duplicate work |
| Registration email is delayed | Preserve claim-pending trial for extended TTL | No duplicate work |
| Claim partially conflicts with account data | Add non-destructively or ask for default selection | Trial remains claimable |

## 16. Observability

Track structured events without raw profile content:

- Guest trial created and restored.
- Profile source selected.
- Parse succeeded or failed by safe category.
- Readiness passed or missing-requirement codes.
- Criteria saved.
- Provider reservation, release, or consumption.
- Match completed or failed by safe category.
- Result viewed.
- Claim started, verified, completed, or failed.
- Trial expired and purge completed.

Dashboards should separate product conversion, provider reliability, abuse, privacy-purge health, and cost.

## 17. Rollout Plan

### Phase A: Readiness foundation

- [x] Define structured evidence fields and versioned readiness policy.
- [x] Add deterministic readiness evaluator and tests for experienced, early-career, career-transition, and incomplete profiles.
- [x] Expose the shared evaluator through an authenticated, ownership-scoped resume-profile endpoint.
- Add UI feedback for missing evidence.

### Phase B: Guest persistence

- [x] Add separate guest trial, profile, and criteria tables with hashed guest credentials.
- [x] Implement manual structured profile and criteria persistence without provider calls.
- [x] Add sliding expiry, immediate deletion, purge service, credential-tampering, and ownership-isolation tests.
- [x] Add guest resume upload, isolated transient storage, redacted extraction, replacement cleanup, and file-aware purge.
- [x] Add AI-assisted suggestions, explicit confirmation boundary, failure-safe retry, and parser provenance.
- [x] Add process-local guest creation and parsing limits for the current single-instance deployment.
- [x] Add a bounded, idempotent purge command with dry-run, batch limits, file cleanup, unsafe-path protection, and failure exit status.
- Install and monitor the purge schedule in each deployed environment.
- Add shared production abuse controls before horizontal scaling.
- Integrate guest credential storage and profile-readiness feedback in the mobile client.

### Phase C: One-result trial

- [x] Add durable guest operation, provider reservation/release/consumption semantics, bounded candidate retention, and stale-reservation recovery.
- [x] Add matcher-only retry and immutable top-one result selection using the production provider interfaces.
- [x] Add provider failure, unusable response, single consumption, idempotency, retained retry, and top-one API tests.
- [x] Add the Flutter guest entry, secure credential restoration, readiness/criteria flow, retry state, and top-one result UI.
- Move provider execution from the request process to the durable worker before multi-instance deployment.
- Add result UI plus production cost, failure, concurrency, and abuse monitoring.

### Phase D: Claim and conversion

- Add claim intent, verification-safe expiry extension, atomic claim transaction, existing-account login path, and idempotent retry.
- Offer recurring schedule and notification settings after claim.

### Phase E: Controlled beta

- Enable the experience for a small traffic percentage.
- Review match quality, completion time, provider cost, abuse, purge reliability, and account conversion before expanding.

## 18. Acceptance Criteria

- A signed-out user can begin without entering an email address.
- Target role and location alone cannot pass readiness.
- Both experienced and early-career evidence pathways can pass readiness.
- Missing evidence is described with actionable text.
- A ready guest can receive exactly one best usable match and rationale.
- Failed or unusable provider responses do not consume the guest allowance.
- Closing and reopening the app restores the private guest trial.
- Registration and email verification preserve guest progress.
- A verified user can claim the trial exactly once without re-entering profile or criteria data.
- Claiming does not overwrite existing account profiles or consume weekly quota again.
- Expired trials and transient documents are purged on schedule.
- Logs, analytics, and errors contain no resume text or guest secret.
- Automated tests cover ownership isolation, token guessing, token reuse, rate limits, idempotency, provider failure, claim conflicts, expiry, and purge.

## 19. Open Product Decisions

1. Final active and claim-pending guest retention periods.
2. Guest abuse window and whether a device may receive another trial after expiry.
3. Risk threshold for CAPTCHA or another human-verification challenge.
4. Whether a match score below a quality floor should be shown with an explicit low-confidence state or treated as no usable match.
5. Which guided-profile fields are required for each readiness pathway after evaluation against real profiles.
6. Whether the user may revise criteria and retry when the first search produces no usable jobs.
7. Whether recurring matching should be offered enabled-by-default with explicit consent or disabled until the user turns it on.

## 20. Recommended Defaults For Prototype

- Active guest retention: 24 hours after last use.
- Claim-pending retention: 72 hours.
- One consumed guest provider search per device/IP abuse window.
- No universal CAPTCHA; challenge only elevated-risk attempts.
- One top usable match, consistent with the mobile product decision.
- No minimum numeric notification threshold in the guest UI.
- Recurring matching remains off until the newly verified user explicitly enables it.
- Guest work is claimed without charging the new account's weekly allowance.

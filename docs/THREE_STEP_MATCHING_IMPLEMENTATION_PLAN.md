# Three-Step Matching Implementation Plan

**Status:** Ready for implementation
**Architecture source:** [3-step_matching_v2.md](3-step_matching_v2.md)
**Audience:** Backend, mobile, web, data/ML, QA, security, and operations
**Last updated:** August 15, 2026

## Implementation Progress

### Contract and registry foundation — implemented August 15, 2026

- Added a separate `server/app/modules/matching_v2/` package without changing legacy callers.
- Added strict Pydantic response contracts for Candidate Profile extraction, Job Profile extraction, and Qualification Assessment.
- Added deterministic provider JSON Schema generation with request-scoped requirement and evidence-reference enums.
- Added immutable, content-hashed schema, prompt, taxonomy, semantic-validator, alternative, deterministic-policy, and role/track scoring registry entries.
- Registered `software-ic-score.v1` as the only approved public role-family/track scoring policy.
- Added all V2 return-path feature flags with public paths disabled and the legacy adapter enabled by default.
- Added focused contract, registry, prompt-envelope, policy-resolution, and configuration tests.

### Candidate persistence foundation — implemented August 15, 2026

- Added migration `20260815_0039` for canonical sources, UTF-8 evidence spans, Candidate Profile versions, career profiles, revisioned career selections, and the persisted policy registry.
- Added authenticated, guest, and shared ownership constraints while keeping candidate sources private and owner-scoped.
- Added immutable cache identity for canonical sources and Candidate Profile extraction inputs.
- Added repository validation for source ownership, exact span excerpts, UTF-8 boundaries, evidence-reference membership, and optimistic career-selection revisions.
- Added idempotent synchronization from the code-owned immutable registry into the database registry.
- Added metadata, repository, migration-upgrade, cache, ownership, evidence, and revision-conflict tests.

### Candidate extraction vertical slice — implemented August 15, 2026

- Added canonical-text v1 normalization and deterministic semantic span generation with exact half-open UTF-8 byte offsets.
- Added bounded, qualification-section-prioritized model input with explicit omitted-span quality warnings.
- Added the strict Candidate Profile provider call, request-scoped evidence enums, semantic evidence validation, and low-confidence level normalization.
- Added internal/shadow-only authenticated APIs to create, cache, retrieve, and revise Candidate Profiles without changing legacy profile routes.
- Added deterministic fallback source rendering for manually entered resume profiles and raw extracted-document use for uploaded resumes.
- Added canonicalization, span-boundary, input-selection, confidence, API cache, retrieval, access-gate, and revision-conflict tests.

## 1. Outcome

Implement the evidence-based matching architecture without interrupting the current guest trial, saved-job matching, or scheduled-search workflows.

The first public version will:

- Extract immutable Candidate Profiles from resumes.
- Extract immutable Job Profiles from cleaned job descriptions.
- Ask the model for requirement-level Qualification Assessments without scores.
- Evaluate preferences and candidate eligibility in deterministic application code.
- Publish reproducible 0–100 scores only for approved software-engineering individual-contributor jobs.
- Return `needs_more_information` with null public scores for unsupported role-family/track policies or insufficient assessment coverage.
- Preserve the current 0–10 matcher until each caller has migrated and rollback retention has expired.

This plan covers implementation and limited rollout. General availability still requires the product decisions and evaluation gates in the architecture document.

## 2. Delivery Principles

1. Build V2 beside the existing matcher and migrate callers incrementally.
2. Make each persisted artifact immutable and reproducible from explicit versioned inputs.
3. Keep model-owned extraction and classification separate from application-owned identity, scoring, eligibility, preferences, and recommendations.
4. Add the deterministic engine and fixtures before enabling V2 results in a user interface.
5. Treat software engineering on the individual-contributor track as the only approved public scoring policy in V1.
6. Use feature flags for shadow execution, internal-super access, guest access, scheduled matching, and legacy read compatibility.
7. Land migrations as additive changes first; defer legacy-column removal to a separately approved cleanup.

## 3. Current-System Integration Points

| Current area | Existing responsibility | V2 integration |
|---|---|---|
| `server/app/modules/resume_job_match/` | Single-call 0–10 matching | Retain as `legacy`; introduce a new `matching_v2` module and a compatibility adapter. |
| `server/app/modules/profiles/` | Resume profiles and readiness | Create or resolve Candidate Profile versions after readiness succeeds. |
| `server/app/modules/jobs/` | Parsed and cached jobs | Attach immutable Job Profile versions to cached job content hashes. |
| `server/app/modules/guest_trials/` | Immediate account-free trial | Evaluate the first usable unique provider result through V2 when the guest flag is enabled. |
| `server/app/modules/automation/` | Weekly search, worker, quota, persistence | Replace direct legacy matcher calls with the versioned V2 orchestrator behind a flag. |
| `server/app/modules/notifications/` | Inbox and daily digest | Render V2 recommendation, evidence, and needs-information results without score fabrication. |
| `mobile/lib/src/matching/` | Mobile matching API models | Add nullable V2 scores, coverage, recommendation, questions, and policy metadata. |
| `client/app/match/` | Web match presentation | Read the same versioned API contract as mobile after backend stabilization. |

The new backend package should start with this shape:

```text
server/app/modules/matching_v2/
  __init__.py
  models.py
  schemas.py
  repositories.py
  registry.py
  prompts.py
  extraction.py
  qualification.py
  preferences.py
  eligibility.py
  scoring.py
  explanations.py
  orchestration.py
  router.py
```

Files may be split further as they grow, but model calls, deterministic policies, persistence, and orchestration must remain separate modules.

## 4. Feature Flags And Compatibility Modes

Add centrally configured flags with safe defaults:

| Flag | Initial value | Purpose |
|---|---:|---|
| `matching_v2_shadow_enabled` | Internal environments only | Run V2 without changing the returned legacy result. |
| `matching_v2_internal_super_enabled` | `false` | Return V2 to internal-super accounts. |
| `matching_v2_guest_enabled` | `false` | Return V2 in account-free trials. |
| `matching_v2_automation_enabled` | `false` | Use V2 for scheduled matching. |
| `matching_v2_web_enabled` | `false` | Enable V2 web result rendering. |
| `matching_v2_mobile_enabled` | `false` | Enable V2 mobile result rendering. |
| `matching_legacy_adapter_enabled` | `true` | Populate legacy 0–10 responses only from eligible non-provisional V2 results during migration. |

The API must record which path produced every result. A flag change affects new operations only; it cannot reinterpret an immutable historical result.

## 5. Phased Delivery Plan

### Phase 0: Contract And Registry Foundation

**Outcome:** The architecture becomes executable contracts before any production path changes.

Work:

- Create strict Pydantic model-response schemas for candidate extraction, job extraction, and qualification assessment.
- Create separate persisted-artifact schemas containing application-owned IDs, versions, hashes, and timestamps.
- Generate normalized JSON Schema from Pydantic and add stable schema hashing.
- Implement immutable registries for prompts, schemas, semantic validators, taxonomies, alternatives, eligibility, preferences, and scoring policies.
- Register `software-ic-score.v1` as the only approved public role-family/track scoring policy.
- Add configuration and feature-flag parsing with production-safe defaults.
- Add fixtures proving model response schemas reject scores, recommendations, application IDs, and unknown fields.

Acceptance criteria:

- Every model response schema uses `additionalProperties: false` and strict validation.
- Registry versions cannot be overwritten with different content.
- Only `(software_engineering, individual_contributor)` resolves to an approved V1 public scoring policy.
- Generated schemas and hashes are stable across repeated test runs.

Dependencies: none.

### Phase 1: Additive Persistence And Repositories

**Outcome:** All V2 artifacts can be stored immutably without changing current reads.

Work:

- Add sequential Alembic migrations for canonical sources and spans, Candidate Profile versions and career profiles, career selections, Job Profile versions and requirements, qualification assessments, preference revisions and assessments, eligibility revisions and assessments, Match Results, and matching operations.
- Use foreign keys and ownership constraints to prevent cross-user attachment.
- Add cache-key uniqueness constraints defined in the architecture.
- Encrypt or otherwise apply the approved sensitive-field protection to Candidate Eligibility Facts.
- Add repository methods that require exact artifact IDs and revisions; never resolve “latest” implicitly during match execution.
- Add deletion-cascade support for guest-private artifacts and account lifecycle integration for authenticated artifacts.
- Update migration-history and empty-database validation scripts.

Acceptance criteria:

- Upgrade succeeds from the current migration head and on an empty database.
- Downgrade behavior is documented; destructive rollback is not required for deployed data.
- Duplicate cache-key insertion returns the existing immutable artifact safely.
- Cross-owner foreign-key and repository tests fail closed.
- Guest purge removes private V2 artifacts without deleting reusable shared Job Profiles.

Dependencies: Phase 0 schemas and version identifiers.

### Phase 2: Canonical Sources And Candidate Profile Extraction

**Outcome:** A ready resume produces a reusable, evidence-linked Candidate Profile.

Work:

- Implement deterministic resume canonicalization and UTF-8 byte-span generation.
- Connect existing uploaded, pasted, and guest resume pathways to canonical source creation.
- Implement the Candidate Profile extraction prompt and strict structured response.
- Validate source references, closed enums, career-profile limits, level confidence, and derived-versus-evidence fields.
- Attach durable career-profile IDs and trusted generation metadata after validation.
- Implement Candidate Career Selection revisions with optimistic concurrency.
- Reuse Candidate Profiles by the complete versioned cache key.
- Expose Candidate Profile creation, retrieval, primary selection, correction, and regeneration endpoints.

Acceptance criteria:

- Every evidence-bearing extracted field references a valid span from the exact canonical source.
- A changed source or extraction-policy input creates a new version; an unchanged key is a cache hit.
- Low-confidence candidate level persists as `unknown`.
- Corrections create a new immutable version and cannot mutate extracted history.
- Existing readiness behavior continues to work when V2 flags are disabled.

Dependencies: Phases 0–1.

### Phase 3: Job Profile Extraction And Reuse

**Status:** Complete in the internal/shadow implementation as of 2026-08-15. Public matching remains on the legacy path.

**Outcome:** The first usable provider job or imported job produces one normalized, reusable Job Profile.

Work:

- Reuse the existing URL-import and ATS-adapter security boundary to obtain raw job text.
- Add deterministic job canonicalization, boilerplate removal, duplicate-span removal, and content hashing.
- Implement the Job Profile extraction prompt and strict response.
- Validate atomic requirements, importance, hard-constraint ownership, scoring dimensions, application constraints, role family, track, target level, and evidence references.
- Reject or merge materially duplicate requirements deterministically.
- Attach Job Profile versions to existing cached jobs without copying candidate data into shared records.
- Expose Job Profile creation and retrieval endpoints.

Acceptance criteria:

- Duplicate job text cannot increase requirement weight.
- Every scored requirement has one validated scoring dimension.
- Missing location, compensation, authorization, sponsorship, travel, and clearance remain unknown.
- Shared Job Profiles are reusable only under the configured source-licensing and retention policy.
- Extraction limits produce `needs_more_information` instead of silent material truncation.

Dependencies: Phases 0–1. May proceed in parallel with Phase 2 after those foundations exist.

Implemented scope:

- Active reusable `jobs_cache` descriptions are the only accepted source boundary; URL fetching and ATS parsing remain owned by the existing hardened import path.
- Shared canonical job sources use stable content hashes and UTF-8 evidence spans. Exact duplicate and known boilerplate spans are removed before extraction.
- Strict Job Profile extraction validates source references, level ranges, scoring dimensions, duplicate requirements, and single ownership of application constraints.
- Immutable Job Profile versions and durable requirement IDs persist extraction, cleanup, source-policy, prompt, schema, taxonomy, model, and validator versions.
- `POST /api/v1/jobs/{job_id}/job-profile` and `GET /api/v1/job-profiles/{job_profile_id}` are available only through the existing internal/shadow access gate.
- The `cached-job-reuse.v1` registry policy permits reuse only for active cached jobs with non-empty imported descriptions, inherits their lifecycle, and prohibits candidate data in shared artifacts.
- Model input limits add an explicit `NEEDS_MORE_INFORMATION:MODEL_INPUT_OMITTED_SPANS` warning rather than silently treating omitted material as complete.

### Phase 4: Qualification Assessment

**Status:** Complete in the internal/shadow implementation as of 2026-08-15. No public score or recommendation is produced by this phase.

**Outcome:** One Candidate Profile and one Job Profile produce evidence-based requirement classifications without a model-generated score.

Work:

- Implement deterministic candidate career-profile selection and persist the selected context and reason code.
- Build bounded qualification input from validated Candidate Profile evidence and Job Profile requirements.
- Implement the strict qualification prompt and response validation.
- Require exactly one assessment for every normal and evidence-based hard requirement.
- Enforce positive-status evidence, approved alternatives, confidence conversion, and no duplicate ownership.
- Implement the complete qualification cache key, including career-selection revision and immutable provider policy inputs.
- Store provider execution references without logging raw private prompts or source text.

Acceptance criteria:

- The model cannot emit a score, recommendation, weight, or application-owned ID.
- Every Job Profile requirement is assessed exactly once in its owning collection.
- Positive statuses contain valid Candidate Profile evidence references.
- Missing ordinary evidence becomes `not_demonstrated`, not `needs_clarification`.
- A repeated identical qualification key performs no additional provider call.

Dependencies: Phases 2–3.

Implemented scope:

- `career-selection-policy.v2` deterministically selects the closest role-family and track context, uses the primary selection only as a class-5 fallback, and persists the selection revision and reason code.
- Qualification input contains validated Job Profile v3 requirements, structured alternative groups, the non-derived Candidate Profile collections, and their evidence spans. `qualification-input.v2` enforces a deterministic UTF-8 byte limit and records omitted evidence explicitly.
- The strict Qualification Assessment v2 provider contract emits exactly one requirement collection using `met`, `met_by_alternative`, `partially_met`, or `not_demonstrated`; it cannot emit scores, weights, recommendations, eligibility outcomes, hard-constraint collections, or application-owned artifact IDs.
- Semantic validation enforces exact requirement coverage, valid candidate evidence, positive-status evidence, exact employer alternative-group references, registered server policy references, partial gaps, and evidence-free `not_demonstrated` decisions. Model confidence is retained for auditability but cannot rewrite an evidence status.
- Immutable private Qualification Assessments and normalized requirement-assessment rows persist complete version and policy identities, selected career context, bounded-input quality, and provider execution references.
- The complete cache key includes Candidate Profile, exact career-selection revision, Job Profile, schema, prompt, model, selection, matching, input, semantic-validator, and applicable alternative-policy hashes.
- `POST /api/v1/qualification-assessments` and `GET /api/v1/qualification-assessments/{qualification_assessment_id}` are available only through the existing internal/shadow access gate and enforce tenant ownership.

### Phase 5: Deterministic Preferences, Eligibility, Scoring, And Explanation

**Status:** Complete in the internal/shadow implementation as of 2026-08-15. Public orchestration and caller cutover remain in Phase 6 and later phases.

Implemented scope:

- Added deterministic User Preference evaluation for roles, location, workplace type, compensation, employment type, desired skills, avoided industries, and single-owner user hard constraints.
- Added deterministic Candidate Eligibility evaluation for employer-stated work authorization, sponsorship, travel, and clearance constraints. Missing user facts remain `unknown` and never become inferred violations.
- Added the pure `score.v1` engine with approved role/track resolution, level-aware requirement weights, qualification and preference coverage, decimal half-up rounding, publication thresholds, recommendation thresholds, and deterministic gate precedence.
- Added deterministic explanation rendering from validated assessments and reason codes only; it cannot invent evidence, scores, or recommendations.
- Added the executable architecture fixture asserting qualification score `68`, preference score `50`, and overall score `63`, plus focused edge-case tests for unsupported policies, provisional job level, insufficient coverage, incomplete preferences, and gates.

- Added immutable preference and AES-256-GCM-encrypted eligibility revisions with optimistic concurrency and authenticated owner scoping. Encryption keys remain outside the database and missing keys fail closed.
- Added immutable, content-addressed Preference Assessments, Eligibility Assessments, and Match Results with explicit policy identities and reusable cache keys.
- Added internal/shadow authenticated preference and eligibility revision APIs plus Match Result creation/retrieval APIs.
- Added the legacy 0–10 adapter only when an overall score is publishable and the compatibility flag is enabled.

**Outcome:** Validated assessments become a fully reproducible Match Result.

Work:

- Implement immutable User Preference revisions using the V1 schema.
- Implement every deterministic preference rule, tie-break, taxonomy dependency, completeness rule, and no-double-counting rule from Section 10 of the architecture.
- Implement Candidate Eligibility Facts revision APIs with optimistic concurrency and private storage.
- Implement deterministic Eligibility Assessment for every material Job Profile application constraint.
- Implement qualification weights, coverage, preference score, hard gates, overall score, rounding, and recommendation thresholds as pure functions.
- Refuse public scoring for unsupported role-family/track policies and emit `SCORING_POLICY_NOT_APPROVED`.
- Permit the approved-policy `mid` fallback only for unknown or low-confidence job level; never change tracks.
- Render strengths, gaps, unknowns, preference conflicts, questions, and evidence through deterministic templates.
- Implement the legacy 0–10 adapter only for non-provisional V2 results.

Acceptance criteria:

- The document's executable fixture returns qualification 68 and overall 63.
- Preference and eligibility evaluation require no model calls.
- Unsupported tracks and unapproved role-family/track pairs return null public scores and `needs_more_information`.
- Hard constraints are gated once and never included in a numerical numerator or denominator.
- Replaying persisted inputs under the same policies produces byte-equivalent score fields and reason codes.
- Missing guest eligibility facts produce unknown questions, not inferred facts or automatic violations.

Dependencies: Phase 4 for end-to-end results; deterministic engines can be developed against fixtures earlier.

### Phase 6: Orchestration, API, Retry, And Idempotency

**Status:** In progress as of 2026-08-16. The first authenticated orchestration slice is implemented
locally and remains behind the existing V2 internal/shadow access gate.

**Outcome:** V2 runs through one durable operation contract for synchronous and asynchronous callers.

Implementation checkpoint:

- Candidate Profile extraction and Job Profile extraction remain independently callable workflows with
  their own persisted immutable outputs. `POST /api/v1/matches` accepts those output IDs and never
  silently invokes either extractor.
- The deterministic pre-step immediately before detailed matching is named **Job Family Pre-Match**. It
  consumes the Candidate Profile, revisioned Matching Intent, and Job Profile general family/track/level;
  it selects the candidate career context and persists compatibility dimensions and reason codes.
- Added owner-scoped `matching_operations` and `matching_operation_stages` persistence with correlation
  IDs, request hashes, leases, heartbeats, per-stage attempts, stable errors, input/output artifact IDs,
  cache markers, provider-usage fields, policy versions, and timestamps.
- Added match creation/retrieval, operation polling, explicit retry, and rerun API contracts.
- Matching retries resume from the first incomplete stage. Completed Candidate Profile and Job Profile
  dependencies are reused, and a failed Qualification Assessment retry does not rerun either extraction.
- Identical owner/idempotency/input tuples return the original operation. Reusing a key with different
  artifact or revision inputs returns `409 IDEMPOTENCY_KEY_REUSED`.
- Routine operation responses and logs contain artifact IDs and stable diagnostics, not resume text, job
  text, prompts, contact data, or eligibility facts.

Remaining Phase 6 work:

- Add revisioned Matching Intent and immutable Job Family Pre-Match schemas, persistence, deterministic
  policy, APIs, and orchestration stage. Include the intent revision and pre-match policy/artifact identity
  in qualification cache keys and full-request idempotency.
- Move independent Candidate Profile and Job Profile extraction onto the same durable asynchronous
  operation/lease contract while retaining their direct cache-hit responses.
- Enforce the 45-second immediate-response boundary and return a still-running operation as `202`
  without waiting for a long provider call.
- Add durable worker pickup for pending and expired-lease operations instead of relying only on the
  initial in-process background task or explicit retry.
- Add cancellation, periodic heartbeat renewal during long provider calls, backoff with jitter, and the
  remaining latency/provider-usage metrics.
- Generate and check in the updated OpenAPI artifact after the complete Phase 6 contract stabilizes.

Work:

- Implement the operation state machine from pending through extraction, assessment, deterministic evaluation, scoring, and terminal states.
- Persist stage leases, attempts, heartbeats, artifact inputs, correlation IDs, and stable errors.
- Implement `POST /api/v1/matches`, match retrieval, operation polling, and explicit rerun.
- Enforce full request idempotency, explicit preference and eligibility revisions, and ownership validation.
- Reuse completed immutable stages after retry or worker restart.
- Add OpenAPI models and update the checked-in OpenAPI document.
- Instrument stage latency, cache hits, provider usage, validation failures, provisional reasons, and policy versions.

Acceptance criteria:

- A repeated idempotency key with identical inputs returns the existing operation; changed inputs return `409`.
- Provider timeouts do not fabricate artifacts or scores.
- Process interruption resumes from the first incomplete stage without repeating completed provider work.
- Synchronous timeout returns `202` with a pollable operation rather than failing an otherwise active match.
- Routine logs contain no raw resume, raw job, complete prompt, name, contact information, or eligibility facts.

Dependencies: Phases 1–5.

### Phase 7: Guest Trial Vertical Slice

**Outcome:** A guest receives one immediate evidence-based result from the first usable unique job.

Work:

- Replace the current best-of-retained-candidates selection with the approved first-usable-result behavior when the V2 guest flag is enabled.
- Reuse Candidate Profile extraction completed during profile readiness.
- Run no more than one Job Profile extraction and one Qualification Assessment for the returned job.
- Preserve current provider-search reservation and no-charge-on-provider-failure behavior.
- Return inline when complete; otherwise return the operation and poll immediately.
- Render null-score needs-information results without presenting them as failures.
- Preserve guest-to-account claim mapping for source, profile, criteria, result, and immutable artifact references.

Acceptance criteria:

- The guest path does not wait for weekly automation.
- It returns the first usable unique provider result regardless of score.
- Provider failure does not consume the trial allowance.
- The guest path meets the 45-second inline boundary and 90-second hard operation deadline.
- Guest deletion and expiration remove all private matching artifacts.

Dependencies: Phase 6 and the existing guest-trial foundation.

### Phase 8: Scheduled Matching, Inbox, And Digest

**Outcome:** Existing weekly entitlements can execute V2 and deliver one result per successful search.

Work:

- Adapt `automation/executor.py` to call the V2 orchestrator behind `matching_v2_automation_enabled`.
- Preserve Free/Starter/Plus weekly provider-search limits of 1/3/5 and unlimited internal-super access subject to operational limits.
- Skip previously seen jobs and unchanged Candidate Profile/Job Profile pairs before qualification calls.
- Persist provisional results in the private inbox under “Needs more information.”
- Update daily digest templates for V2 recommendation labels and nullable scores.
- Preserve manual revised-resume reruns without provider-search quota when the Job Profile is retained.

Acceptance criteria:

- Failed or unusable provider searches consume no quota.
- A usable provider response consumes one search unit even when downstream work must retry.
- Each successful search contributes at most one new digest item.
- Duplicate suppression occurs before a repeated qualification call or notification.
- Reruns preserve old and new immutable result histories.

Dependencies: Phases 6–7; can be enabled independently from the guest flag.

### Phase 9: Mobile And Web Presentation

**Outcome:** Clients present V2 evidence and uncertainty accurately without reproducing business logic.

Work:

- Add V2 API models to the Dart matching repository, including nullable component scores, coverage, recommendation, policy reason codes, questions, strengths, gaps, unknowns, and preference conflicts.
- Add profile-level and track confirmation UI without requiring it before the first supported match.
- Add authenticated preference and eligibility editing with revision-conflict recovery.
- Update guest, match inbox, match detail, and rerun screens.
- Apply the same response contract to the web match page after the mobile contract stabilizes.
- Keep all scoring, gating, and compatibility conversion on the server.

Acceptance criteria:

- Clients render `needs_more_information` without substituting zero.
- Evidence links display only excerpts authorized by the API.
- A stale eligibility or preference edit prompts refresh and retry instead of overwriting a newer revision.
- Existing legacy results remain readable during migration.
- Flutter unit/widget tests and web contract tests cover supported, provisional, conflict, and provider-failure states.

Dependencies: Stable Phase 6 API; UI work can begin against generated fixtures.

### Phase 10: Shadow Evaluation And Controlled Rollout

**Outcome:** V2 becomes public only after correctness, privacy, latency, and cost gates pass.

Work:

- Run V2 beside legacy matching for internal-super accounts and collect de-identified evaluation metrics.
- Build the consented and adjudicated golden sets required by the architecture.
- Compare evidence support, extraction quality, classification agreement, ranking, score distribution, latency, and token cost.
- Rehearse feature-flag rollback, operation recovery, migration deployment, and deletion cascades.
- Enable return-path flags in this order: internal super, guest trial, scheduled matching by tier, mobile, then web.
- Keep unsupported tracks in shadow mode until each has its own approved policy and stratified evaluation.

Acceptance criteria:

- Every numerical and safety gate in Section 28 of the architecture passes for the enabled slice.
- No severe hard-constraint regression or cross-tenant access failure remains open.
- Production rollback has been rehearsed without deleting V2 history.
- Cost remains within the configured per-result budget.
- Product and engineering jointly approve the exact enabled role-family/track scope.

Dependencies: Phases 0–9.

## 6. Recommended Pull Request Sequence

Keep pull requests independently testable and deploy additive backend foundations before caller migrations:

1. V2 schemas, registries, policy fixtures, and feature flags.
2. Additive database migrations and repositories.
3. Canonical source/span infrastructure and Candidate Profile extraction.
4. Job Profile extraction and cached-job integration.
5. Qualification Assessment and evidence validators.
6. Preference, eligibility, and scoring pure functions.
7. Match Result, explanation renderer, and legacy adapter.
8. Operation state machine, API, OpenAPI, and observability.
9. Guest V2 integration behind its flag.
10. Automation, inbox, and digest integration behind their flag.
11. Flutter client support, followed by web client support.
12. Evaluation tooling, shadow reports, and controlled flag enablement.

Do not combine schema/persistence foundations with guest or automation cutover in one pull request.

## 7. Test Matrix

| Layer | Required coverage |
|---|---|
| Schema | Strict acceptance/rejection, bounds, enums, unknown fields, and model/application ownership. |
| Canonicalization | Stable hashes, UTF-8 spans, document formats, deterministic section selection, and truncation warnings. |
| Extraction | Evidence validity, atomic requirements, duplicate removal, career context, application constraints, and adversarial instructions. |
| Qualification | Exactly-once coverage, positive evidence, alternatives, confidence conversion, and cache identity. |
| Preferences | Every status rule, importance, tie-break, unknown handling, incomplete jobs, and duplicate rejection. |
| Eligibility | Satisfied, violated, unknown, not applicable, guest absence, privacy, revision conflict, and no double gating. |
| Scoring | All statuses, dimensions, levels, coverage boundaries, hard gates, thresholds, half-up rounding, and unsupported policies. |
| Persistence | Uniqueness, ownership, immutable history, deletion cascade, cache reuse, and concurrent creation. |
| Operations | Retries, leases, heartbeat recovery, timeout-to-poll, idempotency, cancellation, and provider failures. |
| Integrations | Guest first result, weekly quota, duplicate suppression, daily digest, rerun, claim, mobile, and web. |
| Security | Cross-owner denial, prompt injection, SSRF boundary reuse, sensitive logging, encrypted eligibility facts, and deletion. |
| Evaluation | Evidence precision, extraction precision/recall, agreement, hard-constraint errors, ranking, latency, and cost. |

## 8. Operational Readiness Checklist

Before enabling a V2 return-path flag in us3:

- Database migrations and migration-history validation pass on a production-like copy.
- All registry content and hashes are included in the release manifest.
- Provider model identifiers and data-handling settings match approved configuration.
- Worker concurrency, timeouts, and stage retry limits are configured.
- Dashboards distinguish legacy, V2 shadow, V2 public, cache hit, provisional, and failed operations.
- Alerts cover schema failures, evidence-reference failures, provider failures, stuck leases, latency SLOs, and cross-owner denials.
- Guest purge, account deletion, and backup-retention behavior have been verified.
- OpenAPI, mobile models, and deployed server routes agree.
- Rollback flags and the legacy path have been exercised in us3.

## 9. Definition Of Implementation Complete

Implementation is complete for limited rollout when:

- Phases 0–9 are merged and deployed behind flags.
- All automated tests in Section 7 pass in CI.
- Existing legacy tests continue to pass.
- The complete V2 pipeline works for authenticated, guest, scheduled, and rerun paths.
- Only approved software-engineering individual-contributor jobs receive public scores.
- Historical results remain reproducible from immutable artifacts and registry versions.
- The mobile application installed from the us3-connected build can complete and display the V2 guest and authenticated flows.
- Operations can observe, retry, disable, and roll back V2 without data loss.

Limited rollout begins only after Phase 10 gates pass. General availability additionally requires resolution of the remaining product decisions in Section 30 of the architecture.

## 10. First Implementation Slice

Start with a non-user-visible vertical foundation:

1. Create `matching_v2` schemas and immutable registries.
2. Add feature flags with all public flags disabled.
3. Add the first additive migration set and repositories.
4. Implement canonical resume source spans and Candidate Profile extraction.
5. Add unit tests for strict schemas, version hashes, source references, cache identity, and ownership.
6. Deploy the additive foundation to us3 with no caller cutover.

This slice is complete when an internal test can create and retrieve a versioned Candidate Profile with valid evidence spans while every existing matching route continues returning its unchanged legacy response.

# DaliJob Ask Scout V2 Improvement Plan

Status: proposed. Ask Scout V1 remains implemented and documented in
`ASK_SCOUT_IMPLEMENTATION_PLAN.md`. This document defines the next improvement
phase; none of the V2 checklist items should be treated as implemented yet.

## Purpose

Ask Scout V1 safely maps a user's question to an allowlisted DaliJob page. V2
should make that guidance more accurate, contextual, and useful without turning
Scout into an autonomous agent.

The central design rule remains unchanged:

> Ask Scout may explain, recommend, navigate, and safely prefill. The user must
> review and perform every consequential action.

V2 should improve Scout's understanding through better product context, not by
giving the model unrestricted access to the browser, database, source code, or
write-capable application APIs.

## Current V1 Behavior

For each question, the server currently sends OpenAI:

- the user's current question;
- the validated DaliJob path from which Scout was opened;
- optional selected application, saved-job, interview, and resume-profile IDs;
- a compact catalog of allowlisted actions and short descriptions; and
- a system prompt that enforces passive guidance.

The model does not receive the DaliJob source code, page DOM, account records,
resume content, job descriptions, documents, or previous questions. The server
validates the returned action ID and constructs the destination URL itself.

This produces a strong security boundary, but it also limits answer quality.
Scout knows that a page exists, but often does not know:

- the controls and workflow steps available on that page;
- prerequisites for completing a workflow;
- whether the signed-in user has satisfied those prerequisites;
- recent product terminology or UI changes;
- what a follow-up question refers to; or
- why a control may be unavailable in the user's current state.

## Current Gaps

### Product Knowledge Drift

The action catalog is manually maintained and some descriptions no longer match
the current product. For example:

- Home is described as showing setup alerts and best matches, although those
  functions now belong primarily to Dashboard.
- Manual job creation is described as entering all job details manually, while
  the current flow accepts a title and job description and generates the
  structured profile.
- The catalog does not explain Getting Started, saved search criteria, document
  dependencies, application tasks, or the read-only and edit states of detail
  views.

Because this catalog is the model's primary product knowledge, stale catalog
content directly causes stale answers.

### Insufficient User State

Scout cannot currently distinguish between users who have no resume, one default
resume, saved jobs that still need matching, or existing applications. It must
therefore give generic instructions even when DaliJob already knows the next
useful step.

### No Follow-Up Context

Answers are retained in React state for display, but prior turns are not sent to
the provider. Questions such as `What about the other option?` are effectively
new, context-free requests.

### Limited Quality Measurement

The current tests strongly validate routing safety, but there is no broad,
versioned evaluation set for answer correctness, current terminology,
prerequisites, or multi-turn behavior. Users also cannot indicate that an answer
was unhelpful.

## Goals

1. Keep Scout's product knowledge synchronized with shipped DaliJob workflows.
2. Give personalized next-step guidance from bounded, non-sensitive account
   facts.
3. Support short follow-up conversations without permanently storing chat
   history.
4. Prefer deterministic routing for clear intents and use the model for language,
   ambiguity resolution, and explanation.
5. Measure answer quality with repeatable evaluations and user feedback.
6. Preserve the V1 passive-action, ownership, CSRF, rate-limit, and route-
   allowlist boundaries.
7. Keep token use predictable by sending only relevant product knowledge.

## Non-Goals

V2 will not:

- click buttons, submit forms, start operations, upload files, or mutate records;
- provide the model with SQL, filesystem, browser, MCP, or arbitrary HTTP tools;
- send resume text, job descriptions, document bodies, notes, or email content;
- let the model create routes, HTTP methods, API payloads, or unvalidated IDs;
- answer broad career-advice questions that are unrelated to DaliJob workflows;
- create a permanent general-purpose chat archive; or
- replace authorization checks in destination APIs.

## Proposed Architecture

```text
Ask Scout page
  -> validated question, current path, selected IDs, bounded prior turns
  -> POST /api/v1/operations/ask-scout
  -> authenticated account-state summary builder
  -> deterministic intent and URL extraction
  -> product knowledge registry lookup
  -> relevant workflow context selection
  -> OpenAI structured response
  -> server normalization and allowlisted action construction
  -> managed-operation result
  -> guidance, destination, explanation, and optional feedback controls
```

The model remains one component inside a server-controlled decision pipeline. It
does not become the source of truth for routes, permissions, account state, or
workflow completion.

## Product Knowledge Registry

### Single Source Of Truth

Replace the short action-only descriptions with a typed product knowledge
registry. The registry should remain server-owned and code reviewed.

Each workflow definition should contain:

```python
@dataclass(frozen=True)
class ScoutWorkflowDefinition:
    action_id: str
    label: str
    path: str
    purpose: str
    aliases: tuple[str, ...]
    prerequisites: tuple[str, ...]
    steps: tuple[str, ...]
    limitations: tuple[str, ...]
    related_action_ids: tuple[str, ...]
    allowed_parameters: tuple[str, ...]
    relevant_state_keys: tuple[str, ...]
    visibility: Literal["authenticated", "admin"] = "authenticated"
```

The existing route catalog should either be generated from this registry or
become its routing subset. Route construction and parameter sanitation must stay
deterministic.

### Initial Knowledge Coverage

The first V2 registry should describe:

- Home introduction and Getting Started;
- Dashboard alerts, recommended next step, best matches, and recent jobs;
- Resumes: import, anonymized analysis, manual profiles, default resume, and
  document dependencies;
- Saved Jobs: URL import, list import, manual creation, analysis-on-match,
  matching, archive, and selection actions;
- Job Search: saved criteria, manual searches, import behavior, and result limits;
- Match: resume-profile and pasted-resume choices, pasted descriptions, URL
  matching, and saved-job matching;
- Applications: creation, status tracking, tasks, notes, documents, materials,
  and interviews;
- Documents: upload, versions, download, dependency behavior, and deletion;
- Materials: tailored resumes and cover letters tied to application and document
  versions;
- Interviews: adding interviews, preparation generation, and application links;
- Analytics, Account, Operations, reports, and administrator-only diagnostics;
- Ask Scout's own passive boundary and limitations.

### Registry Validation

Automated checks should fail when:

- a registry path has no Next.js page;
- two workflows use the same action ID;
- a related action ID is missing;
- a declared query parameter lacks a destination-page adapter;
- an administrator-only action is included for a normal user; or
- required fields are blank or exceed prompt-size limits.

The registry should carry a version such as `product-knowledge-v2`. The selected
version should be recorded with the managed operation for debugging and
evaluation reproducibility.

## Relevant-Knowledge Selection

Sending the entire registry on every request will become wasteful as DaliJob
grows. V2 should use a small deterministic selector before calling OpenAI.

### First Implementation

Use local scoring over:

- route proximity;
- action aliases;
- words and URLs in the question;
- selected record types; and
- related workflow IDs.

Always include:

- Ask Scout's passive boundary;
- the current page workflow;
- the highest-scoring workflows;
- directly related workflows; and
- a compact list of all remaining action IDs and labels so unsupported requests
  can still be recognized.

This avoids adding an embedding service or vector database for a relatively
small help corpus. Embedding retrieval should be considered only when measured
evaluation results show that deterministic selection no longer scales.

## Safe Account-State Context

### Principle

Scout should know account facts that affect navigation, but not user-authored
content. The state summary must be computed on the server after authentication;
the browser must not be trusted to assert account state.

### Proposed Contract

```json
{
  "tutorial_completed": true,
  "resume_profile_count": 2,
  "has_default_resume": true,
  "saved_job_count": 8,
  "jobs_ready_to_match_count": 3,
  "application_count": 2,
  "upcoming_interview_count": 1,
  "document_count": 4,
  "selected_record": {
    "application_id": null,
    "job_id": 17,
    "interview_id": null,
    "resume_profile_id": null
  }
}
```

The exact fields should be added only when they support a documented guidance
decision. Zero-value counts are useful; titles, descriptions, notes, filenames,
and document contents are not required.

### State Derivation

Create `server/app/modules/scout/context.py` to build the summary using
owner-scoped repository queries. Reuse existing dashboard and repository logic
where practical, but do not call HTTP endpoints from the server.

The context builder must:

- verify every selected ID belongs to the authenticated identity;
- omit a selected ID when ownership cannot be established;
- use aggregate queries rather than loading full rows;
- tolerate an individual optional count failing by returning an unknown value;
- never serialize ORM records directly; and
- have a strict output schema with no arbitrary metadata.

### Personalized Guidance Examples

| Account state and question | Expected guidance |
| --- | --- |
| No resume, `How do I match a job?` | Explain that a resume profile is needed first and recommend Resumes. |
| Default resume exists, no saved jobs | Recommend Job Search or Import Job before Match. |
| Saved jobs need matching | Recommend Saved Jobs and explain Match/Match All. |
| Selected application exists | Recommend its detail page for tasks, documents, materials, or interviews. |
| Getting Started incomplete | Explain the locked first-time workflow and recommend Getting Started. |

## Deterministic Intent Handling

Clear requests should not rely entirely on model judgment. Add deterministic
handling for high-confidence cases such as:

- one HTTP URL plus `job`, `posting`, or `import` -> single-job import;
- one HTTP URL plus `list`, `results`, or `search page` -> job-list import;
- `upload resume` -> Resumes;
- `saved jobs`, `my jobs`, or `archive job` -> Saved Jobs;
- `application`, `task`, or `application status` -> Applications;
- `interview preparation` -> Interviews; and
- `password`, `delete account`, or `report issue` -> Account.

The deterministic layer may select candidate workflows and prefill values, but
the provider may still write the concise explanation. Ambiguous requests should
continue to use structured model classification.

When intent confidence is low, Scout should ask one concise clarifying question
instead of guessing. The public response contract should therefore add a
`clarification_prompt` field or allow `needs_context` to carry a focused question.

## Bounded Conversation Context

### V2 Scope

Support follow-ups within the currently open Ask Scout page only. Do not create a
permanent conversation table in the first V2 release.

The client may send at most three prior turns, with limits such as:

- maximum 500 characters per prior user question;
- maximum 750 characters per prior Scout answer;
- maximum 3 prior turns; and
- maximum 3,000 characters across conversation context.

All client-supplied history is untrusted. It must be separated from system and
registry instructions and must not carry route authority, record ownership, or
hidden state.

The server should prefer compact turn summaries:

```json
{
  "user_goal": "Import one job posting",
  "recommended_action_id": "open_job_import",
  "unresolved_context": []
}
```

If stronger tamper resistance becomes necessary, the server can return a signed,
short-lived continuation token containing only these summaries. A database-backed
conversation system is not justified until users need cross-device or long-term
history.

## Prompt And Response Contract

### Prompt Inputs

The V2 provider request should contain distinct sections for:

1. system policy and passive-action boundary;
2. selected product knowledge entries;
3. trusted account-state summary;
4. trusted current path and verified selected IDs;
5. untrusted bounded conversation history; and
6. the current untrusted user question.

The prompt must explicitly distinguish trusted server context from untrusted user
content.

### Structured Output

Retain the V1 status, action, alternatives, limitations, and confidence fields.
Add only fields that improve the UI contract:

```json
{
  "status": "navigate",
  "answer": "Your explanation",
  "action_id": "open_resume_profiles",
  "action_parameters": {},
  "alternative_action_ids": [],
  "limitations": [],
  "confidence": "high",
  "clarification_prompt": null,
  "state_basis": ["no_resume_profile"]
}
```

`state_basis` must use a server-defined enum and should only explain why guidance
was personalized. It must not expose sensitive values. The server should remove
internal confidence before returning the public response.

Increment the prompt version from `ask-scout-v1` to `ask-scout-v2` when this
contract ships.

## User Experience Changes

The dedicated Ask Scout page should remain compact and work-focused.

Add:

- short contextual text such as `Based on your current Saved Jobs view`;
- a visible clarification question for `needs_context` responses;
- suggested follow-up prompts based on related workflows;
- Helpful and Not helpful controls after each completed answer; and
- a clear indication when guidance uses account setup state.

Do not add:

- a typing animation that delays an already available answer;
- tool traces, chain-of-thought, provider names, or token counts;
- automatic navigation after an answer;
- automatic execution on the destination page; or
- a large chat overlay that covers the current workflow.

## Feedback Design

### API

Add an authenticated endpoint such as:

```text
POST /api/v1/ask-scout/feedback
```

Request:

```json
{
  "operation_id": 42,
  "helpful": false,
  "reason": "wrong_destination"
}
```

Allowed reasons should be an enum:

- `wrong_destination`
- `outdated_instructions`
- `too_generic`
- `did_not_understand`
- `other`

Do not collect free-form feedback in the first version. It creates another
untrusted-content retention surface and is not required to identify broad
quality problems.

### Persistence

If feedback is retained, add an `ask_scout_feedback` table with:

- `id`
- `managed_operation_id`
- `workspace_id`
- `user_id`
- `helpful`
- `reason`
- `created_at`
- `updated_at`

Enforce one active feedback record per user and operation. Verify operation
ownership before insert or update. Do not duplicate the question or answer in the
feedback table.

## Evaluation Strategy

Create a versioned evaluation dataset under `server/tests/fixtures/ask_scout/`.
Each case should declare:

- user question;
- current path;
- safe account-state fixture;
- optional prior-turn summaries;
- expected status;
- expected primary action ID or allowed set;
- forbidden actions;
- required answer concepts; and
- forbidden execution claims.

Evaluation groups should cover:

1. Common navigation and terminology.
2. Missing prerequisites.
3. Current-page and selected-record context.
4. URL import versus list import.
5. Multi-turn references.
6. Unsupported requests.
7. Destructive or mutation wording.
8. Prompt injection and malicious URLs.
9. Normal-user versus administrator visibility.
10. Product-regression cases for recently changed UI.

Use deterministic fake-provider tests for all security and normalization rules.
Provider-backed evaluation should be an explicit, cost-bearing command rather
than part of every unit-test run.

Recommended quality gates:

- 100% of safety and route-allowlist cases pass;
- at least 95% expected primary-action accuracy on high-confidence questions;
- no invented routes or record IDs;
- no execution claims;
- no regression in V1 URL-prefill behavior; and
- a documented review for every changed knowledge-registry entry.

## Observability

Continue using managed-operation metadata. Add structured fields for:

- prompt version;
- product-knowledge version;
- selected workflow IDs;
- deterministic-intent result;
- whether account state influenced the answer;
- public status and normalized action ID;
- latency and available token usage; and
- feedback outcome when available.

Do not log:

- full questions or conversation history;
- URLs with query strings;
- record titles, notes, filenames, resume data, or job descriptions;
- model chain-of-thought; or
- cookies, secrets, or provider credentials.

## Security Review

V2 must preserve or strengthen these controls:

- authentication, CSRF, per-user rate limits, and operation ownership;
- allowlisted relative paths and parameters;
- owner verification for selected record IDs;
- server-derived account state;
- strict request and model-output schemas;
- output rendered as text rather than HTML;
- no model-authored HTTP requests or destination URLs;
- bounded prompt and history sizes;
- administrator workflow filtering based on authenticated role; and
- destination APIs performing their normal authorization checks.

Product knowledge and state context should be treated as information disclosure
surfaces. The public answer must not reveal hidden counts, administrator features,
or record existence that the current user is not authorized to know.

## Failure Behavior

- Context query failure: answer with generic product guidance and do not claim
  the missing state is false.
- Knowledge selection failure: use a small static catalog fallback.
- Provider unavailable: return common safe shortcuts and preserve the question
  for retry.
- Low confidence: ask a clarification question rather than selecting a route.
- Stale or removed destination: fail registry route validation in CI.
- Invalid model output: return a safe failure without exposing provider output.
- Rate limit: preserve current page state and display retry guidance.

## Proposed File Changes

```text
server/app/modules/scout/
  catalog.py          # Route construction and parameter sanitation
  knowledge.py        # Typed workflow registry and versions
  context.py          # Owner-scoped safe account-state summary
  retrieval.py        # Deterministic relevant-workflow selection
  prompts.py          # V2 prompt and response schema
  schemas.py          # Context, history, response, and feedback contracts
  service.py          # Intent routing, provider call, normalization
  repository.py       # Feedback persistence only, if enabled
  router.py           # Feedback endpoint only; operations stay in operations router

client/components/AskScoutPage.tsx
client/lib/api.ts
server/tests/fixtures/ask_scout/
server/tests/test_ask_scout.py
server/tests/test_ask_scout_context.py
server/tests/test_ask_scout_knowledge.py
server/tests/test_ask_scout_feedback.py
client/test/ask-scout.test.mjs
```

Keep provider execution in the existing managed-operations infrastructure. Do
not move the full Scout flow into a new synchronous endpoint.

## Implementation Phases

### Phase 0: Correct The V1 Baseline

- [ ] Audit every current DaliJob page and workflow against the V1 catalog.
- [ ] Correct stale Home, Dashboard, manual-job, matching, and resume terminology.
- [ ] Add missing supported pages and intentionally document excluded diagnostic
  or administrator-only pages.
- [ ] Add catalog-to-route and catalog-to-prefill-adapter tests for the corrected
  inventory.

Exit criteria: current single-turn questions are grounded in the shipped UI.

### Phase 1: Product Knowledge Registry

- [ ] Add typed workflow definitions and `product-knowledge-v2` versioning.
- [ ] Generate the routing catalog from the registry's safe routing fields.
- [ ] Document prerequisites, steps, limitations, aliases, and related workflows.
- [ ] Add registry integrity and prompt-size tests.
- [ ] Implement deterministic relevant-knowledge selection.

Exit criteria: route metadata and help content have one validated source of
truth, and each request sends only bounded relevant entries.

### Phase 2: Safe Account Context

- [ ] Add the strict account-state summary schema.
- [ ] Build owner-scoped aggregate queries in `scout/context.py`.
- [ ] Verify selected entity ownership before including IDs.
- [ ] Pass trusted state separately from untrusted user content.
- [ ] Add personalized prerequisite and next-step tests.

Exit criteria: Scout can distinguish common setup states without receiving
user-authored resume, job, document, or application content.

### Phase 3: Intent And Clarification

- [ ] Add deterministic candidate routing for common high-confidence intents.
- [ ] Add a structured clarification prompt for ambiguous requests.
- [ ] Preserve server-side action and parameter normalization.
- [ ] Add URL-import versus list-import ambiguity tests.

Exit criteria: clear questions route predictably and ambiguous questions do not
produce guessed destinations.

### Phase 4: Bounded Follow-Ups

- [ ] Add strict prior-turn summary schemas and size limits.
- [ ] Send at most three recent turns from the open Ask Scout page.
- [ ] Treat all prior client history as untrusted prompt content.
- [ ] Add follow-up, tampering, refresh, and token-budget tests.
- [ ] Decide from measured need whether signed continuation tokens are warranted.

Exit criteria: short references such as `What about the other option?` work
within one page session without permanent chat storage.

### Phase 5: Feedback And Quality Evaluation

- [ ] Add the versioned evaluation fixture set and evaluation runner.
- [ ] Add Helpful and Not helpful controls.
- [ ] Add the feedback endpoint, ownership checks, and migration if persistence is
  approved.
- [ ] Add action-accuracy, safety, stale-terminology, and prompt-injection gates.
- [ ] Document how product changes update registry entries and evaluation cases.

Exit criteria: answer quality is measurable and user-reported failures can be
grouped without retaining question text.

### Phase 6: Browser And Release Hardening

- [ ] Add browser tests for entry, follow-up, clarification, navigation, prefill,
  feedback, keyboard focus, and signed-out behavior.
- [ ] Add provider outage, invalid response, context failure, and rate-limit tests.
- [ ] Regenerate OpenAPI and update API, system-design, testing, and operations
  documentation.
- [ ] Run server tests, Ruff, client tests, lint, production build, OpenAPI drift,
  and provider-backed evaluation before release.

Exit criteria: V2 meets the existing passive-agent security boundary and the new
quality gates across server, client, and provider evaluation.

## Recommended Delivery Order

The highest-value sequence is:

1. Correct the stale V1 catalog.
2. Introduce the typed product knowledge registry.
3. Add the safe account-state summary.
4. Add deterministic intent and clarification.
5. Add bounded follow-up context.
6. Add feedback and broader provider evaluations.

Changing the OpenAI model should not be the first response to weak answers. A
larger model cannot reliably recover product facts that were never supplied or
were supplied incorrectly. Evaluate model changes only after the knowledge and
context improvements are measured.

## Acceptance Criteria

Ask Scout V2 is ready when:

- common DaliJob workflow questions use current product terminology and steps;
- guidance accounts for safe setup facts such as resume and saved-job presence;
- current-page and verified selected-record context improve the answer;
- short follow-up questions work within the open page session;
- ambiguous requests ask for clarification instead of guessing;
- every navigation action remains server allowlisted and non-executing;
- no prompt contains resume text, job descriptions, notes, files, or secrets;
- normal users cannot discover administrator-only destinations through Scout;
- evaluation gates meet the documented accuracy and safety thresholds; and
- user feedback can identify wrong, stale, or overly generic guidance without
  storing full conversations.


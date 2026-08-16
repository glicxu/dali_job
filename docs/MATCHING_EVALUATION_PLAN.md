# Three-Step Matching Evaluation Plan

Status: E1/E2 replay and human review pending; E3/E4 engineering foundations implemented
Scope: Candidate Profile, Job Profile, Qualification Assessment, and deterministic Phase 5 evaluation
Historical early scope: preferences, eligibility, numerical scoring, ranking, and recommendations
were excluded until the three generated-artifact stages were structurally stable.

## 1. Purpose

Evaluate the three generated-artifact stages and then evaluate Phase 5 deterministic scoring and
product-facing recommendations without moving scoring ownership into the model.

The early evaluation must answer:

1. Does Candidate Profile extraction preserve the qualifications actually supported by a resume?
2. Does Job Profile extraction produce complete, atomic, correctly classified requirements?
3. Does Qualification Assessment classify each requirement correctly and cite evidence that genuinely supports the classification?
4. Are role family, track, and level sufficiently reliable to support later scoring policies?
5. Are results reproducible enough to compare prompt, schema, policy, and model revisions on identical inputs?

The first five questions remain Phase 3/4 gates. Phase 5 evaluation extends the same frozen
benchmark to score calibration, ranking, thresholds, preferences, eligibility gates, and
recommendations.

## 2. Core Principle: A Frozen Benchmark, Not Random Search

Evaluation must not fetch a new random set of jobs for every run. Each benchmark release contains a curated, immutable collection of job snapshots and candidate fixtures.

Every benchmark job records:

- Stable benchmark job ID.
- Benchmark release ID.
- Employer and official source URL.
- Role-category and coverage-slot labels.
- Source-system or ATS type.
- Capture timestamp and whether the job was active when captured.
- Raw-content SHA-256 and canonical-content SHA-256.
- Extraction, canonicalization, deduplication, prompt, schema, taxonomy, model, and validator versions.
- Production-review status, recorded as `deferred_internal_testing` during the pilot.
- Storage reference for the frozen source snapshot.
- Human annotation status and adjudication history.

A refresh never overwrites an existing snapshot. It creates a new benchmark release or a new immutable job-snapshot version. Old releases remain replayable.

## 3. What “Quality Job” Means

Employer reputation alone does not make a posting suitable for evaluation. A benchmark job must satisfy a source-quality rubric:

- It comes from the employer's official careers site or an official ATS page.
- The posting contains a meaningful title, responsibilities, and qualifications.
- Required and preferred qualifications can be distinguished, or their ambiguity is deliberately labeled.
- The description is sufficiently complete for evidence-based matching.
- Boilerplate does not dominate the useful job content.
- The source can be captured through the existing hardened URL-import and ATS-adapter boundary.
- It can be frozen completely so the internal benchmark remains replayable.

“Tier-1 company” is a benchmark-cohort label used to obtain realistic, high-signal job descriptions. It must never be treated as evidence that a job, candidate, or match is inherently better.

## 4. Initial Curated Job Set: 10 Jobs

The first release, `matching-benchmark-jobs.v1`, contains ten coverage slots. A slot is filled only when a suitable active official posting is available.

| Slot | Target role | Domain/track | Target level | Preferred source cohort |
|---|---|---|---|---|
| 1 | Backend or distributed-systems engineer | Software engineering, IC | Mid or senior | Amazon, Google, or Microsoft |
| 2 | Infrastructure, cloud, or site-reliability engineer | Software engineering, IC | Senior | Google, Microsoft, or Amazon |
| 3 | Mobile or client-platform engineer | Software engineering, IC | Mid or senior | Apple, Google, or Microsoft |
| 4 | Machine-learning or data-platform engineer | Software/data, IC | Mid or senior | Microsoft, Google, Meta, or NVIDIA |
| 5 | Silicon, electrical, or hardware-design engineer | Hardware engineering, IC | Mid or senior | Apple, NVIDIA, Google, or Microsoft |
| 6 | Embedded-systems or firmware engineer | Hardware/software boundary, IC | Senior | Apple, Amazon, Microsoft, or NVIDIA |
| 7 | Product Manager | Product management | Mid or senior | Google, Microsoft, Amazon, or Apple |
| 8 | Technical Program Manager | Technical program | Senior | Microsoft, Google, Amazon, or Apple |
| 9 | Engineering Manager | Engineering management | Manager | Amazon, Google, Microsoft, Meta, or Apple |
| 10 | Principal engineer, architect, or senior technical leader | Architecture/leadership | Staff or principal | NVIDIA, Microsoft, Amazon, Google, or Apple |

Initial balancing rules:

- At least four employers.
- No employer supplies more than two of the ten jobs unless a documented source-availability exception is approved.
- At least four software IC jobs.
- At least two hardware or embedded jobs.
- At least one Product Manager and one Technical Program Manager job.
- At least two leadership-context jobs, counting engineering management, staff/principal, or architecture.
- At least three levels across the set.
- Include both clean and moderately ambiguous descriptions; exclude unusably incomplete postings.
- Do not select ten near-identical software-engineer roles merely because they are easy to fetch.

If the preferred employer for a slot has no usable active posting, another company from the approved cohort may fill the same slot. The coverage slot is stable; the employer assignment is not.

## 5. Expansion Set: 100 Jobs

After the ten-job pilot proves the workflow, expand to `matching-benchmark-jobs.v2` with approximately 100 jobs.

Recommended stratification:

| Slice | Approximate jobs |
|---|---:|
| Software engineering IC | 35 |
| Data, ML, and research | 12 |
| Hardware, silicon, firmware, and embedded | 15 |
| Product management | 10 |
| Technical program management | 8 |
| Engineering management | 10 |
| Staff, principal, and architecture tracks | 10 |

The 100-job set should also vary:

- Entry through principal level.
- Remote, hybrid, onsite, and unknown workplace types.
- Clear and ambiguous seniority language.
- Required versus preferred qualification quality.
- Explicit and absent compensation.
- Explicit and unknown authorization, sponsorship, travel, and clearance constraints.
- Multiple ATS platforms and employer career-site implementations.
- Short, medium, and long descriptions, including realistic duplicated boilerplate.

The expansion set is not allowed to become a convenience sample dominated by whichever source is easiest to scrape.

## 6. Job Acquisition Workflow

### 6.1 Source discovery

Use official employer career pages and official ATS-hosted pages. Search or provider discovery may identify candidate URLs, but benchmark admission requires a direct official source.

Do not use LinkedIn profile or job-page scraping as the canonical benchmark source. Do not bypass authentication, access controls, robots restrictions, or source terms.

### 6.2 Secure import

All network retrieval uses the existing job URL import boundary, including:

- SSRF protections and restricted redirects.
- Content-type and response-size limits.
- Structured-data extraction.
- Registered Greenhouse, Lever, Workday, SmartRecruiters, Ashby, and other approved ATS adapters.
- Existing boilerplate and content-quality checks.

The evaluation harness must not introduce a second unrestricted downloader.

### 6.3 Admission checks

Before freezing a job:

1. Confirm the official source and employer.
2. Confirm the posting was active at capture time.
3. Run deterministic extraction and calculate source hashes.
4. Score the source-quality rubric.
5. Assign exactly one primary coverage slot and optional secondary slice labels.
6. Check employer and role-distribution limits.
7. Mark the snapshot `deferred_internal_testing`; production source-policy review is not an admission gate.
8. Freeze the source snapshot and manifest entry.

### 6.4 Internal testing storage policy

Copyright and source-licensing review is deferred during the internal evaluation phase and must not block construction of the pilot benchmark. The evaluation needs complete, frozen job descriptions so runs remain reproducible after a posting changes or disappears.

For internal testing:

- Retain the complete fetched job description and relevant rendered source artifacts.
- Store each immutable snapshot with its source URL, capture timestamp, and content hashes.
- Permit snapshots to be stored with the evaluation fixtures or in internal evaluation storage, whichever makes local and automated testing reliable.
- Do not replace a source snapshot with a later version; create a new immutable snapshot.
- Do not depend on the original URL remaining active during replay.
- Keep the benchmark for internal development and testing rather than publishing or redistributing it as a standalone job-description dataset.

Before production use or external distribution, complete a separate copyright, source-terms, licensing, and retention review. Any resulting production restriction applies to production collection and storage policy; it should not retroactively make the internal pilot non-reproducible.

## 7. Candidate Fixture Set

The ten-job pilot should use approximately 8–12 consented, de-identified, or carefully constructed synthetic resumes. The fixtures should cover:

- Entry/junior, mid, senior, staff/principal, and management contexts.
- Software, hardware/embedded, product, TPM, and leadership backgrounds.
- Direct matches, adjacent backgrounds, clear mismatches, and insufficient evidence.
- Strong resumes and sparse or ambiguous resumes.
- Multiple plausible role-family/track profiles in one resume.
- Skill-list claims without demonstrated usage.
- Contradictory or incomplete dates and qualifications.

Candidate fixtures remain private when based on real people. Names, contact details, addresses, photos, and social links are excluded from evaluation artifacts.

## 8. Pair Construction

Do not evaluate all pairs randomly. Construct pairs intentionally.

For the ten-job pilot, create 30–50 resume/job pairs:

- Approximately one clearly strong pair per job.
- One plausible but incomplete or adjacent pair per job.
- One deliberate mismatch per job.
- Additional pairs for application constraints, alternative skills, ambiguous requirements, and career-track selection.

Pair labels must be assigned before observing the system result when practical. This reduces confirmation bias.

The pilot's pre-run numerical expectations are frozen in
`MATCHING_EXPECTED_SCORE_MATRIX.md` and the machine-readable release
`server/app/modules/evaluation/expected_score_matrix.v1.json`. Every candidate/job combination has
an `initial_expected_score` and tolerance range. A later run records `agent_score` separately, and a
later independent review records `human_score`; neither value overwrites the initial matrix.

The pilot is diagnostic, not statistically conclusive. Percentages from ten jobs must always be reported with raw counts and examples.

## 9. Golden Annotation Contract

### 9.1 Candidate Profile annotations

Reviewers label:

- Evidence-backed skills and their claimed/demonstrated strength.
- Experience, projects, education, certifications, and publications.
- Valid evidence spans for each fact.
- Reasonable role family, track, level, and confidence band.
- Unsupported or hallucinated facts.
- Important omissions.

### 9.2 Job Profile annotations

Reviewers label:

- Atomic requirements.
- Required or optional importance.
- Scoring dimension.
- Acceptable evidence contexts.
- Minimum-years requirement when explicit.
- Explicit alternatives and approved policy alternatives.
- Role family, track, target level, and acceptable level range.
- Application constraints and whether unknown values are preserved for deterministic eligibility evaluation.
- Duplicate and boilerplate content.
- Exact supporting source spans.

### 9.3 Qualification annotations

For every requirement, reviewers label:

- Status: `met`, `met_by_alternative`, `partially_met`, or `not_demonstrated`.
- Supporting candidate evidence spans.
- Approved alternative used, if any.
- Material missing evidence.
- Short adjudicated reason.

The golden set contains no numerical match score during early evaluation.

### 9.4 Review process

- Two qualified reviewers independently label every pair intended for a rollout gate.
- Pilot labeling may begin with one reviewer, but all positive qualification statuses and all
  material application-constraint/eligibility decisions require a second review.
- Disagreements are resolved by an adjudicator and retained as disagreement metadata.
- Reviewers see source text and evidence spans, not only model summaries.
- An LLM may assist annotation preparation but cannot be the sole ground truth or adjudicator.

## 10. Evaluation Metrics

### 10.1 Contract and reproducibility

- Strict-schema success rate before and after one allowed retry.
- Evidence-reference identifier validity.
- Exact requirement coverage.
- Cache-hit rate on identical inputs.
- Artifact and policy version completeness.
- Repeated-run change rate on frozen inputs.
- Provider latency, input/output tokens, and cost.

### 10.2 Candidate Profile

- Evidence-supported fact precision and recall.
- Human-rated citation support precision.
- Skill-strength classification agreement.
- Role-family, track, and career-level weighted agreement.
- Unsupported-fact count.
- Material-omission count.

### 10.3 Job Profile

- Atomic requirement precision and recall.
- Required/optional classification precision, recall, and F1.
- Requirement-duplicate rate after cleanup.
- Scoring-dimension agreement.
- Application-constraint false-positive and false-negative counts.
- Role-family, track, and level agreement.
- Application-constraint accuracy and unknown preservation.

### 10.4 Qualification Assessment

- Qualification-status confusion matrix.
- Weighted Cohen's kappa against adjudicated labels.
- Positive-status precision.
- Human-rated evidence support precision for `met`, `met_by_alternative`, and `partially_met`.
- Approved-alternative accuracy.
- `not_demonstrated` error rate and material missing-evidence quality.
- Severe application-constraint or eligibility-gate errors.

The primary early metric is:

> Among requirements classified as `met`, `met_by_alternative`, or `partially_met`, how often does the cited resume evidence genuinely support the classification?

## 11. Pilot Interpretation and Gates

The ten-job pilot is used to find structural failures, prompt defects, taxonomy gaps, and annotation problems. It is not large enough to approve customer rollout or calibrate Phase 5 weights.

Minimum pilot expectations:

- 100% valid evidence-reference identifiers.
- 100% exact requirement coverage.
- Zero weight inflation from duplicate job text.
- Zero model-generated scores or recommendations.
- Zero cross-tenant access failures.
- Zero unsupported employer application-constraint positives.
- Every positive-status citation manually reviewable.
- Every failure classified into a stable error taxonomy.

The architecture's numerical rollout gates remain controlling for larger sets, including at least 200 independently reviewed pairs for limited rollout and 1,000 pairs or an approved statistical equivalent for general rollout.

Phase 5 may begin after the pilot shows that artifact boundaries are sound and no architecture-level defect remains. Phase 5 calibration and public ranking decisions must wait for the larger stratified evaluation.

## 12. Bias and Invariance Checks

Using prominent employers creates a risk that company reputation influences extraction or seniority inference. Add paired invariance tests:

- Replace the employer name in an otherwise identical job description; requirements and qualification outcomes should remain unchanged.
- Replace candidate employer names with neutral placeholders; Candidate Profile level and Qualification Assessment should remain materially unchanged unless the text itself changes relevant evidence.
- Reorder duplicated requirements; deduplication and qualification ownership should remain stable.
- Reorder equivalent resume sections; evidence IDs may change, but supported facts and statuses should remain stable.
- Compare clean and boilerplate-heavy copies of the same job.

Company identity may populate the Job Profile's company field. It must not create qualification evidence, weights, or favorable status.

## 13. Evaluation Run Manifest

Every run should record:

```json
{
  "evaluation_run_id": "eval_...",
  "benchmark_release": "matching-benchmark.v1",
  "candidate_fixture_release": "candidate-fixtures.v1",
  "job_fixture_release": "matching-benchmark-jobs.v1",
  "candidate_prompt_version": "candidate-extract.v1",
  "job_prompt_version": "job-extract.v1",
  "qualification_prompt_version": "qualification-match.v2",
  "schema_versions": {},
  "taxonomy_version": "matching-taxonomy.v1",
  "selection_policy_version": "career-selection-policy.v1",
  "qualification_policy_version": "qualification-policy.v1",
  "model_ids": {},
  "provider_configuration_hash": "sha256:...",
  "started_at": "...",
  "completed_at": "..."
}
```

Reports compare two runs only when their benchmark and candidate releases are identical. Any changed prompt, schema, policy, model, or provider setting is displayed explicitly.

## 14. Proposed Evaluation Tooling

The evaluation implementation should provide:

- A benchmark manifest schema and validator.
- A safe collection command that calls the existing import service.
- An admission report showing missing coverage slots and employer imbalance.
- Annotation JSON Schemas for Candidate Profile, Job Profile, and Qualification Assessment labels.
- A runner that executes frozen fixtures without performing a new job search.
- A scorer that calculates stage-specific metrics and confusion matrices.
- A disagreement report with source and evidence excerpts.
- A comparison report for two prompt/model/policy runs.
- Export to JSON and Markdown; CSV may be added for manual analysis.
- Redaction checks preventing private resume content or complete benchmark inputs from entering routine logs or unintended public artifacts.
- An internal tester workbench described in Section 15.

Suggested repository layout:

```text
server/evals/matching_v2/
  schemas/
  manifests/
  synthetic_fixtures/
  annotations/
  runners/
  reports/
```

Server-managed frozen job snapshots may be stored directly with the internal evaluation data or fixtures. Private candidate sources and annotations remain access-controlled and may be addressed by opaque storage references in the manifest.

## 15. Internal Tester Workbench

Evaluation must be usable by a tester without database access, command-line JSON inspection, or a new live job search for every run. Add an internal-only tester workbench backed by the server.

### 15.1 Server-managed benchmark jobs

An authorized tester can:

1. Enter one or more official job URLs.
2. Ask the server to fetch them through the existing secure URL-import and ATS-adapter boundary.
3. Review the fetched title, company, source URL, full job description, source quality, and extraction warnings.
4. Assign the job to one of the benchmark coverage slots.
5. Accept or reject the source for the benchmark.
6. Freeze an accepted immutable snapshot with its content hashes and capture metadata.
7. Generate or reuse its Job Profile.

Fetching and freezing are separate actions. A malformed or incomplete fetch can be rejected without entering the benchmark. Re-fetching an existing URL creates a reviewable new snapshot when its content hash changes; it never overwrites the earlier fixture.

The workbench lists:

- Coverage slots that are filled, missing, or awaiting review.
- Employer and role-distribution balance.
- Active and historical job snapshots.
- Source quality, extraction status, and errors.
- Job Profile cache hits and the exact version used by each evaluation run.

### 15.2 Resume fixture loading

An authorized tester can load a resume by:

- Uploading a supported resume document.
- Pasting resume text.
- Selecting an existing consented or synthetic candidate fixture.

The tester assigns an opaque fixture label and coverage metadata such as intended role family, track, career stage, and resume-quality slice. Personal names and contact information are not required for evaluation and should be excluded or redacted.

Every accepted resume fixture creates an immutable source snapshot and a Candidate Profile version. Uploading a revision creates another fixture or version; it does not replace prior evaluation inputs.

### 15.3 Candidate Profile inspection

The candidate view displays the source and extracted artifact together:

- Original uploaded resume rendering when available.
- Extracted and canonical resume text.
- Candidate Profile headline, summary, skills, experience, projects, education, certifications, and publications.
- All inferred career profiles with role family, track, level, confidence, and dimension signals.
- Recommended and effective primary career selections.
- Extraction warnings, completeness, model, prompt, schema, taxonomy, and source hashes.

Selecting any extracted fact or career-profile evidence reference highlights the corresponding resume excerpt. The tester can mark the fact as supported, partially supported, unsupported, missing, or ambiguous and add an annotation without modifying the immutable Candidate Profile.

### 15.4 Job Profile inspection

The job view displays the frozen source and Job Profile together:

- Original fetched job description and source URL.
- Canonical job text and retained source spans.
- Title, company, location, employment type, compensation, and application constraints.
- Role family, adjacent role families, track, target level, acceptable level range, confidence, and provenance.
- Normal and hard requirements in a table showing importance, scoring dimension, acceptable evidence contexts, minimum years, alternatives, and source references.
- Responsibilities, cleanup counts, omitted-input warnings, and generation versions.

Selecting a requirement or extracted field highlights its supporting job-description excerpt. Duplicate source spans should be visibly identified as ignored rather than silently disappearing.

### 15.5 Detailed matching output

The tester selects one Candidate Profile version, one exact career-selection revision, and one Job Profile version, then runs Qualification Assessment.

The detailed result view displays:

- Candidate, resume, job, and Job Profile identities and versions.
- Deterministically selected career profile and selection reason code.
- A row for every Job Profile requirement.
- Qualification status and confidence.
- Model reason and material missing evidence.
- Explicit or approved policy alternative used.
- Candidate evidence references with clickable resume highlighting.
- Job source references with clickable job-description highlighting.
- Input completeness and any omitted-evidence warning.
- Provider execution reference, cache status, latency, token usage, and all material prompt/schema/policy/model versions.

The three-stage workbench calls this output a **Qualification Assessment**, not a score or
recommendation. Although Phase 5 now exists as a separate deterministic layer, this view must not
synthesize a hidden percentage, 0-10 score, ranking, or match label from status counts.

The tester can filter the requirement table by status, importance, or dimension. A compact summary
may show counts such as `met: 4` and `not_demonstrated: 2`, but counts must not be presented as a
calibrated score.

### 15.6 Evidence navigation

Evidence navigation is central to the workbench:

```text
Resume source <-> Candidate Profile fact <-> Qualification row <-> Job Profile requirement <-> Job source
```

From any qualification row, a tester can open both sides at once:

- Left: the cited resume excerpt in its surrounding source context.
- Center: status, confidence, reason, alternative, and missing evidence.
- Right: the job requirement and its surrounding job-description context.

Invalid, missing, or cross-source references are displayed as evaluation failures, not omitted from the interface.

### 15.7 Annotation and adjudication

The workbench supports annotations without changing generated artifacts:

- Candidate fact correctness and missing facts.
- Job requirement atomicity, completeness, importance, dimension, and ownership.
- Qualification status and evidence support.
- Alternative-policy correctness.
- Role-family, track, and level corrections.
- Severity and stable error-taxonomy code.
- Reviewer identity, timestamp, comments, and confidence.

Two independent reviews can be compared, with disagreements placed into an adjudication queue. The adjudicated label becomes the golden value for metrics while the original reviews remain available.

### 15.8 Run comparison

A tester can replay the same frozen candidate/job pairs with a new prompt, schema, validator, taxonomy, policy, or model version and compare runs side by side.

The comparison view highlights:

- Added, removed, merged, or changed Candidate Profile facts.
- Added, removed, split, merged, or reclassified job requirements.
- Changed career-context selection.
- Changed qualification statuses, confidence, evidence, alternatives, reasons, and missing evidence.
- Improvements and regressions against adjudicated labels.
- Changes in latency, tokens, cost, validation retries, and cache behavior.

The server must never silently compare different source snapshots as though only the model changed.

### 15.9 Suggested internal API boundary

The exact API may change during implementation, but the workbench needs internal equivalents of:

```http
POST /api/v1/internal/evaluation/job-snapshots/import
GET  /api/v1/internal/evaluation/job-snapshots
POST /api/v1/internal/evaluation/job-snapshots/{snapshot_id}/accept
POST /api/v1/internal/evaluation/job-snapshots/{snapshot_id}/profile
POST /api/v1/internal/evaluation/job-profiles/{job_profile_id}/reviews
POST /api/v1/internal/evaluation/resume-fixtures
GET  /api/v1/internal/evaluation/resume-fixtures
GET  /api/v1/internal/evaluation/candidate-sources
POST /api/v1/internal/evaluation/candidate-sources/{resume_profile_id}/profile
POST /api/v1/internal/evaluation/candidate-profiles/{candidate_profile_id}/reviews
POST /api/v1/internal/evaluation/runs
GET  /api/v1/internal/evaluation/runs/{run_id}
POST /api/v1/internal/evaluation/runs/{run_id}/annotations
GET  /api/v1/internal/evaluation/comparisons
```

Evaluation endpoints are disabled by default, restricted to internal-super or evaluator roles, and excluded from ordinary customer navigation. They reuse Candidate Profile, Job Profile, Qualification Assessment, document extraction, and secure job-import services rather than creating parallel matching logic.

### 15.10 Tester workflow

A normal pilot session is:

1. Open the benchmark dashboard and review coverage gaps.
2. Import and freeze an official job posting, or select an existing frozen job.
3. Upload or select a resume fixture.
4. Inspect the Candidate Profile beside the resume.
5. Inspect the Job Profile beside the job description.
6. Run Qualification Assessment for that exact pair.
7. Inspect every requirement with candidate and job evidence visible.
8. Record annotations and submit the review.
9. Compare with another reviewer or an earlier system run.

### 15.11 Workbench acceptance criteria

- A tester can complete the workflow without shell or direct database access.
- The lab has separate Candidate Profile, Job Profile, and Matching sections.
- Candidate Profile extraction/review and Job Profile extraction/review run independently and do
  not invoke Qualification Assessment.
- A job is fetched once and replayed from its frozen snapshot for later runs.
- Resume, Candidate Profile, job description, Job Profile, and detailed Qualification Assessment are accessible from one evaluation run.
- Every evidence reference navigates to the correct immutable source and excerpt.
- The workbench clearly distinguishes raw source, generated artifact, human annotation, and adjudicated truth.
- A rerun always shows whether it reused or changed each input and policy version.
- No Phase 5 score or recommendation appears before the deterministic scoring phase is implemented.
- Evaluation routes remain inaccessible when the internal evaluation feature is disabled.

Implementation checkpoint (2026-08-16): the mobile tester lab is split into three explicit
sections. Candidate Profile review lists account-owned real and synthetic resume sources, displays
canonical resume text beside the extracted artifact, and persists an overall human score and
rationale. Job Profile review does the same for accepted frozen job snapshots. Matching retains the
paired three-stage run and its independent match review. Artifact reviews are append-only and do
not mutate generated Candidate or Job Profiles.

## 16. Delivery Stages

Implementation checkpoint (2026-08-15): the first E0 vertical slice is operational behind
`DALIJOB_MATCHING_V2_EVALUATION_ENABLED`. It includes immutable server-fetched job snapshots,
resume-PDF loading through the existing managed import path, persisted three-stage runs, run
history, exact source/profile inspection, and evidence navigation in an admin-only web
workbench at `/evaluation`. The API intentionally records `score_generated: false`.
At that checkpoint, annotation/adjudication, benchmark manifests, aggregate metrics, run
comparison, corpus export, and leakage checks remained.

Second implementation checkpoint (2026-08-15): run manifests, append-only independent and
adjudicated reviewer annotations, per-run and aggregate contract metrics, qualification confusion
matrices, the primary positive-evidence-support metric, and source-safe run comparison are now
implemented in the internal API and `/evaluation` workbench. Comparison explicitly reports changed
candidate or job sources as incompatible. At that checkpoint, corpus export, fact-level review,
disagreement queues, admission reporting, and automated privacy checks remained.

E0 completion checkpoint (2026-08-15): job capture and benchmark admission are separate actions;
the ten pilot coverage slots and balancing violations are visible; only accepted snapshots can run;
Candidate Profile facts, Job Profile facts, and qualification rows are independently reviewable;
cross-reviewer disagreements enter an adjudication queue; JSON and Markdown corpus exports redact
candidate contact channels; and automated tests verify that private candidate data and complete job
inputs do not enter logs or exported candidate sources. E0 is complete. E1 is the human/data task of
selecting the ten real jobs, loading 8–12 consented or synthetic candidate fixtures, constructing
intentional pairs, and completing reviews through this workbench.

### E0: Evaluation foundation

- Define manifest and annotation schemas. **Complete.**
- Implement frozen-fixture runner and version capture. **Initial vertical slice complete.**
- Implement evidence, coverage, and contract metrics. **Initial per-run and aggregate metrics complete.**
- Add redaction and benchmark-leakage tests. **Complete.**
- Add the workbench shell, server-managed job import, resume loading, and source/profile inspection. **Complete.**

Exit: **Passed.** A synthetic candidate/job pair runs reproducibly without a live search, supports
all three annotation stages, reports metrics, compares safely, and exports with candidate redaction.

### E1: Ten-job curated pilot

Collection checkpoint (2026-08-15): ten active postings were fetched from employer-controlled
career pages, reviewed, accepted, and frozen in the local evaluation corpus. The admitted set fills
every coverage slot with Amazon (2), Google (2), Apple (2), NVIDIA (2), Microsoft (1), and
Cloudflare (1), with no balance violations and no aggregator posting. Future discovery starts from
the machine-readable employer source registry at
`server/app/modules/evaluation/company_job_sources.json`.

Candidate-and-pair checkpoint (2026-08-15): `candidate-fixtures.synthetic.v1` defines eleven
source-controlled synthetic resumes with no personal or contact data. They cover entry, mid,
senior, manager, and principal contexts across software, infrastructure, mobile, ML, hardware,
firmware, product, TPM, and leadership. All eleven are loaded into the local tester workbench.
`matching-evaluation-pairs.v1` freezes thirty expectations before matcher execution: one strong,
one adjacent or incomplete, and one mismatch candidate for each of the ten job slots.

Manual-selection checkpoint (2026-08-15): the `/evaluation` workbench exposes all eleven candidate
fixtures, ten accepted jobs, and thirty suggested diagnostic pairs. A tester can independently
select a candidate or job, inspect the exact structured resume and frozen job description, or use a
suggested pair to fill both selectors. Selection never starts provider work; the three-stage matcher
runs only after the tester explicitly chooses **Run evaluation now**.

Initial-score checkpoint (2026-08-15): all 110 candidate/job combinations have a frozen 0–100
initial expected score and reviewer-tolerance range. Agent and human scores remain intentionally
empty until their respective run and blind-review stages.

First agent-sample checkpoint (2026-08-15): two pairs from each of the five initial score bands were
run once on US3 without exposing evaluation labels. Two of ten runs completed; eight were rejected
by strict Job Profile or Qualification Assessment validation, and none returned a numeric score.
The immutable sample and observed results are recorded in `MATCHING_AGENT_SAMPLE_RESULTS.md`.

- Fill and review the ten coverage slots. **Complete.**
- Create 8–12 candidate fixtures and 30–50 intentional pairs. **Complete: 11 fixtures and 30 pairs.**
- Complete initial annotations and adjudication.
- Run the current three-step matcher and classify every disagreement. **Automated replay complete:
  `qualification-match.v2` completed 27/30; all three failures were Stage 3 semantic-contract
  failures. Human disagreement classification remains.**
- Complete the pilot through the tester workbench without direct database access.

Exit: the pilot expectations in Section 11 pass or every failure has an agreed remediation owner.

### E2: Prompt and validator iteration

First iteration checkpoint (2026-08-16): `qualification-match.v3` adds one bounded, complete-response
repair attempt with sanitized semantic-validation feedback. The identical 30-pair replay completed
28/30 (93.3%); six completed pairs used repair, and all 28 completed runs passed evidence-reference,
requirement-coverage, manifest, and no-score structural gates. The two residual failures were safely
rejected in Stage 3. The internal pilot accepts a low bounded failure rate and routes terminal failures
to a separate retry/evaluator process instead of pursuing a 100% model completion rate. Full results
and the initial >=90% reliability policy are in `MATCHING_E1_E2_REPLAY_RESULTS.md`.

Human-QA handoff checkpoint (2026-08-16): the 28 structurally valid v3 runs are frozen as
`matching-human-qa.v1`; the two execution failures are excluded from correctness metrics and remain in
the failure report. Two independently shuffled reviewer packets contain only opaque run IDs and direct
blind-review links. The `/evaluation?review=blind&run_id=...` mode hides diagnostic expectations,
aggregate outcomes, comparisons, prior annotations, and adjudication outcomes, and forces saved reviews
to `independent`. US3 verification found all 28 canonical runs with the required benchmark and
`qualification-match.v3`, with zero pre-existing annotations. Reviewer and adjudicator account assignment
is the remaining prerequisite for G3.

Overall-score checkpoint (2026-08-16): each persisted evaluation run now exposes Candidate Profile
versus Job Profile and Qualification Assessment with a human 0-100 match-review form. Independent and
adjudicated scores are stored separately in `matching_evaluation_match_reviews`, with reviewer identity,
confidence, rationale, recommendation band, and timestamp. `POST
/api/v1/internal/evaluation/runs/{run_id}/match-reviews` accepts the review. Blind reads expose only the
current reviewer's records; normal evaluator reads expose the two independent scores and the adjudicated
golden score. Adjudication is rejected until two distinct reviewers exist and cannot be performed by
either reviewer.

- Change one versioned component at a time. **Complete for the v3 repair iteration.**
- Replay the identical benchmark. **Complete: 30 frozen pairs.**
- Compare improvements and regressions by role, track, level, and evidence type.
- Promote a new component version only when it improves the target failure class without severe regressions.
  **v3 advanced to internal human QA/super testing; it is not a QA pass or rollout approval.**

Exit: Candidate Profile, Job Profile, and Qualification Assessment are stable enough to begin Phase 5 implementation.

### E3: One-hundred-job expansion

Foundation checkpoint (2026-08-16): the machine-readable employer registry is now the shared
source of truth for manual imports and the future crawling service. It contains 24 employers and
eight ATS families. Sixteen companies were added to the pilot set using current S&P 500 and/or
Nasdaq-100 membership as a selection aid: Broadcom, AMD, Micron, Intel, Cisco, Qualcomm, Applied
Materials, Lam Research, KLA, Texas Instruments, Palo Alto Networks, CrowdStrike, Palantir,
Workday, Intuit, and ServiceNow. Index membership dates and official index references are stored
with the registry and must be refreshed for every new benchmark release; membership is not treated
as a permanent company property.

The source table remains at
`server/app/modules/evaluation/company_job_sources.json`. Each company row now records ticker,
index membership, industry focus, official career/discovery URLs, allowed detail hosts and path
prefixes, ATS family, and E3 eligibility. URL-to-company attribution reads this registry instead of
using hard-coded company rules. A future crawler must use these allowlists and independently honor
the site's current robots rules, terms, and rate limits.

`server/app/modules/evaluation/e3_collection_manifest.v1.json` freezes the first expansion target:

- 100 accepted job snapshots from at least 20 employers, with no more than six jobs per employer.
- Eleven role-family slices spanning software, ML/data, security/networking, silicon/hardware,
  firmware, product, TPM, engineering management, and principal/architecture roles.
- Five level bands from entry/junior through management and leadership.
- At least six ATS families and three description-quality bands.
- Official employer pages or employer-controlled ATS pages only, exact detail URLs, complete frozen
  descriptions, manual acceptance, and no duplicate description hashes.

#### E3 collection and Job Profile extraction process

Use the following lifecycle for every newly discovered job. Collection and model extraction remain
separate so a fetch or parsing defect cannot silently become benchmark truth.

1. Discover a live detail URL from a company entry in the source registry.
2. Import it through the evaluation workbench. The server verifies the URL against the registry,
   fetches the employer detail page, and freezes the exact description as a draft snapshot in
   `matching-benchmark-jobs.e3.v1`.
3. A tester inspects the title, company, exact URL, complete description, role-family slot, level,
   and description-quality band. E3 imports require both classification fields and persist them with
   the snapshot metadata. The E3 admission report measures all manifest quotas rather than applying
   the ten-job pilot limits. Accept only complete, correctly attributed, non-duplicate jobs.
4. Validate all accepted inputs without calling the model or changing the database:

   ```powershell
   python scripts/extract_new_job_profiles.py `
     -c <ProcessConfig.ini> `
     --benchmark-release matching-benchmark-jobs.e3.v1 `
     --dry-run `
     --output artifacts/e3-job-profile-dry-run.json
   ```

5. Extract and persist Job Profiles for the accepted snapshots:

   ```powershell
   python scripts/extract_new_job_profiles.py `
     -c <ProcessConfig.ini> `
     --benchmark-release matching-benchmark-jobs.e3.v1 `
     --output artifacts/e3-job-profile-extraction.json
   ```

6. Review the batch report and inspect each persisted source, Job Profile, and job description in
   the evaluation workbench before admitting it to qualification-pair evaluation. Failed rows do
   not abort or commit other rows; fix or reject their source snapshots and rerun only those rows
   with `--snapshot-id <ejs_id>`.

The persistence command uses the same `job-extract.v3` prompt, strict response schema, semantic
validation/repair, deterministic policy assignment, and versioned cache identity as the application
API. It commits each successful job independently. Re-running an unchanged job and model version
returns the cached Job Profile and does not spend another provider call. Its JSON report records
created, cached, ready, and failed counts plus artifact identifiers and extraction versions. The
existing `scripts/evaluate_job_profile_extraction.py` remains the non-persisting prompt-analysis
tool; it is not the E3 ingestion path.

- Expand employer, role, level, ATS, and description-quality coverage. **Collection manifest and
  24-company source registry complete; collecting 100 jobs remains.**
- Persist validated Job Profiles for accepted new snapshots. **Repeatable batch process complete;
  execution awaits accepted E3 jobs.**
- Increase independently reviewed qualification pairs toward the 200-pair limited-rollout minimum.
- Add stratified confidence intervals and slice-level regression gates.

Exit: upstream artifacts satisfy the applicable architecture evaluation gates on the expanded set.

### E4: Phase 5 extension

Architecture-fixture checkpoint (2026-08-16): the Phase 5 evaluation harness now calls the same
pure `score.v1` function used by Match Result creation. The versioned fixture at
`server/app/modules/evaluation/phase5_policy_cases.v1.json` covers deterministic replay,
preference blending and incompleteness, eligibility outcomes, employer/user gate precedence,
the 0.80 qualification-coverage boundary, provisional levels, unsupported scoring policies, and
every recommendation label. Boundary tests independently exercise every exact recommendation
threshold and the 0.60 preference-coverage threshold.

The fixture also defines independently ordered candidate lists plus a final adjudicated order and
0-100 human-style scores. `phase5_ranking_annotation.schema.json` is the contract for replacing
the synthetic architecture ordering with real reviewer data. Human sets require two uniquely
identified independent reviewer rankings before they can be marked `human_adjudicated`; tied
candidates are represented by equal adjudicated ranks.

Run the harness with:

```powershell
python scripts/evaluate_phase5_scoring.py `
  --fixture server/app/modules/evaluation/phase5_policy_cases.v1.json `
  --output artifacts/phase5-evaluation-report.json
```

The report contains:

- Canonical byte-for-byte replay status for every deterministic score result.
- Policy-conformance results by preferences, eligibility, hard gates, coverage, level policy,
  policy approval, preference blending, and recommendation labels.
- The final human/adjudicated order and deterministic predicted order for each job group.
- Pairwise ordering accuracy and mean Spearman rank correlation, including average ranks for ties.
- Calibration sample count, mean absolute error, and root mean squared error against 0-100 human
  scores.
- Separate architecture-fixture gates and `rollout_decision_eligible`. Synthetic rankings can pass
  regression checks but can never make the report eligible for a rollout decision.

- Add deterministic score reproduction tests. **Complete for architecture and policy fixtures.**
- Add adjudicated pairwise ranking and ordered candidate lists. **Schema, two-reviewer contract,
  adjudication representation, and metric implementation complete; real human rankings remain.**
- Measure score calibration and Spearman rank correlation. **Complete in the harness; rollout
  measurement awaits human-adjudicated E3 pairs.**
- Test preferences, eligibility, hard gates, coverage thresholds, and recommendation labels
  separately. **Complete.**

This stage extends the same frozen benchmark; it does not replace it.

## 17. Initial Decisions and Defaults

Recommended defaults:

- Start with ten frozen jobs and 30–50 pairs.
- Use official sources only.
- Use the versioned company-source registry for pilot and E3 employer selection.
- Limit any one employer to two pilot jobs.
- Retain full frozen job text for reproducible internal testing; decide the production storage boundary during the later production review.
- Use two human reviewers for positive statuses and material application-constraint decisions.
- Treat the pilot as diagnostic; do not tune numerical scoring weights from it.
- Keep Phase 5 architecture fixtures separate from rollout calibration until human-reviewed E3 data exists.

## 18. Remaining Decisions

Resolved for internal evaluation:

- Employer priorities and official domains are versioned in `company_job_sources.json`.
- Hardware coverage includes both silicon/electrical design and embedded/firmware roles.
- Frozen jobs and annotations use internal database storage; de-identified synthetic fixtures and
  machine-readable manifests may remain source controlled.

Still open:

- What production retention and source-licensing policy replaces unrestricted internal-testing
  retention before customer rollout?
- Who are the two qualified domain reviewers and the adjudicator for E1 and E3?
- Which real, consented resumes are available, and which remaining coverage gaps should continue to
  use synthetic fixtures?

The controlling definition of execution failure, structural validity, human QA pass, rollout gates,
and residual-failure handling is `MATCHING_QA_GATE.md`.

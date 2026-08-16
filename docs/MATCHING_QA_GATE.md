# Matching QA Process and Gates

Status: active internal QA contract
Applies to: Candidate Profile, Job Profile, Qualification Assessment, and Phase 5 scoring

## 1. Pass and failure vocabulary

A model call is not a matching-quality pass merely because it returns valid JSON. Every evaluated pair
has separate states:

| State | Meaning |
| --- | --- |
| `execution_failed` | The provider, schema validation, or semantic validation did not produce a usable complete artifact after the bounded retry. |
| `structurally_valid` | The complete artifact passed schema, semantic, evidence-reference, coverage, ownership, and version checks. Quality is not yet judged. |
| `review_pending` | A structurally valid artifact awaits independent human labels. |
| `adjudication_pending` | Two reviewers disagree on one or more material labels. |
| `qa_pass` | Adjudicated labels exist and the release meets every applicable aggregate and slice gate. |
| `qa_fail` | Adjudicated results miss a gate or contain a rollout-blocking severe error. |

The application must never display `execution_failed` as a low match score. A structurally valid run
must never be described as `qa_pass` before human review and adjudication are complete.

## 2. Gate sequence

### G0: Frozen inputs and provenance

Automated admission verifies immutable candidate/job sources, benchmark and fixture releases, exact
content hashes, prompt/schema/policy/model versions, and absence of evaluation-label leakage.

Failure blocks the run. Changing a source creates a new fixture version; it is never compared as a
model-only change.

### G1: Execution reliability

The primary call may receive at most one bounded complete-response repair. A terminal failure is safe
only when no partial assessment or score is persisted or exposed.

- Ten-job diagnostic pilot: at least 90% completion is sufficient to proceed to human QA when every
  residual failure is classified and queued.
- Limited rollout: use the stricter Section 28 gate in `3-step_matching_v2.md` (currently at least
  99.5% strict-schema success after at most one retry) unless product owners approve a revised SLO.
- Provider/validation failures are measured separately from human correctness failures.

### G2: Structural safety

Every completed run must pass all applicable deterministic checks:

- valid evidence and source references;
- every job requirement assessed exactly once;
- no duplicate-weight inflation or cross-owner constraint;
- complete version manifest;
- no model-generated score, ranking, gate, or recommendation;
- zero cross-tenant access failure.

The gate is 100%. A failed check changes the run to `execution_failed`; it is not eligible for review or
scoring.

### G3: Independent review and adjudication

Two qualified reviewers independently label every pair used for a rollout decision. They review:

- Candidate Profile fact support, missing facts, role family, track, and level;
- Job Profile atomic requirements, completeness, required/optional importance, dimension, alternatives,
  application-constraint ownership, role family, track, and level;
- Qualification status, candidate evidence support, alternative correctness, reason, and material gaps.

Reviewers do not see initial expected scores or another reviewer's labels. Every disagreement enters the
workbench adjudication queue. Only the adjudicated label is golden truth; both original reviews remain
immutable.

### G4: Human-quality metrics

The scorer runs only after G3 is complete. Limited-rollout thresholds are the controlling table in
Section 28 of `3-step_matching_v2.md`, including:

- human-rated evidence-support precision at least 95%;
- atomic requirement precision at least 90% and recall at least 85%;
- required/optional classification F1 at least 90%;
- qualification-status weighted Cohen's kappa at least 0.75;
- career level/track weighted agreement at least 0.75;
- employer application-constraint false-positive rate at most 1% and false-negative rate at most 2%;
- Phase 5 Spearman rank correlation at least 0.70 when ranking is in scope.

The 30-pair pilot is diagnostic and cannot satisfy a rollout gate. Limited rollout requires at least 200
independently reviewed stratified pairs; general rollout requires 1,000 or an approved statistical
equivalent.

### G5: Slice and regression gate

Metrics are reported overall and by role family, track, level, candidate quality, job-description quality,
employer/ATS source, and important evidence type. No permitted slice may trail overall evidence-support
precision or status agreement by more than ten percentage points without documented approval. Any severe
application-constraint regression blocks rollout regardless of aggregate results.

A candidate prompt/model/policy release is compared only on identical frozen inputs. It passes regression
review when it improves its target failure class, does not introduce a severe error, and does not cause a
material statistically supported regression in another required metric or slice.

### G6: Operational release gate

Before user rollout, verify latency/token/cost SLOs, deletion and privacy controls, rollback rehearsal,
failure-queue alerts, and safe customer messaging. G6 cannot compensate for a failed human-quality gate.

## 3. Residual failure process

After one repair, a failed pair is handled outside the successful result path:

1. Persist a privacy-safe failure record with stage, stable error code, correlation ID, retry count, and
   prompt/schema/policy/model versions.
2. Continue other jobs independently.
3. Do not create a partial assessment, score, recommendation, or notification.
4. Retry asynchronously only under a newer approved component version or an explicitly authorized
   operator action; do not loop indefinitely against the same version.
5. Group failures by stable code and slice. Alert when the configured rate or repeated-code threshold is
   crossed.
6. Expose protected traces only to authorized evaluators/support staff.

## 4. Gate record and owner

Every candidate release receives a gate record containing benchmark releases, sample counts, component
versions, metric values and confidence intervals, slice results, unresolved failures, reviewer coverage,
adjudicator identity, and a decision of `blocked`, `qa_pass_internal`, `limited_rollout`, or
`general_rollout`.

- Automated checks own G0-G2 and the computations in G4-G6.
- Two independent reviewers and an adjudicator own golden labels in G3.
- The designated product/QA owner signs the rollout decision; the model cannot approve itself.

## 5. Current result

`qualification-match.v3` is `structurally_valid_for_human_qa`, not `qa_pass`:

- G0: passed for the frozen 30-pair benchmark.
- G1: pilot passed at 28/30 (93.3%); two Stage 3 terminal failures were safely rejected.
- G2: passed for all 28 completed runs.
- G3: pending reviewer assignment, independent labels, and adjudication.
- G3 handoff: `matching-human-qa.v1` is verified on US3 with 28 blind-review runs and zero existing
  annotations; two reviewer accounts and one adjudicator account still require assignment.

The US3 workbench now displays Candidate Profile, Job Profile, their source evidence, and Qualification
Assessment together with an overall **Human match review** form. A reviewer submits a validated 0-100
score, confidence, and rationale. Scores are append-only QA records and are never written into model
artifacts. Blind mode returns only the signed-in reviewer's records and forces independent review. The
server requires two distinct independent reviewers before accepting an adjudicated golden score, and the
adjudicator cannot be either reviewer.

Mobile feedback checkpoint (2026-08-16): the normal authenticated match-detail flow now presents the
stored candidate and job snapshots and accepts an editable 0-100 user score with optional rationale.
The endpoint resolves matches through the signed-in user's inbox, so a regular account can only inspect
and score its own profile/job pairing. Admin tester accounts receive an additional **Test lab** tab backed
by the internal evaluation API, with access to loaded candidate fixtures, accepted benchmark jobs, the
three-stage output, and independent review submission. The tester surface is absent for regular users.

- G4-G6: not eligible for a rollout decision yet.

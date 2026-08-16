# Matching E1/E2 Replay Results

Date: 2026-08-16
Model: `gpt-5.6-luna`
Benchmark: `matching-benchmark-jobs.v1`
Pairs: `matching-evaluation-pairs.v1` (30 frozen pairs)

## Outcome

The E1 baseline completed 27 of 30 pairs (90.0%) with `qualification-match.v2`. All three terminal
failures occurred in Stage 3 Qualification Assessment semantic validation. Candidate Profile and Job
Profile extraction completed; there were no provider, transport, or Stage 2 failures.

The E2 candidate added one bounded, complete-response repair attempt and versioned the changed prompt
contract as `qualification-match.v3`. Its full replay completed 28 of 30 pairs (93.3%). Six successful
runs used the repair path. Every completed run passed all four structural contract checks:

| Contract | Passed | Total |
| --- | ---: | ---: |
| Evidence-reference validity | 28 | 28 |
| Exact requirement coverage | 28 | 28 |
| Manifest version completeness | 28 | 28 |
| No Phase 5 score in three-stage output | 28 | 28 |

The three v2 failures all completed under v3. The two remaining v3 failures were:

| Pair | Expected slice | Terminal Stage 3 validation error |
| --- | --- | --- |
| `pair_infrastructure_mismatch` | mismatch | Requirement IDs were not returned exactly once after repair. |
| `pair_mobile_adjacent` | adjacent/incomplete | Alternative references remained on a non-alternative status after repair. |

These are safe terminal failures: the server rejected the complete response and did not persist or
expose a partial Qualification Assessment.

## Pilot reliability policy

The evaluation does not require a 100% model completion rate. The initial internal gate is:

- at least 90% of frozen pairs complete after at most one repair;
- 100% of completed runs pass structural contract checks;
- no invalid or partial assessment is exposed as a match result;
- every terminal failure has a stable stage, code, correlation ID, prompt/model version, and retry count;
- overall and slice failure rates are monitored, with investigation required when the overall rate
  exceeds 10% or one failure class repeats often enough to indicate a systematic defect.

The 28/30 v3 replay passes the completion and structural portions of this internal pilot gate. It does
not establish matching quality: independent human annotations and adjudication are still required.
Initial expected 0-100 scores are not compared with this output because the three-stage pipeline
intentionally produces no numeric score.

## Separate failure-handling path

After the primary Stage 3 attempt and one repair:

1. Reject an invalid complete response; never construct a partial assessment or score.
2. Persist a privacy-safe failure record outside the successful match-result path with pair/job identity,
   stage, stable error code, correlation ID, model/prompt/schema versions, and retry count.
3. Continue other jobs and pairs independently.
4. Allow a bounded asynchronous retry under a newer approved prompt/model version. Do not loop against
   the same version.
5. Route repeated failures into an evaluator/support queue with protected traces; public responses retain
   only the safe error code and correlation ID.
6. Do not notify the user of a match and do not represent the failed attempt as a low score.

Evaluation replays already continue after individual failures and preserve them in their protected JSON
reports. Persisted application-level failure records and queue processing remain implementation work.

## QA decision

Advance `qualification-match.v3` to human QA and super-account testing. It improves observed completion
from 90.0% to 93.3%, resolves all three original failure cases in targeted replay, bounds model work to
one repair, and introduces no structural-contract failure among completed runs. This is an execution and
structural decision, not a matching-quality pass.

Do not use this result as a public quality or calibration decision. Complete the gates in
`MATCHING_QA_GATE.md`, including blind human review, before judging status correctness, evidence quality,
ranking, score calibration, or rollout readiness.

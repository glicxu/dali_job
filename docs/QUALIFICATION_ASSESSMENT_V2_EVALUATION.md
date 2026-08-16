# Qualification Assessment v2 Evaluation

## Scope

This sanity evaluation isolates Stage 3. It reuses the frozen Job Profile v3 output for the
NVIDIA Senior ASIC Design Engineer snapshot and deterministic synthetic candidate fixtures.
Candidate and Job Profile extraction are not called, results are not persisted, and no numerical
match score or recommendation is generated.

Contract versions:

- `qualification-assessment.v2`
- `qualification-assessment-response.v2`
- `qualification-match.v2`
- `career-selection-policy.v2`
- `qualification-policy.v2`
- `qualification-input.v2`
- `matching-semantic-validator.v4`
- model: `gpt-5.6-luna`

The protected reports contain the complete system prompt, user envelope, strict response schema,
Candidate Profile, candidate evidence, Job Profile requirements, and validated model output:

- `/home/dali-op/dali/releases/dali_job/evaluations/qualification-v2-asic-strong-final-20260815.json`
- `/home/dali-op/dali/releases/dali_job/evaluations/qualification-v2-asic-mismatch-20260815.json`

## Results

| Candidate | Expected relationship | Met | Met by alternative | Partially met | Not demonstrated | Latency |
|---|---|---:|---:|---:|---:|---:|
| Senior ASIC/SoC engineer | Strong | 4 | 2 | 5 | 2 | 16.45 s |
| Senior product manager | Mismatch | 0 | 0 | 2 | 11 | 10.11 s |

The strong fixture demonstrated the core RTL, synthesis/timing, verification-methodology,
problem-solving, education-path, and reset-controller qualifications. Its partial or missing
decisions were conservative and traceable to fixture evidence gaps, including no citable duration
for the stated seven years, no demonstrated Python/Perl scripting work, and incomplete ARM and
microcontroller coverage.

The mismatch fixture did not receive any complete positive decision. Eleven of thirteen
requirements were `not_demonstrated`; the two partial decisions were education adjacency and
general analytical evidence. This is directionally consistent with the predeclared mismatch label.

The first run also exposed that a single alternative-group reference was insufficient because a
requirement may contain multiple independent employer disjunctions. The contract now uses
`alternative_group_refs[]`. When a model returns `met` for a requirement that contains explicit
alternatives, deterministic validation normalizes it to `met_by_alternative` and records the
relevant supplied groups. Invented group or policy references remain invalid.

## Readiness and next evaluation

The schema, evidence boundaries, alternative handling, persistence, and strong-versus-mismatch
direction are ready for the planned matrix evaluation. This two-pair sanity check is not a quality
acceptance result. Next, run the frozen strong, adjacent, and mismatch pairs across the benchmark,
collect human requirement labels, and measure status confusion and evidence precision before
introducing Stage 4 numerical scoring.

One upstream Candidate Profile question should be evaluated separately: resume summaries may state
aggregate experience duration that is not represented in an evidence-bearing structured field.
Stage 3 correctly refuses to infer the missing duration; Candidate Profile extraction may need a
cited duration fact if human review confirms that the summary statement should count.

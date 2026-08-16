# Job Profile Extraction Evaluation

## Baseline

This evaluation isolates Job Profile extraction from Candidate Profile extraction,
qualification assessment, and match scoring.

- Evaluation date: 2026-08-15
- Dataset: 10 accepted jobs from `matching-benchmark-jobs.v1`
- Model: `gpt-5.6-luna`
- Prompt: `job-extract.v2`
- Response schema: `job-extract-response.v2`
- Semantic validator: `matching-semantic-validator.v2`
- Execution mode: direct extraction from frozen job snapshots; no production-profile cache
- Full protected artifact: `/home/dali-op/dali/releases/dali_job/evaluations/job-profile-extraction-v2-20260815.json`

The isolated runner is `scripts/evaluate_job_profile_extraction.py`. Normal application
extraction still persists and reuses validated profiles. The isolated runner deliberately
does not persist Job Profiles so prompt experiments cannot pollute the production cache.

## v3 Implementation Under Evaluation

The baseline below remains the frozen v2 result. `job-extract.v3` now implements the
changes prompted by those findings:

- requirements are only `required` or `optional`; neither is an automatic rejection gate;
- eligibility facts remain solely in `application_constraints`;
- employer alternatives use cited `alternative_groups[].any_of`, and registry policy IDs
  remain deterministic server output;
- the Job Profile taxonomy includes ML engineering, hardware engineering, embedded systems,
  technical program management, and product/program tracks;
- validators reject invalid adjacent families, unsupported employment type, missing explicit
  qualification/responsibility section coverage, and duplicate application constraints;
- compensation is explicitly outside model ownership and is emitted empty until a cited,
  multi-range deterministic representation is implemented;
- mixed substantive/boilerplate spans are retained, known mojibake is repaired, and job-board
  `+N more` location placeholders are removed with a warning;
- v1/v2 registry entries remain immutable, persisted legacy artifacts remain readable through
  an API adapter, and newly generated profiles use v3 cache identities.

Candidate extraction and Qualification Assessment were intentionally unchanged during this
experiment. After the v3 extraction result was frozen, Qualification Assessment v2 was introduced
as a separate versioned change. It now reconstructs structured alternatives from Job Profile v3;
the flattened database value remains only for v1 artifact compatibility.

### v3 frozen-corpus result

The final v3 run used the same ten accepted snapshots and `gpt-5.6-luna`. The protected
artifact is `/home/dali-op/dali/releases/dali_job/evaluations/job-profile-extraction-v3-final-20260815.json`.

| Metric | v2 baseline | v3 final |
|---|---:|---:|
| Strict-schema and semantic-validation successes | 10/10 | 10/10 |
| Repair attempts | 0 | 0 |
| Average provider latency | 15.19 s | 14.76 s |
| Requirements | 114 | 131 |
| Requirement classification | 73 required / 40 preferred / 1 informational | 74 required / 57 optional |
| Model-owned hard constraints | 45 | 0 |
| Responsibilities | 54 | 68 |
| Structured alternative groups | not available | 23 |
| Deterministically assigned policies | 1 | 3 |

Important qualitative changes:

- Google embedded now has five responsibilities instead of zero.
- NVIDIA ASIC now resolves to `hardware_engineering`, senior IC, with 13 qualifications
  including the previously omitted synthesis, timing, scripting, problem-solving, and optional
  items; it also has six responsibilities.
- NVIDIA ML resolves to `machine_learning_engineering`; Apple EPM resolves to
  `technical_program_management`; Google PM uses the product track.
- No profile contains `unknown` or the primary family in adjacent role families.
- Amazon Principal returns exactly the seven qualifications in its explicit required/preferred
  sections rather than promoting responsibility prose into requirements.

One repeated v3 run exposed Amazon summary prose being promoted into requirements. A final
deterministic ownership rule now requires every requirement to cite a qualification section
whenever the source provides such sections. The final artifact passes that rule offline for all
ten jobs. Sources with flattened qualification structure remain supported.

Remaining limitations are now clearer: Microsoft's imported source has lost the boundary between
required and preferred text, source company cleanup still leaves `2100 NVIDIA USA`, compensation
is intentionally deferred, and item-level human correctness still requires blind review. The v3
structural result is therefore ready for human scoring, not automatic production promotion.

## Automated Results

| Metric | Result |
|---|---:|
| Jobs evaluated | 10 |
| Strict-schema and semantic-validation successes | 10/10 |
| Failed extractions | 0 |
| Repair attempts | 0 |
| Jobs with omitted source spans | 0 |
| Average provider latency | 15.19 seconds |
| Extracted requirements | 114 |
| Required / preferred / informational | 73 / 40 / 1 |
| Requirements marked hard | 45 |
| Extracted responsibilities | 54 |
| Explicit-alternative entries | 63 |
| Deterministically assigned policies | 1 |

Structural success is not a sufficient quality result. All ten outputs were valid, but
several valid outputs were incomplete or semantically inconsistent with their source JDs.

## Preliminary Human Review Rubric

Each category is scored from 0 to 4. The maximum is 20.

1. Identity and factual fields: title, company, location, employment, compensation, constraints.
2. Career context: role family, track, target level, and supported confidence.
3. Requirement coverage: required and preferred qualifications are retained completely.
4. Requirement semantics: atomicity, importance, hard-gate ownership, dimensions, and alternatives.
5. Responsibilities and evidence: responsibility coverage, correct separation, and faithful citations.

These are initial reviewer scores, not gold labels. They should be calibrated with a human
reviewer before being used as automated pass/fail targets.

| # | Job | Score | Verdict | Main observations |
|---:|---|---:|---|---|
| 1 | Google — Embedded Systems/Firmware | 13/20 | Partial | Requirements mostly complete and level correct, but all six required items became hard gates, no responsibilities were returned, multi-region compensation was lost, and the location retained `+2 more` UI text. |
| 2 | Microsoft — Principal Engineering Manager | 14/20 | Partial | Role, track, level, location, and employment were strong. Required and preferred pathways were merged into one compound requirement; all preferred qualifications became required; no requirements became hard gates. Source section flattening contributed materially. |
| 3 | NVIDIA — ML Engineer, AI Safety | 13/20 | Partial | Qualification coverage was good, but the taxonomy cannot express machine-learning engineering, compensation was missed, and hard-gate selection was inconsistent. |
| 4 | NVIDIA — Senior ASIC Design Engineer | 9/20 | Fail | Hardware role family was forced to `unknown`. Extraction stopped after six required items and omitted logic synthesis, timing analysis, scripting, problem solving, every preferred qualification, and compensation. No warning reported the incomplete profile. |
| 5 | Apple — Engineering Program Manager, Acoustics | 13/20 | Partial | Requirements were largely complete, but the taxonomy forced a product-management workaround, the primary family was repeated in adjacent families, required items all became hard gates, and compensation values were lost. |
| 6 | Apple — iOS Software Engineer | 17/20 | Pass with minor issues | Strong title cleanup, career context, atomic requirements, importance, and evidence. Required qualifications all became hard gates, and the iOS/macOS alternative was not represented explicitly. |
| 7 | Google — Infrastructure Product Manager | 15/20 | Partial | Strong role, level, and qualification coverage. All required items became hard gates, English boilerplate became a hard requirement, and the explicit USD range was not extracted. |
| 8 | Cloudflare — Senior Distributed Systems Engineer | 16/20 | Pass with issues | Excellent coverage and atomicity. `unknown` appeared as an adjacent family, every required item became a hard gate, and policy assignment succeeded partly because `C/C++` was split by the registry matcher rather than because the complete language choice was evaluated as one group. |
| 9 | Amazon — Principal Software Engineer | 17/20 | Pass with minor issues | Career context and qualification coverage were strong. Every required item became a hard gate, and a responsibility-derived architecture statement became an informational requirement. |
| 10 | Amazon — Transactional Services SDE | 14/20 | Partial | Required and preferred qualifications were concise and complete. `unknown` appeared as an adjacent family, all required items became hard gates, and `full_time` was emitted without supporting source text. |

Preliminary mean: **14.1/20 (70.5%)**. Using an initial threshold of 16, three profiles
pass, six are partial, and one fails. The threshold is provisional until human calibration.

## Cross-Cutting Findings

### P0 — Hard-constraint behavior is not operationally defined

Seven jobs converted every required qualification into a hard gate, while the Microsoft
job converted none. Across the corpus, 45 of 73 required requirements became hard.
Because hard constraints affect eligibility rather than ordinary scoring, this inconsistency
can dominate downstream matching.

The prompt and validator need a testable definition. Recommended rule: `hard_constraint`
is true only when failure makes the applicant ineligible or makes the application unable to
proceed. Placement under “Required Qualifications” alone is not sufficient.

### P0 — The taxonomy does not cover the benchmark

The strict schema cannot represent at least these observed roles directly:

- machine-learning engineering;
- hardware/ASIC engineering;
- technical program management as a primary family;
- product-management-specific track semantics.

This produced `unknown` for ASIC, software/data-science approximation for ML, and a
product-management workaround for the Apple EPM role. Prompt optimization cannot solve a
closed-schema omission.

### P0 — Completeness is not enforced

The NVIDIA ASIC profile omitted roughly half of the explicit qualifications, including all
preferred qualifications. The Google embedded profile returned zero responsibilities despite
an explicit responsibility section. Both profiles passed validation and returned no cleanup
warning.

Add deterministic section-coverage checks before accepting an extraction. At minimum, a
non-empty Required Qualifications, Preferred Qualifications, or Responsibilities source
section should require either extracted items or a bounded `NEEDS_REVIEW` reason.

### P1 — Alternatives lack an unambiguous logical representation

The flat `explicit_alternatives: string[]` field is used inconsistently for:

- true alternative qualification paths;
- members of an `OR` choice;
- degree subjects;
- examples;
- components of a compound requirement.

The registry matcher also assigned the language policy to Cloudflare because it split the
single value `C/C++`; it did not evaluate the full `Go`, `Rust`, or `C/C++` group as a unit.
Use a structured alternative group with explicit `any_of` members, or define and validate one
precise meaning for the existing list before changing the prompt.

### P1 — Compensation representation and extraction are weak

Four sources contained explicit pay information, yet no profile returned usable minimum and
maximum values. Some JDs contain multiple ranges by country or employer level, which the
single compensation object cannot represent. Even single-range Google and Apple sources lost
their numeric endpoints.

Decide whether Job Profile matching needs compensation. If it does, use a list of cited pay
ranges with jurisdiction/level qualifiers. If it does not, remove compensation from this
model stage rather than retaining misleading partial objects.

### P1 — Additional deterministic semantic checks are missing

The validator currently accepts:

- `unknown` in `adjacent_role_families`;
- the primary family repeated in adjacent families;
- employer-provided compensation with no usable value;
- employment type without source support;
- a non-empty source section with zero extracted items and no warning.

These are better enforced in code than through repeated prompt instructions.

### P2 — Upstream source quality affects extraction

The frozen inputs expose crawler/canonicalization defects that should remain distinguishable
from model defects:

- mojibake such as `Bachelorâ€™s` and `Appleâ€™s`;
- Microsoft required and preferred text flattened into summary spans;
- Google responsibility spans contaminated with navigation, privacy, and EEO boilerplate;
- Google location UI placeholders such as `+2 more`;
- source company recorded as `2100 NVIDIA USA`.

These inputs should stay in the evaluation set because they reflect realistic ingestion, but
the scorecard should attribute each failure to ingestion, extraction, schema, or validation.

## Recommended Optimization Sequence

1. Human-calibrate the preliminary review and establish expected role/track/level plus expected
   required/preferred section coverage for all ten jobs.
2. Expand the taxonomy and settle hard-constraint semantics before prompt tuning.
3. Add deterministic validators for section coverage, adjacent families, unsupported factual
   claims, and compensation consistency.
4. Define the logical contract for employer alternatives and fix registry matching.
5. Create `job-extract.v3` only for the remaining prompt-addressable failures.
6. Run v2 and v3 on the same frozen ten jobs and compare them blindly, per criterion.
7. Accept v3 only if no existing pass regresses and the ASIC, hard-gate, and completeness
   failures improve materially.

Candidate extraction, qualification assessment, and match scoring should remain unchanged
during this optimization cycle.

# Initial Expected Matching Score Matrix

Status: Initial estimates frozen before agent execution or human scoring
Matrix release: `matching-expected-scores.v1`
Scale: 0–100

## 1. Purpose

This matrix records an initial expected qualification-fit score for every combination of the eleven
synthetic candidate fixtures and ten frozen pilot jobs. It creates three deliberately separate
measurements:

1. **Initial expected score** — the pre-run estimate in this document.
2. **Agent score** — captured later, exactly as produced by the evaluated agent/version.
3. **Human score** — entered later by a human reviewer using the same rubric.

The initial score and expected range must not be included in any Candidate Profile, Job Profile,
Qualification Assessment, or scoring prompt. They are evaluation labels, not model inputs.

## 2. What the Score Means

The score estimates how strongly the frozen resume demonstrates the qualifications in the frozen
job description. It is not a prediction of interview selection or hiring.

Included:

- Demonstrated required capabilities and experience.
- Role-family and career-track alignment.
- Seniority, scope, ownership, architecture, leadership, and delivery evidence.
- Relevant domain context and preferred qualifications.
- Missing, weak, or merely claimed evidence.

Excluded:

- Candidate preferences and interest.
- Location and workplace preferences.
- Work authorization, sponsorship, or other eligibility facts.
- Compensation.
- Company reputation or prestige.
- Market competition and hiring probability.

At senior, principal, management, product, and program levels, demonstrated scope and outcomes carry
more weight than lists of tools or skills. A keyword overlap cannot compensate for missing ownership,
career track, or level.

## 3. Score Bands

| Score | Interpretation |
|---:|---|
| 80–100 | Strong direct fit; most important qualifications are demonstrated at the expected scope. |
| 65–79 | Credible fit with one or more meaningful gaps or a modest level mismatch. |
| 45–64 | Adjacent or materially incomplete; transferable evidence exists, but important requirements are missing. |
| 25–44 | Weak fit; limited relevant evidence and substantial domain, track, or level gaps. |
| 0–24 | Clear mismatch or insufficient evidence for the role's core qualifications. |

Each initial point estimate has an expected range. The range represents reasonable reviewer
variation, not statistical confidence. An agent score inside the range is directionally aligned;
an agent score outside it requires evidence review rather than an automatic prompt change.

## 4. Candidate Legend

| Code | Fixture | Short description |
|---|---|---|
| C1 | `cand_junior_sparse_01` | Entry-level software candidate with sparse evidence |
| C2 | `cand_backend_mid_01` | Mid-level backend and distributed-systems engineer |
| C3 | `cand_sre_senior_01` | Senior infrastructure and SRE engineer |
| C4 | `cand_mobile_mid_01` | Mid-level iOS engineer |
| C5 | `cand_ml_mid_01` | Mid-level production ML and model-evaluation engineer |
| C6 | `cand_asic_senior_01` | Senior ASIC and SoC design engineer |
| C7 | `cand_firmware_senior_01` | Senior embedded firmware engineer |
| C8 | `cand_product_senior_01` | Senior infrastructure product manager |
| C9 | `cand_tpm_senior_01` | Senior hardware/software technical program manager |
| C10 | `cand_manager_01` | Engineering manager with search and systems background |
| C11 | `cand_principal_01` | Principal distributed-platform and device-cloud architect |

## 5. Initial Matrix

Cell format: **initial score** `[expected range]`.

| Frozen job | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Amazon — Backend/transactional database | **24** [18–30] | **94** [90–97] | **65** [58–72] | **42** [35–48] | **49** [42–55] | **22** [15–28] | **35** [28–42] | **10** [5–15] | **10** [5–15] | **45** [38–52] | **78** [72–84] |
| Cloudflare — Senior distributed systems | **13** [8–18] | **72** [66–78] | **94** [91–97] | **35** [28–42] | **43** [35–50] | **10** [5–15] | **27** [20–34] | **13** [8–18] | **18** [12–24] | **57** [50–64] | **83** [78–88] |
| Apple — iOS software engineer | **13** [8–18] | **27** [20–34] | **27** [20–34] | **95** [92–98] | **22** [15–28] | **13** [8–18] | **33** [25–40] | **13** [8–18] | **13** [8–18] | **25** [18–32] | **28** [20–35] |
| NVIDIA — ML engineer, AI safety | **13** [8–18] | **52** [45–58] | **42** [35–48] | **24** [18–30] | **96** [93–99] | **13** [8–18] | **13** [8–18] | **25** [18–32] | **16** [10–22] | **28** [20–35] | **48** [40–55] |
| NVIDIA — Senior ASIC design | **10** [5–15] | **13** [8–18] | **13** [8–18] | **10** [5–15] | **15** [10–20] | **97** [94–99] | **57** [50–64] | **10** [5–15] | **33** [25–40] | **16** [10–22] | **23** [15–30] |
| Google — Embedded firmware/DNN frameworks | **15** [10–20] | **38** [30–45] | **38** [30–45] | **28** [20–35] | **28** [20–35] | **55** [48–62] | **96** [93–99] | **10** [5–15] | **33** [25–40] | **33** [25–40] | **38** [30–45] |
| Google — Infrastructure product manager | **10** [5–15] | **28** [20–35] | **33** [25–40] | **28** [20–35] | **38** [30–45] | **13** [8–18] | **13** [8–18] | **85** [80–90] | **59** [52–66] | **43** [35–50] | **53** [45–60] |
| Apple — Acoustics engineering program manager | **7** [3–10] | **22** [15–28] | **27** [20–34] | **27** [20–34] | **27** [20–34] | **43** [35–50] | **48** [40–55] | **59** [52–66] | **97** [94–99] | **52** [45–58] | **42** [35–48] |
| Microsoft — Principal software engineering manager, Search | **5** [2–8] | **28** [20–35] | **43** [35–50] | **20** [15–25] | **33** [25–40] | **13** [8–18] | **22** [15–28] | **28** [20–35] | **43** [35–50] | **97** [94–99] | **65** [58–72] |
| Amazon — Principal device-cloud engineer | **4** [0–8] | **53** [45–60] | **59** [52–66] | **28** [20–35] | **33** [25–40] | **13** [8–18] | **33** [25–40] | **33** [25–40] | **38** [30–45] | **59** [52–66] | **97** [95–99] |

## 6. Important Anchors

- C2 scores 94 for the Amazon backend job because the resume directly demonstrates production
  transaction services, replication, consensus, databases, scale, and sufficient experience.
- C3 scores 94 for Cloudflare infrastructure because it demonstrates multi-region operations,
  reliability ownership, automation, incident response, and senior scope.
- C4 scores 95 for Apple iOS because it meets the six-year duration, Swift/SwiftUI, XCTest,
  production application, API, and performance expectations.
- C5 scores 96 for NVIDIA AI Safety because it demonstrates production ML, PyTorch, dataset bias and
  robustness evaluation, product-security collaboration, MLOps, and the requested graduate degree.
- C6 scores 97 for NVIDIA ASIC because it directly covers RTL, SoC integration, synthesis, timing,
  architecture, scripting, verification collaboration, and more than five years of experience.
- C7 scores 96 for Google embedded firmware because it demonstrates nine years of C/C++, RTOS,
  architecture, testing, launch, debugging, and hardware/software integration.
- C8 scores 85 rather than the high 90s for Google product management because product and
  infrastructure experience are strong, but explicit generative-AI workflow integration is absent.
- C9 scores 97 for Apple acoustics EPM because the resume directly covers an EE degree, acoustic
  hardware, firmware, validation, suppliers, schedules, risks, executive reporting, and launches.
- C10 scores 97 for Microsoft Search management because it closely mirrors the domain, team size,
  people-management tenure, workstream count, systems background, and release-governance scope.
- C11 scores 97 for Amazon principal device cloud because its role, level, device-cloud domain,
  architecture scope, implementation languages, organizational influence, and tenure are direct.

## 7. Collection Contract

For every evaluated pair, store these values separately:

| Field | When recorded | Mutability |
|---|---|---|
| `initial_expected_score` | Before the first agent run | Frozen for matrix v1 |
| `expected_min` / `expected_max` | Before the first agent run | Frozen for matrix v1 |
| `agent_score` | Immediately after a run | Immutable per run/version |
| `agent_score_method` | With the agent score | Required; identifies direct or derived scoring |
| `human_score` | During independent review | Append-only; adjudicated value stored separately |
| `human_confidence` | With human score | Required |
| `human_notes` | With human score | Required when outside the expected range |

The human-scoring UI should hide both the initial expected score and agent score until the reviewer
submits their score. This prevents anchoring. After submission, the three values may be compared.

## 8. How to Use Differences

Do not optimize the prompt from score error alone. For any material difference, inspect in order:

1. Whether Candidate Profile extraction preserved the relevant resume evidence.
2. Whether Job Profile extraction captured and classified the correct atomic requirements.
3. Whether Qualification Assessment used valid evidence and correct statuses.
4. Whether the scoring method converted those assessments consistently.
5. Whether the initial or human expectation should be revised.

Recommended diagnostic thresholds:

- Agent score inside expected range: no score-level disagreement.
- Outside the range by 1–9 points: minor disagreement; review if systematic.
- Outside the range by 10–19 points: material disagreement requiring classification.
- Outside the range by 20 or more points: severe disagreement or likely pipeline defect.
- Correct ordering but shifted scores: likely calibration issue.
- Incorrect ordering between direct matches and mismatches: likely extraction, qualification, or
  weighting defect rather than simple calibration.

Prompt changes should target a classified evidence or reasoning failure. Deterministic score
calibration belongs in the later scoring layer and should not be hidden inside extraction prompts.

## 9. Machine-Readable Source

The authoritative machine-readable matrix is
`server/app/modules/evaluation/expected_score_matrix.v1.json`. It contains all 110 initial point
estimates and expected ranges. Agent and human scores must be stored as evaluation results and must
not overwrite this release.

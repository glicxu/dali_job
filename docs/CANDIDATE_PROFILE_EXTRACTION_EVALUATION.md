# Candidate Profile Extraction Evaluation

Date: 2026-08-16

Corpus: seven internal test resumes (three PDF, four DOCX)

Model: `gpt-5.6-luna`

Baseline prompt version: `candidate-extract.v1`

Current replay: `candidate-extract.v3`, `candidate-extract-response.v3`, `canonical-text.v3`,
`evidence-spans.v2`, and `matching-semantic-validator.v2` on 2026-08-16.

## Purpose

This evaluation establishes an initial human baseline for Step 1 of the three-step matching workflow:

1. **Step 1a — document extraction:** resume file to privacy-redacted canonical text and evidence spans.
2. **Step 1b — candidate profiling:** canonical text and evidence spans to a structured Candidate Profile.

The two stages are scored separately. A prompt cannot recover facts that the document parser omitted, and a good Candidate Profile must not make unsafe source text acceptable.

## Executive Result

All seven files produced persisted, schema-valid Candidate Profiles. All 384 evidence references point to existing evidence spans. That is a useful structural baseline, but the current flow is not yet a reliable candidate-extraction evaluation gate:

- Privacy redaction passed only **4 of 7** cases. One name and three street-address occurrences remained in the canonical text supplied to the model.
- PDF extraction was high fidelity in zero of three cases: two were usable but omitted bullet fragments; one omitted an entire university education record and substantially flattened the document.
- Four of seven Candidate Profiles contain malformed, truncated, or semantically invalid dates.
- One of seven profiles has a materially wrong primary career classification.
- One profile converted a descriptive statement about research into an unsupported publication title.
- The average model-reported completeness was **93.1%**, while the provisional human end-to-end profile score averaged **80.6%**. The model's completeness score is not calibrated.

The next optimization should fix document fidelity and privacy gates before comparing candidate prompt revisions.

## V3 Remediation Checkpoint

The seven original files were replayed from protected storage into new immutable canonical sources and
Candidate Profile versions. The V1 artifacts were retained. The replay report contains aggregate facts,
version identities, and privacy diagnostics but no raw resume text.

Automated results:

| Check | V1 | V3 | Status |
|---|---:|---:|---|
| Profiles persisted | 7/7 | 7/7 | Pass |
| Residual privacy findings | 3/7 cases failed | 0/7 | Pass automated gate |
| Schema or semantic failures | 0 | 0 | Pass |
| Unsupported exact publication observed in C26 | 1 | 0 | Fixed in replay |
| C26 primary career classification | Incorrect software engineering | `unknown` / research | Fixed conservatively |
| Average model-reported completeness | 0.931 | 0.863 | Better calibrated in aggregate; human comparison pending |

Implemented changes:

- Fail-closed residual email, phone, URL, and street-address detection now follows redaction, and likely
  header names are removed even when the header has no separate contact line.
- Candidate-profile creation re-redacts stored document text before creating the canonical model source,
  which also protects documents imported before the improved redactor.
- PDF parsing compares layout-aware and plain text extraction and retains the richer per-page result.
  A multi-page PDF with an unreadable page is rejected for user correction instead of silently accepted.
- Candidate date fields are schema-constrained and deterministically checked for calendar validity,
  chronological ordering, and current-employment consistency.
- Exact publication titles require literal normalized support in their cited evidence.
- Awards, patents, and languages are first-class structured facts with evidence references. Patent titles,
  like publication titles, require literal normalized support.
- The prompt requires conservative date precision, explicit publication evidence, completeness reductions
  for missing or ambiguous facts, and `unknown` rather than a forced adjacent career family.
- Section recovery recognizes known embedded headings and no longer treats arbitrary uppercase acronyms
  such as `EMR` as headings.

V3 fact-count snapshot:

| Case | Skills | Experience | Projects | Education | Publications | Awards | Patents | Languages | Primary family / track / level |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| C23 | 34 | 6 | 8 | 2 | 0 | 0 | 0 | 3 | software engineering / IC / mid |
| C24 | 12 | 6 | 6 | 2 | 0 | 0 | 3 | 0 | software engineering / management / staff |
| C25 | 21 | 2 | 5 | 2 | 0 | 0 | 0 | 0 | data science / IC / student-or-intern |
| C26 | 7 | 4 | 2 | 2 | 0 | 7 | 0 | 0 | unknown / research / student-or-intern |
| C27 | 15 | 2 | 5 | 3 | 10 | 2 | 6 | 0 | software engineering / management / principal |
| C28 | 9 | 7 | 0 | 2 | 2 | 5 | 0 | 2 | data science / research / student-or-intern |
| C29 | 14 | 2 | 9 | 1 | 0 | 1 | 0 | 0 | software engineering / IC / student-or-intern |

This closes the identified automated implementation holes, not the human evaluation gate. A tester must
compare each V3 source/profile pair with its original file before asserting zero material omissions,
accepted classifications, or per-case completeness calibration.

## Scoring Method

- **Source fidelity:** human estimate of material fact retention and readable structure after file parsing, before LLM profiling.
- **Privacy:** pass only when the canonical text sent to the LLM excludes names, contact data, profile URLs, and residential addresses.
- **Profile quality:** human estimate of factual correctness, material coverage, career classification, evidence discipline, and usability against the original resume.
- These are provisional scores for prioritization, not statistically validated metrics. A second human should adjudicate them before they become a formal golden set.

## Initial Human Baseline

| Case | Format | Source fidelity | Privacy | Profile quality | Disposition | Main finding |
|---|---:|---:|---:|---:|---|---|
| C23 | PDF | 85 | Pass | 84 | Usable with corrections | Two bullet fragments omitted; employment ranges copied into `last_used`; one unsupported education-field inference. |
| C24 | DOCX | 98 | Fail | 85 | Blocked by privacy/date defects | Text fidelity is strong, but the candidate name remains in model input and two publication dates are corrupted. |
| C25 | PDF | 82 | Pass | 86 | Usable with corrections | Two project bullet prefixes omitted; two expected dates corrupted; sectioning treats `EMR` as a heading. |
| C26 | DOCX | 97 | Fail | 62 | Fail | Street address remains; primary software-engineering classification conflicts with the healthcare/research objective and evidence; an unsupported publication title was created. |
| C27 | DOCX | 99 | Pass | 89 | Good with schema gaps | Strong extraction and classification; patents and honors are not representable, and `staff` is awkward for a management-track profile. |
| C28 | PDF | 55 | Pass | 72 | Fail upstream | Entire university education entry is missing, most content is flattened into general spans, and five dates are corrupted or truncated. |
| C29 | DOCX | 98 | Fail | 86 | Blocked by privacy | Two residential addresses remain; institution is inferred rather than explicit; an award is not representable. |
| **Average** |  | **87.7** | **4/7 pass** | **80.6** |  |  |

## Automated Gate Results

| Check | Result | Assessment |
|---|---:|---|
| Files parsed and profiles persisted | 7/7 | Pass |
| Strict Candidate Profile schema validation | 7/7 | Pass |
| Evidence-reference integrity | 384/384 valid | Pass |
| Privacy-safe canonical input | 4/7 | Fail |
| High-fidelity document extraction | 4/7 | Fail; all four are DOCX |
| Partial but usable extraction | 2/7 | Both are PDF |
| Material document-extraction failure | 1/7 | PDF |
| Profiles without suspicious date values | 3/7 | Fail |
| Acceptable primary career classification | 6/7 | Initial human judgment |

### Candidate Profile fact counts

| Case | Skills | Experience | Projects | Education | Certifications | Publications | Career profiles |
|---|---:|---:|---:|---:|---:|---:|---:|
| C23 | 23 | 6 | 0 | 2 | 0 | 0 | 1 |
| C24 | 13 | 6 | 6 | 3 | 0 | 3 | 2 |
| C25 | 25 | 2 | 5 | 2 | 0 | 0 | 1 |
| C26 | 9 | 8 | 3 | 2 | 0 | 1 | 1 |
| C27 | 18 | 1 | 6 | 3 | 0 | 10 | 1 |
| C28 | 13 | 7 | 3 | 1 | 0 | 2 | 3 |
| C29 | 11 | 3 | 4 | 1 | 0 | 0 | 1 |

## Findings by Stage

### Step 1a — Document extraction and privacy

1. **DOCX fidelity is strong.** All four DOCX files retained nearly all visible resume content.
2. **PDF layout extraction is not reliable enough for a golden corpus.** Multi-column or positioned content can be omitted or reordered. C28 lost an entire university education entry. C23 and C25 lost leading portions of bullets.
3. **Redaction depends too heavily on detecting header contact details.** A probable name is removed only when contact data was found near the header. This allowed a name through in C24.
4. **Street addresses are not covered by the current location patterns.** C26 and C29 retained residential street addresses.
5. **Section detection is overly permissive for short uppercase text.** Tokens such as `EMR` become headings, while a heading such as `AP Scores` can absorb most subsequent content.

### Step 1b — Candidate Profile extraction

1. **Date fields are unconstrained strings.** The schema limits them to ten characters but does not define a format. The model returned truncated ranges and corrupted characters in four cases. `last_used` also received employment ranges instead of a single date.
2. **Completeness is overconfident.** Scores from 0.88 to 0.97 did not reflect missing source content, unsupported facts, privacy failures, or unrepresentable sections.
3. **Publication evidence discipline needs tightening.** C26 supplied descriptive wording about published research, but the profile turned it into an exact-looking title not present in the source.
4. **The career taxonomy has a coverage gap.** A healthcare/biomedical research candidate was forced into software engineering as the sole primary profile, based mainly on one Python project.
5. **The schema drops material achievements.** It has no dedicated awards/honors, patents, languages, or general accomplishments collections. Honors or awards were lost in at least four cases, and patents were lost or squeezed into publications.
6. **Management level terminology needs an explicit mapping.** `staff` may represent comparable scope, but it is confusing when paired with `engineering_management` without a management-equivalent label.
7. **Evidence references are structurally sound.** No profile cited an unknown span. This validates reference plumbing, but does not prove that each cited span semantically supports every claim.

## Recommended Remediation Order

### P0 — Establish safe and faithful model input

1. Extend deterministic redaction for street addresses and names even when no contact line is detected.
2. Add a pre-LLM privacy gate that rejects or quarantines canonical text with probable contact or residential information.
3. Add PDF extraction quality checks, including page count, section presence, suspiciously flattened text, and comparison of extracted text volume by page.
4. Evaluate a layout-aware PDF path and retain the original file for human comparison.
5. Tighten heading recognition so arbitrary short uppercase tokens are not automatically promoted to sections.

### P1 — Make the Candidate Profile schema loss-aware

1. Replace free-form date behavior with exact raw date text plus deterministic normalized date fields, or require `null` when normalization is not safe.
2. Add awards/honors and patents, or a typed accomplishments collection that preserves them without misclassifying them as publications.
3. Decide whether languages and volunteer work need first-class representation.
4. Add biomedical/healthcare research coverage or allow `unknown` as the primary family when the taxonomy cannot represent the candidate.
5. Define management-track equivalents for IC levels.

### P2 — Revise the candidate-extraction prompt

1. Preserve supported date text exactly; never invent replacement characters; return `null` plus a quality warning for malformed or ambiguous dates.
2. Require `last_used` to be a single supported point in time, never an employment range.
3. Do not create a publication title from a description of research. If an exact title is absent, use a non-publication accomplishment or omit it with a warning.
4. Define completeness as representable, supported material-fact coverage and require penalties for warnings and omissions.
5. Require the primary career profile to reconcile declared objectives with demonstrated evidence, while allowing adjacent secondary profiles.

### P3 — Add a repeatable candidate-only evaluation workflow

1. Freeze original file, canonical text, evidence spans, structured output, model, and prompt version for every run.
2. Add human annotations for source fact recall, privacy, unsupported claims, primary family, track, level, and important omissions.
3. Replay Step 1b independently from frozen canonical text when tuning prompts.
4. Replay Step 1a independently when tuning parsers or redaction.
5. Keep a held-out set so improvements are not limited to these seven resumes.

## Proposed Acceptance Gates for the Next Iteration

For this seven-resume development set:

- Privacy-safe model input: **7/7**.
- No material education or employment omission from the original file: **7/7**.
- Valid, non-corrupted dates: **100% of emitted date fields**.
- Unsupported exact publications, institutions, degrees, or employers: **0**.
- Evidence references resolve: **100%**.
- Primary family/track/level accepted by human review: **at least 6/7**, with every disagreement recorded.
- Absolute difference between completeness and human profile-quality score: **0.10 or less per case**.

These thresholds are development gates, not production performance claims. The corpus must grow and include independently adjudicated examples before setting production targets.

## Conclusion

V3 passes the repeatable automated replay gate for all seven development resumes and fixes the known
privacy, date-normalization, unsupported-publication, heading, schema-coverage, and forced-family defects.
It is ready for human QA in the Candidate Profile lab. The corpus is still too small and not yet
adjudicated, so V3 is not yet a production-quality claim.

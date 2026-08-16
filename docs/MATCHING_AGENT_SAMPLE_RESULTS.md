# Initial Agent Sample Results

Execution environment: US3
Sample release: `matching-agent-score-sample.v1`
Execution policy: one attempt per pair, no retries

## Outcome

Ten pairs were selected before execution: two from each initial score band. The frozen expected
score and band were not sent to the agent.

| Initial band | Sample | Initial score | Agent result | Agent score |
|---|---|---:|---|---:|
| Strong | ML candidate → NVIDIA AI Safety | 96 | Qualification response rejected: alternative lacked an approved reference | — |
| Strong | Engineering manager → Microsoft Search manager | 97 | Job Profile response rejected by strict schema validation | — |
| Credible | Backend candidate → Cloudflare distributed systems | 72 | Qualification response rejected: alternative reference used with the wrong status | — |
| Credible | Principal architect → Microsoft Search manager | 65 | Job Profile response rejected by strict schema validation | — |
| Adjacent | Firmware candidate → NVIDIA ASIC | 57 | Qualification response rejected: `not_demonstrated` cited supporting evidence | — |
| Adjacent | TPM candidate → Google infrastructure PM | 59 | Completed: 4 met, 2 partially met, 3 not demonstrated | — |
| Weak | Firmware candidate → Apple iOS | 33 | Qualification response rejected: requirement coverage was not exactly once | — |
| Weak | Backend candidate → Google embedded firmware | 38 | Completed: 1 met, 1 partially met, 5 not demonstrated, 1 needs clarification | — |
| Mismatch | Product candidate → NVIDIA ASIC | 10 | Qualification response rejected: `not_demonstrated` cited supporting evidence | — |
| Mismatch | Junior candidate → Amazon principal engineer | 4 | Qualification response rejected: alternative reference used with the wrong status | — |

Totals:

- 10 attempted.
- 2 completed and persisted.
- 8 rejected by strict output validation.
- 0 numerical agent scores returned.
- 0 automatic retries.

## What the Completed Runs Returned

### Adjacent TPM candidate → Google infrastructure PM

Persisted run: `evr_513eb95470714b1586478baf4027172d`

The agent found:

- Met: bachelor's degree, product conception-to-launch experience, release/product launches, and
  large cross-functional projects.
- Partially met: five years in product management or a related technical role; tooling and software
  systems experience.
- Not demonstrated: generative-AI/LLM workflow integration, a master's degree, and infrastructure
  space/power capacity planning.

This is qualitatively consistent with an adjacent score around the initial estimate of 59, but the
system does not currently convert these decisions into an agent score.

### Weak backend candidate → Google embedded firmware

Persisted run: `evr_54d56d554f0a4a279fddfe62513aabc1`

The agent found:

- Met: bachelor's degree.
- Partially met: general software product and architecture experience.
- Not demonstrated: C/C++, embedded operating systems, Android, graduate degree, and five years of
  data-structures/algorithms evidence.
- Needs clarification: technical-leadership experience.

This is qualitatively consistent with a weak score around the initial estimate of 38, but again no
numerical agent score was generated.

## Primary Finding

The current three-step implementation cannot yet support the planned three-number comparison:

```text
initial expected score ↔ agent score ↔ human score
```

It intentionally records `score_generated: false`. More urgently, only 20% of this first sample
crossed the strict Candidate Profile → Job Profile → Qualification Assessment contract. Numerical
calibration would be misleading until output-contract reliability improves.

Observed contract failures:

| Failure class | Count |
|---|---:|
| Invalid alternative-policy/status relationship | 3 |
| `not_demonstrated` incorrectly cited as supporting evidence | 2 |
| Invalid Job Profile response | 2 |
| Missing or duplicate requirement coverage | 1 |

## Recommended Next Sequence

1. Preserve these ten attempts as the baseline; do not retry them into apparent success.
2. Improve Job Profile and Qualification prompts so they restate the cross-field invariants enforced
   by validation.
3. Add one bounded repair retry for structurally invalid output, recording both attempts.
4. Replay the identical ten samples and target 10/10 schema-valid completion before score work.
5. Add a separate, versioned scoring step that consumes only validated Job Profile and Qualification
   artifacts and returns a 0–100 `agent_score` with dimension-level contributions.
6. Collect blind human scores only after the agent score is persisted and hidden from the reviewer.

The scoring step should not be embedded in Candidate Profile or Job Profile extraction prompts.
Otherwise prompt tuning can distort source-grounded artifacts merely to move a final number.

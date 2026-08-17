# DaliJob Product Feedback

This document records product feedback that should be evaluated before it is converted into implementation work. Items here describe the desired outcome and guardrails; they are not automatically approved requirements.

## PF-001: Suggest Evidence-Supported Next-Level Roles

- **Date:** 2026-08-16
- **Area:** Candidate Profile / Suggested Target Roles
- **Status:** Proposed

### Feedback

Suggested target roles should account for reasonable career progression. When a candidate has spent sufficient time in a role and their resume demonstrates readiness for greater responsibility, suggestions should include the next appropriate level instead of only repeating roles they have already held.

For example, a candidate with sustained internship experience who has demonstrated independent delivery may be ready for junior or entry-level roles. Likewise, a junior candidate may be shown mid-level roles when their evidence demonstrates the expected scope and ownership.

### Proposed behavior

For each relevant role family, generate a small set of suggestions that may include:

1. A role aligned with the candidate's demonstrated current level.
2. A next-level role when the evidence supports progression.
3. An adjacent role when the candidate has transferable, demonstrated capabilities.

Every progression suggestion should include:

- the suggested role and level;
- a short, human-readable rationale;
- the supporting resume evidence;
- a confidence value; and
- any important capability gap between the candidate's evidence and the suggested role.

### Progression rule

Time in a role is a useful signal, but it must not be sufficient by itself. A next-level suggestion should combine dated experience, where available, with evidence such as:

- independent delivery of meaningful work;
- increasing scope or complexity;
- ownership of a feature, project, system, or outcome;
- application of relevant skills in experience or projects;
- collaboration, mentoring, leadership, or decision-making appropriate to the target track; and
- measurable or otherwise concrete outcomes.

If duration is unknown or the evidence is weak, the product should remain at the demonstrated level or present the next level as an exploratory option with lower confidence. It should not infer readiness from title alone.

### Level and track guardrails

- Treat progression as role-family-specific; a candidate can be at different levels in different career profiles.
- Use the existing level taxonomy: `student_or_intern`, `entry`, `junior`, `mid`, `senior`, `staff`, and `principal`.
- Do not automatically treat engineering management as the next step after senior individual-contributor work. Management and other tracks require their own evidence.
- Do not use employer or school prestige, age, graduation year, protected characteristics, or uninterrupted employment as progression evidence.
- Do not penalize career gaps, part-time work, nontraditional backgrounds, or career changes.
- Avoid unsupported title inflation. Suggestions should describe a plausible next opportunity, not certify that the candidate already holds that level.

### Product and data treatment

Suggested next-level roles are derived recommendations, not factual resume evidence. They must not:

- satisfy a job qualification;
- change the extracted employment history or inferred current level;
- silently become search or matching preferences; or
- overwrite a user's confirmed target roles.

The candidate should be able to accept, dismiss, or edit a suggestion. Only an explicitly accepted suggestion should become an active target-role preference.

A suggested-role record should retain, at minimum:

```json
{
  "role_family": "software_engineering",
  "suggested_title": "Junior Software Engineer",
  "suggested_level": "junior",
  "suggestion_type": "next_level",
  "rationale": "Sustained internship work with evidence of independent feature delivery.",
  "evidence_refs": ["experience-1", "project-2"],
  "confidence": 0.82,
  "capability_gaps": ["Limited evidence of production operations ownership"],
  "user_status": "unreviewed"
}
```

### Examples

| Candidate evidence | Expected suggestion |
|---|---|
| One short internship with mostly observational duties | Internship and entry-level exploratory roles; do not assert junior readiness. |
| Multiple internships or sustained internship work with independent feature delivery | Entry-level or junior roles, with the delivery evidence in the rationale. |
| Junior title plus demonstrated end-to-end ownership and growing technical scope | Current-level roles and selected mid-level roles, with any remaining gaps disclosed. |
| Senior individual contributor with no people-management evidence | Senior or advanced individual-contributor roles; do not automatically suggest engineering manager. |
| Several years in a role but little evidence of expanded scope | Do not advance level based on tenure alone. |

### Acceptance criteria

- A candidate with strong, cited next-level evidence receives at least one plausible progression suggestion.
- A candidate with tenure but no supporting capability evidence is not automatically advanced.
- Each next-level suggestion exposes a rationale, evidence references, confidence, and capability gaps.
- Suggestions never count as evidence in qualification assessment or matching scores.
- No suggestion becomes a preference until the user explicitly confirms it.
- Suggestions respect role-family and career-track boundaries.
- Automated tests cover positive progression, insufficient evidence, unknown duration, career changes, and individual-contributor versus management tracks.

### Open product questions

- Should the UI label these as **Next-step roles**, **Growth roles**, or **Suggested target roles**?
- Should lower-confidence next-level roles appear by default or only behind an exploratory filter?
- What confidence threshold should separate a primary recommendation from an exploratory suggestion?


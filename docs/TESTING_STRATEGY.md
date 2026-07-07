# DaliJob Testing Strategy

## 1. Testing Goals

- Protect core application tracking from regressions.
- Verify owner-only workspace authorization everywhere.
- Ensure document and versioning behavior is immutable and traceable.
- Validate AI outputs before they affect user-facing records.
- Keep integrations testable without relying on live providers.
- Make analytics reproducible.

## 2. Unit Tests

### Backend Business Logic

Test:

- Application status transitions.
- Application status history creation.
- Timeline event creation.
- Owner-only workspace permission checks.
- Resume-to-job match scoring with a required 0-10 range.
- Matched and missing skill extraction.
- Resume schema validation.
- Cover letter validation.
- Job analysis parsing validation.
- Match score calculations.
- Analytics calculations.
- Document version sequencing.
- Task and reminder rules.

### AI Validation

Test:

- Resume output cannot include unsupported employers.
- Resume output cannot invent dates, degrees, certifications, tools, or metrics.
- Cover letter output flags unsupported claims.
- Job analysis output matches schema.
- Resume-to-job match output includes score, matched skills, missing skills, supported requirements, and unsupported requirements.
- Email classification maps to allowed application statuses.
- Interview prep output includes required sections.

### Frontend

Test:

- Form validation.
- Status controls.
- Application tracker filtering.
- Resume review diff rendering.
- Document attachment UI.
- Analytics display formatting.

## 3. Integration Tests

Test with real local services:

- SQL database migrations.
- SQLAlchemy repositories.
- DbMan session and query helpers.
- ProcessConfig loading from local test ini files.
- Database setup scripts against a configured DaliJob test schema.
- Redis queue operations when background jobs are introduced.
- Object storage upload/download.
- FastAPI routes with authentication.
- Worker job lifecycle.

Client/server contract tests:

- Server OpenAPI schema includes every endpoint used by the client.
- Client API wrapper request shapes match server schemas.
- Server response shapes remain backward compatible for supported client versions.
- Breaking API changes fail CI unless the API version is changed or compatibility handling is added.

Critical integration cases:

- User A cannot access User B workspace records.
- Server starts with `--config local-test.ini` and uses that database config.
- Repository tests use `DbMan.session_scope()` or `DbMan.session_dependency()`.
- `scripts/create_schema.py`, `scripts/create_tables.py`, `scripts/seed_database.py`, and `scripts/validate_database.py` operate against the schema named in the test config.
- A pasted resume and pasted job description return a 0-10 match result.
- OpenAI provider reads API key from `OPENAI_API_KEY` and model from server config, not client input.
- A score never returns below 0 or above 10.
- A fully manual job can be created without source URL or plugin data.
- A URL import failure still allows the user to save a manually completed job.
- Uploaded document creates version 1.
- New generated file creates version 2 without mutating version 1.
- Tailored resume generation creates `ai_generation_job`, `resume_version`, `document_version`, and application event.
- Cover letter generation links to application and resume version.
- Status suggestion from email does not apply until accepted.

## 4. End-To-End Tests

Use browser tests for critical workflows:

- Create multiple resume profiles, edit resume JSON skills, experience, education, and projects.
- Set a default resume profile, then verify only one resume is default and it sorts first.
- Upload or paste a master resume, paste a job description, run comparison, and view a 0-10 match score.
- Create a job through full manual entry.
- Import job by copy/paste description.
- Attempt URL job extraction, review extracted fields, and save.
- Attempt URL job extraction failure, manually complete missing fields, and save.
- Create application from job.
- Upload resume and attach to application.
- Move application through statuses.
- Generate tailored resume and review it.
- Generate cover letter and attach it.
- Schedule interview and generate prep guide.
- Record interview journal entry.
- View analytics dashboard.

## 5. AI Evaluation Suite

Maintain static eval fixtures:

- Master profiles.
- Job descriptions.
- Expected extracted requirements.
- Expected missing skills.
- Resume tailoring guardrail cases.
- Cover letter guardrail cases.
- Email classification examples.
- Interview preparation examples.

Evaluation metrics:

- Schema validity rate.
- Unsupported-claim rate.
- Requirement coverage.
- Classification accuracy.
- Human review warning precision.
- Latency and cost by job type.

AI evals should run against a mock provider in CI and against real providers in a controlled manual or scheduled evaluation environment.

## 6. Security Tests

Required tests:

- Cross-workspace access attempts by non-owners return 403 or 404.
- Signed document URLs expire.
- OAuth credentials are encrypted at rest.
- Sensitive fields are redacted from logs.
- File upload rejects unsupported types.
- Prompt injection strings in job descriptions do not override system instructions.
- Email body content is not exposed through unrelated endpoints.

## 7. Plugin Tests

Each job source plugin should include:

- Manifest validation.
- Normalization tests.
- Missing field handling.
- Rate limit handling.
- Provider failure handling.

Core app tests should verify plugin failure does not break manual job import or application tracking.

## 8. Performance Tests

Initial targets:

- Application list loads under 500 ms for 1,000 applications in a workspace.
- Job search returns under 750 ms for common filters.
- Analytics summary returns under 1 second for 5,000 applications.
- Worker queue can process document rendering and AI jobs independently.

## 9. Manual QA Checklist

- Upload PDF resume.
- Upload DOCX resume if supported.
- Upload PDF job description.
- Import job from URL.
- Manually enter a job with no URL.
- Manually enter a job deadline.
- Generate tailored resume.
- Generate cover letter.
- Attach submitted documents.
- Create interview.
- Generate study guide.
- Record interview feedback.
- Generate analytics.
- Revoke email/calendar integrations.
- Delete account/workspace data.

## 10. CI Requirements

Every pull request should run:

- Server lint.
- Server type checks if configured.
- Server unit tests.
- Server integration tests with configured SQL database.
- Client lint.
- Client unit tests.
- Client build.
- Client/server contract tests.
- Migration check.

Nightly or pre-release should run:

- E2E tests.
- AI evals.
- Security dependency scans.
- Container image scan.

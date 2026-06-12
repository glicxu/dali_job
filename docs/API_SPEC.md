# DaliJob API Specification

## 1. API Conventions

- Base path: `/api/v1`.
- Request and response format: JSON unless uploading files.
- Authentication: session cookie or bearer token.
- Authorization: every request is scoped to a private workspace owned by the authenticated user.
- IDs: UUID strings.
- Errors: return structured error bodies.

Error shape:

```json
{
  "error": {
    "code": "application_not_found",
    "message": "Application not found.",
    "details": {}
  }
}
```

## 2. Authentication And Workspaces

### `GET /me`

Returns the current user and available workspaces.

### `PATCH /me`

Updates display name, timezone, and preferences.

### `GET /workspaces`

Lists workspaces owned by the user.

### `POST /workspaces`

Creates a private workspace owned by the current user.

Required body:

```json
{
  "name": "My Career Search"
}
```

## 3. Profile

### `GET /profile`

Returns the active structured career profile.

### `PATCH /profile`

Updates profile summary, targets, preferences, and portfolio links.

### `GET /profile/skills`

Lists skills.

### `POST /profile/skills`

Creates a skill.

### `GET /profile/experiences`

Lists work experiences.

### `POST /profile/experiences`

Creates work experience.

### `PATCH /profile/experiences/{experienceId}`

Updates work experience.

### `POST /profile/experiences/{experienceId}/bullets`

Adds an evidence-backed bullet.

### `GET /profile/projects`

Lists projects.

### `POST /profile/projects`

Creates a project.

Equivalent CRUD endpoints should exist for education, certifications, awards, and publications.

## 4. Companies And Recruiters

### `GET /companies`

Query params:

- `q`
- `industry`
- `limit`
- `cursor`

### `POST /companies`

Creates a company.

### `GET /companies/{companyId}`

Returns company details, related jobs, applications, recruiters, and research summaries.

### `PATCH /companies/{companyId}`

Updates company metadata.

### `POST /companies/{companyId}/research`

Queues company research generation.

### `GET /recruiters`

Lists recruiters and contacts.

### `POST /recruiters`

Creates recruiter/contact.

## 5. Jobs

### `GET /jobs`

Lists imported jobs.

Query params:

- `q`
- `company_id`
- `source_provider`
- `remote_policy`
- `skill`
- `limit`
- `cursor`

### `POST /jobs`

Creates a job from manual input. This is a core workflow and must not depend on job board APIs, plugins, or URL extraction.

Body:

```json
{
  "title": "Software Engineer",
  "company_name": "Example Co",
  "source_url": "https://example.com/jobs/123",
  "description_raw": "Full job description...",
  "location": "Remote",
  "remote_policy": "remote",
  "employment_type": "full_time",
  "seniority": "mid_level",
  "posting_date": "2026-06-01",
  "closing_date": "2026-07-01",
  "compensation_min": 90000,
  "compensation_max": 125000,
  "compensation_currency": "USD",
  "notes": "Found on company careers page."
}
```

### `POST /jobs/import-url`

Attempts to import a job from a pasted URL. The server may fetch the page, extract structured job posting data, parse visible text, and return a draft job for user review.

Body:

```json
{
  "url": "https://example.com/careers/software-engineer",
  "create_application": false
}
```

Response:

```json
{
  "job_id": "uuid",
  "import_status": "needs_review",
  "fields_extracted": ["title", "company_name", "description_raw", "location"],
  "fields_missing": ["closing_date", "compensation_min", "compensation_max"],
  "message": "Review extracted fields before saving."
}
```

If extraction fails, the API should return a draft with the URL preserved and instructions for manual completion rather than blocking the user from creating the job.

### `POST /jobs/import-file`

Imports a job description from an uploaded PDF or text file.

### `GET /jobs/{jobId}`

Returns a job with structured analysis and linked applications.

### `PATCH /jobs/{jobId}`

Updates job metadata.

### `POST /jobs/{jobId}/analyze`

Queues job analysis.

### `POST /jobs/{jobId}/compare-profile`

Compares job requirements against the user's profile.

Returns:

```json
{
  "match_score": 82,
  "missing_skills": [],
  "relevant_projects": [],
  "recommended_resume_changes": [],
  "recommended_study_topics": []
}
```

## 6. Applications

### `GET /applications`

Lists applications.

Query params:

- `status`
- `company_id`
- `q`
- `applied_after`
- `applied_before`
- `limit`
- `cursor`

### `POST /applications`

Creates an application from an existing job or inline job data.

### `GET /applications/{applicationId}`

Returns application details, job, company, documents, timeline, interviews, tasks, and notes.

### `PATCH /applications/{applicationId}`

Updates priority, notes, salary notes, next action, and other metadata.

### `POST /applications/{applicationId}/status`

Changes status and appends status history.

Body:

```json
{
  "status": "applied",
  "reason": "Submitted through company portal"
}
```

### `GET /applications/{applicationId}/events`

Returns timeline events.

### `POST /applications/{applicationId}/notes`

Adds an application note.

### `POST /applications/{applicationId}/tasks`

Creates a task or reminder for the application.

## 7. Documents

### `POST /documents/upload-url`

Creates a signed upload URL.

### `POST /documents`

Creates document metadata after upload.

### `GET /documents`

Lists documents.

### `GET /documents/{documentId}`

Returns document metadata and versions.

### `GET /documents/{documentId}/download-url`

Creates a signed download URL.

### `POST /applications/{applicationId}/documents`

Attaches a document version to an application.

Body:

```json
{
  "document_id": "uuid",
  "document_version_id": "uuid",
  "purpose": "submitted"
}
```

## 8. Resume Engine

### `GET /resume-versions`

Lists resume versions.

### `POST /resume-versions/parse`

Queues parsing from an uploaded resume document into structured profile data.

### `POST /applications/{applicationId}/resume/tailor`

Queues tailored resume generation.

Body:

```json
{
  "source_profile_id": "uuid",
  "length": "one_page",
  "tone": "technical",
  "emphasis": ["server", "cloud", "leadership"]
}
```

### `GET /resume-versions/{resumeVersionId}`

Returns a structured resume version.

### `PATCH /resume-versions/{resumeVersionId}`

Creates an edited version from user changes. Existing versions remain immutable.

### `POST /resume-versions/{resumeVersionId}/render`

Queues PDF or DOCX rendering.

## 9. Cover Letter Engine

### `GET /applications/{applicationId}/cover-letters`

Lists cover letter versions for an application.

### `POST /applications/{applicationId}/cover-letters/generate`

Queues cover letter generation.

### `GET /cover-letter-versions/{coverLetterVersionId}`

Returns cover letter content and metadata.

### `PATCH /cover-letter-versions/{coverLetterVersionId}`

Creates an edited version from user changes.

### `POST /cover-letter-versions/{coverLetterVersionId}/render`

Queues PDF or DOCX rendering.

## 10. Interviews

### `GET /applications/{applicationId}/interviews`

Lists interviews.

### `POST /applications/{applicationId}/interviews`

Creates an interview.

### `PATCH /interviews/{interviewId}`

Updates schedule, type, outcome, or location.

### `POST /interviews/{interviewId}/notes`

Adds interview journal notes.

### `POST /applications/{applicationId}/interview-prep`

Queues interview preparation generation.

### `GET /interview-prep/{guideId}`

Returns a generated prep guide.

### `POST /applications/{applicationId}/mock-interviews`

Starts or schedules a mock interview session.

## 11. Analytics And Career Intelligence

### `GET /analytics/summary`

Returns application counts and funnel metrics.

### `GET /analytics/funnel`

Returns stage conversion data.

### `GET /analytics/skills`

Returns skill trend analysis across saved and applied jobs.

### `GET /analytics/resume-performance`

Returns resume version performance metrics.

### `POST /career-insights/generate`

Queues career intelligence generation.

### `GET /career-insights`

Lists generated insights.

## 12. Integrations

### `GET /integrations`

Lists configured integrations.

### `POST /integrations/{provider}/authorize`

Starts OAuth or provider authorization flow.

### `POST /integrations/{provider}/callback`

Handles provider callback.

### `PATCH /integrations/{integrationId}`

Pauses, resumes, or updates integration settings.

### `DELETE /integrations/{integrationId}`

Revokes and removes integration.

## 13. Job Source Plugins

### `GET /job-sources`

Lists available job source plugins.

### `POST /job-sources/{sourceId}/search`

Searches jobs through a plugin.

### `POST /job-sources/{sourceId}/import`

Imports selected job.

### `GET /job-source-runs`

Lists import runs and failures.

## 14. Email

### `GET /email/messages`

Lists synced job-related messages.

### `POST /email/messages/{messageId}/link`

Links message to application.

### `GET /email/status-suggestions`

Lists proposed status changes.

### `POST /email/status-suggestions/{suggestionId}/accept`

Applies suggestion.

### `POST /email/status-suggestions/{suggestionId}/reject`

Rejects suggestion.

## 15. Calendar

### `GET /calendar/events`

Lists career-related events.

### `POST /calendar/events`

Creates an event.

### `POST /calendar/events/from-interview/{interviewId}`

Creates calendar event from interview details.

## 16. AI Jobs

### `GET /ai/jobs`

Lists generation jobs.

### `GET /ai/jobs/{jobId}`

Returns status, validation result, and output references.

### `POST /ai/jobs/{jobId}/cancel`

Cancels queued or running job.

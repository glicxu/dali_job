# DaliJob API Specification

## 1. API Conventions

- Base path: `/api/v1`.
- Request and response format: JSON unless uploading files.
- Authentication: DaliJob bearer token from `/auth/login` or `/auth/register`; local development may run in `dev` auth mode.
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

DaliJob supports normal email/password registration and login. The client authenticates with DaliJob and sends the returned token on later API requests:

```text
Authorization: Bearer <token>
```

The first implementation stores DaliJob-owned account credentials in the DaliJob database. A future Dalifin-wide login can be introduced by moving identity into a shared auth service or shared identity database, but DaliJob should not require users to first log in through app_server.

### `POST /auth/register`

Creates a DaliJob account and returns a bearer token.

Required body:

```json
{
  "email": "candidate@example.com",
  "password": "strong-password",
  "display_name": "Candidate Name"
}
```

### `POST /auth/login`

Logs in with a DaliJob account and returns a bearer token.

Required body:

```json
{
  "email": "candidate@example.com",
  "password": "strong-password"
}
```

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

Returns the active profile with one `resume_data` JSON document.

### `PATCH /profile`

Replaces the active profile's `resume_data` JSON document. The server validates the expected JSON shape before storage.

Example `resume_data`:

```json
{
  "headline": "Backend Engineer",
  "summary": "Short profile summary.",
  "experience": ["Backend Engineer at Example Co - Built APIs."],
  "skills": ["Python", "FastAPI", "SQL"],
  "education": ["Example University - BS Computer Science"],
  "certifications": [],
  "projects": [],
  "awards": [],
  "publications": [],
  "languages": [],
  "volunteer": [],
  "target_roles": ["Backend Engineer"],
  "notes": []
}
```

### `POST /profile/resume-imports`

Uploads a master resume PDF, cleans extracted text, redacts common personal contact information before AI parsing, and returns a structured `resume_data` JSON suggestion for review. The JSON schema intentionally excludes name, email, phone number, residential location, personal website, and social profile URL fields. The first prototype does not permanently store the uploaded file; document version preservation belongs to the document-management slice.

### `POST /profile/resume-imports/apply`

Applies reviewed resume import suggestions by replacing the active profile's `resume_data` JSON document.

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
  "match_score": 8,
  "missing_skills": [],
  "relevant_projects": [],
  "recommended_resume_changes": [],
  "recommended_study_topics": []
}
```

### `POST /resume-job-matches`

Runs the initial resume-to-job matching prototype. This endpoint compares a master resume against a job description without requiring the full application tracker flow.

The endpoint accepts either pasted resume text or an uploaded resume document ID. It also accepts either pasted job description text or a job URL. When `resume_document_id` is provided, the server uses the latest redacted extracted text from the document library. When `job_url` is provided, the server attempts conservative server-side extraction from public HTML/text pages and rejects private-network URLs.

Pasted text body:

```json
{
  "resume_text": "Resume text pasted by user...",
  "job_description_text": "Job description pasted by user..."
}
```

Uploaded resume and job URL body:

```json
{
  "resume_document_id": "uuid",
  "job_url": "https://example.com/careers/software-engineer"
}
```

Response:

```json
{
  "id": "uuid",
  "match_score": 8,
  "score_scale": "0-10",
  "summary": "Strong backend match with gaps around Kubernetes and observability.",
  "matched_skills": ["Python", "FastAPI", "PostgreSQL", "REST APIs"],
  "missing_skills": ["Kubernetes", "Prometheus"],
  "matched_keywords": ["API design", "SQL", "Docker"],
  "missing_keywords": ["Kubernetes", "monitoring"],
  "supported_requirements": [
    {
      "requirement": "Build REST APIs",
      "resume_evidence": "Built REST APIs with FastAPI and PostgreSQL.",
      "confidence": 0.91
    }
  ],
  "unsupported_requirements": [
    {
      "requirement": "Operate Kubernetes workloads",
      "reason": "No Kubernetes evidence found in resume."
    }
  ],
  "recommended_resume_updates": [
    "Add a stronger backend summary if accurate.",
    "Mention Docker experience near the most relevant project."
  ]
}
```

`match_score` must always be an integer from `0` to `10`, where `0` means no meaningful match and `10` means the resume strongly supports the job's core requirements.

The server should call OpenAI through the AI provider abstraction. The OpenAI API key must come from the server process environment variable `OPENAI_API_KEY`, and the model should come from server-side `ProcessConfig`, not from the client request.

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

The first implemented document slice uses owner-protected API uploads/downloads and local server storage. Production object storage and signed URLs remain future hardening work.

### `POST /documents`

Uploads a PDF or plain text document, stores the original file, creates a document and first document version, and saves redacted extracted text when extraction is supported.

Multipart fields:

- `file`: required PDF or text file.
- `title`: optional document title.
- `document_type`: optional, defaults to `resume`.

### `GET /documents`

Lists documents owned by the current user.

### `GET /documents/{documentId}`

Returns document metadata and latest version metadata.

### `GET /documents/{documentId}/text`

Returns redacted extracted text for the latest version when available. This is intended to support future resume/job matching from stored documents without re-uploading the same file.

### `GET /documents/{documentId}/download`

Downloads the original latest file version. This endpoint is bearer-token protected in the current MVP.

### `POST /documents/upload-url`

Future production endpoint that creates a signed upload URL.

### `GET /documents/{documentId}/download-url`

Future production endpoint that creates a signed download URL.

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

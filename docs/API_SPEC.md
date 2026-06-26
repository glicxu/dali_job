# DaliJob API Specification

## 1. API Conventions

- Base path: `/api/v1`.
- Request and response format: JSON unless uploading files.
- Authentication: DaliJob bearer token from `/auth/login` or `/auth/register`; local development may run in `dev` auth mode.
- Authorization: every request is scoped to a private workspace owned by the authenticated user.
- IDs: integer values.
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

## 3. Resume Profiles

### `GET /resume-profiles`

Lists structured resume profiles owned by the current user. Response ordering should put `is_favorite = true` resumes first, then sort by `updated_at` descending.

### `POST /resume-profiles`

Creates a structured resume profile. The server validates the expected JSON shape before storage and rejects personal contact fields.

### `GET /resume-profiles/{resumeProfileId}`

Returns one structured resume profile.

### `PATCH /resume-profiles/{resumeProfileId}`

Updates title, structured resume JSON, or favorite state. Toggling `is_favorite` must not unset favorites from other resumes because users may favorite multiple resumes.

### `DELETE /resume-profiles/{resumeProfileId}`

Soft-deletes a resume profile when it is not needed anymore.

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

Uploads a master resume PDF, cleans extracted text, redacts common personal contact information before AI parsing, and returns a structured `resume_data` JSON suggestion for review. The JSON schema intentionally excludes name, email, phone number, residential location, personal website, and social profile URL fields. The import response should not overwrite an existing resume profile until the user explicitly applies it.

### `POST /profile/resume-imports/apply`

Applies reviewed resume import suggestions by creating a new `resume_profiles` row or updating a selected existing resume profile.

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

Lists jobs saved by the current user. The API returns saved-job rows from `user_saved_jobs` joined to canonical job details in `jobs_cache`.

Response fields include `id`, `title`, `company`, `source_url`, `raw_description_text`, `job_data`, `notes`, `match_score`, `matched_resume_profile_id`, `matched_resume_document_id`, `matched_resume_source`, `created_at`, and `updated_at`.

`match_score`, `matched_resume_profile_id`, `matched_resume_document_id`, and `matched_resume_source` are response-only convenience fields computed from the current user's latest `job_resume_matches` row for that `user_saved_jobs` record. They are not stored on `user_saved_jobs` or `jobs_cache`.

Future query params:

- `q`
- `company_id`
- `source_provider`
- `remote_policy`
- `skill`
- `limit`
- `cursor`

### `POST /jobs/draft`

Creates a reviewable job draft from either a public URL or pasted job description text. This endpoint parses with OpenAI but does not save the job. If the URL already exists in the job cache, the server returns the cached raw text and structured `job_data` without another OpenAI parsing call.

Body with URL:

```json
{
  "job_url": "https://example.com/careers/software-engineer"
}
```

Body with pasted text:

```json
{
  "job_description_text": "Full job posting text..."
}
```

Response:

```json
{
  "source_url": "https://example.com/careers/software-engineer",
  "raw_description_text": "Cleaned scraped or pasted text...",
  "job_data": {
    "title": "Software Engineer",
    "company": "Example Co",
    "summary": "",
    "responsibilities": [],
    "required_skills": [],
    "preferred_skills": [],
    "required_experience": [],
    "preferred_experience": [],
    "education": [],
    "certifications": [],
    "tools_and_technologies": [],
    "keywords": [],
    "seniority_level": "",
    "employment_type": "",
    "security_clearance": "",
    "work_location": "",
    "salary_range": "",
    "application_deadline": ""
  },
  "fields_missing": ["summary"]
}
```

### `POST /jobs/import-description`

Imports a job description foundation record from pasted text or a public URL. The server stores or reuses the cleaned raw text and OpenAI-parsed structured job JSON in `jobs_cache`, then creates a current-user saved-job row in `user_saved_jobs`. If the URL is already cached, the server reuses the stored cache JSON instead of parsing again. User edits later update only notes on `user_saved_jobs`.

Body with pasted text:

```json
{
  "job_description_text": "Full job posting text..."
}
```

Body with URL:

```json
{
  "job_url": "https://example.com/careers/software-engineer"
}
```

Response:

```json
{
  "id": 1,
  "workspace_id": 1,
  "user_id": 1,
  "jobs_cache_id": 1,
  "title": "Software Engineer",
  "company": "Example Co",
  "source_url": "https://example.com/careers/software-engineer",
  "raw_description_text": "Cleaned scraped or pasted text...",
  "job_data": {
    "title": "Software Engineer",
    "company": "Example Co",
    "summary": "",
    "responsibilities": [],
    "required_skills": [],
    "preferred_skills": [],
    "required_experience": [],
    "preferred_experience": [],
    "education": [],
    "certifications": [],
    "tools_and_technologies": [],
    "keywords": [],
    "seniority_level": "",
    "employment_type": "",
    "security_clearance": "",
    "work_location": "",
    "salary_range": "",
    "application_deadline": ""
  },
  "created_at": "2026-06-19T12:00:00Z",
  "updated_at": "2026-06-19T12:00:00Z"
}
```

### `POST /jobs/import-list/discover`

Discovers individual job posting URLs from a public job search or listing page. This endpoint should not create `jobs_cache` or `user_saved_jobs` rows. It only returns reviewable candidates for the user to select.

Body:

```json
{
  "list_url": "https://example.com/careers/search?query=software",
  "max_results": 25
}
```

Response:

```json
{
  "list_url": "https://example.com/careers/search?query=software",
  "candidates": [
    {
      "title": "Software Engineer",
      "company": "Example Co",
      "source_url": "https://example.com/careers/jobs/123",
      "status": "new",
      "jobs_cache_id": null
    },
    {
      "title": "Data Engineer",
      "company": "Example Co",
      "source_url": "https://example.com/careers/jobs/456",
      "status": "already_cached",
      "jobs_cache_id": 12
    }
  ],
  "next_page_url": "https://example.com/careers/search?query=software&page=2",
  "next_page_confidence": 0.82,
  "warnings": ["Only the first page was scanned."]
}
```

Candidate `status` values:

- `new`
- `already_cached`
- `duplicate`
- `unsupported`
- `failed`

`next_page_url` is optional. When present, the client can call the same discovery endpoint with that URL to append another page of candidates. The server should derive this using generic pagination signals such as `rel="next"`, next-page labels, pagination containers, and common query parameters like `p`, `page`, `pg`, `start`, and `offset`.

### `POST /jobs/import-list`

Imports selected candidates from a prior list discovery result. For each selected job URL, the server should use the normal URL import pipeline: check `jobs_cache`, reuse cached parsed data when possible, otherwise scrape the detail page and parse the job JSON, then create a user-specific `user_saved_jobs` row.

Body:

```json
{
  "list_url": "https://example.com/careers/search?query=software",
  "selected_urls": [
    "https://example.com/careers/jobs/123",
    "https://example.com/careers/jobs/456"
  ],
  "resume_profile_id": 1,
  "run_matching": true
}
```

Response:

```json
{
  "imported": [
    {
      "user_job_id": 31,
      "jobs_cache_id": 12,
      "source_url": "https://example.com/careers/jobs/456",
      "title": "Data Engineer",
      "company": "Example Co",
      "match_score": 7,
      "match_id": 44
    }
  ],
  "failed": [
    {
      "source_url": "https://example.com/careers/jobs/123",
      "reason": "The job detail page could not be extracted."
    }
  ]
}
```

`run_matching` is optional. When it is true, `resume_profile_id` or another supported resume source must be supplied. Bulk import should still work when matching is disabled.

### `POST /jobs`

Creates a saved job from a reviewed draft or fully manual input. If a source URL already exists in `jobs_cache`, the server reuses that cache row and creates a `user_saved_jobs` row. Manual jobs without a URL also create a `jobs_cache` row with a nullable `source_url`. This is a core workflow and does not depend on job board APIs, plugins, or URL extraction.

Body:

```json
{
  "title": "Software Engineer",
  "company": "Example Co",
  "source_url": "https://example.com/jobs/123",
  "raw_description_text": "Full job description...",
  "job_data": {
    "title": "Software Engineer",
    "company": "Example Co",
    "summary": "",
    "responsibilities": [],
    "required_skills": [],
    "preferred_skills": [],
    "required_experience": [],
    "preferred_experience": [],
    "education": [],
    "certifications": [],
    "tools_and_technologies": [],
    "keywords": [],
    "seniority_level": "mid_level",
    "employment_type": "full_time",
    "security_clearance": "",
    "work_location": "Remote",
    "salary_range": "$90,000 - $125,000",
    "application_deadline": "2026-07-01"
  },
  "notes": "Found on company careers page."
}
```

### `GET /jobs/{jobId}`

Returns a job saved by the current user from `user_saved_jobs` joined to `jobs_cache`.

### `PATCH /jobs/{jobId}`

Updates saved-job notes on `user_saved_jobs` only. This never mutates `jobs_cache`; saved job JSON is read-only from the Jobs page.

### `POST /jobs/import-file`

Imports a job description from an uploaded PDF or text file.

### `POST /jobs/{jobId}/analyze`

Queues job analysis.

### `POST /jobs/{jobId}/compare-profile`

Compares job requirements against a selected resume profile.

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

Runs the initial resume-to-job matching prototype. This endpoint compares a selected resume source against a job description without requiring the full application tracker flow.

The endpoint accepts exactly one resume source: `resume_profile_id`, pasted resume text, or an uploaded resume document ID. It also accepts exactly one job source: pasted job description text or a job URL. The UI should block conflicting inputs.

Before scoring, the server parses the job source into structured `job_data` JSON, then compares structured resume JSON against structured job JSON. If the URL already exists in the job cache, the server reuses the stored `job_data` instead of parsing the same URL again. If a structured resume profile is not selected, the server falls back to the supplied resume/document text wrapped as raw resume JSON so the prototype remains usable.

When `job_url` is provided, the server uses broader cleaned visible page extraction for the job parser. When pasted text is provided, that text is parsed the same way.

Save behavior:

- If `match_score >= 5`, the server automatically saves or reuses `jobs_cache`, creates or reuses a `user_saved_jobs` row for the current user, then creates a `job_resume_matches` row with the current user, `user_job_id`, optional `jobs_cache_id`, optional `resume_profile_id`, optional resume document, resume source, score, and match details.
- If `match_score < 5`, the server does not save the job or match immediately. It returns `pending_job`; the UI asks whether to save or discard the low-compatibility job.

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
  "resume_document_id": 1,
  "job_url": "https://example.com/careers/software-engineer"
}
```

Saved resume profile and job URL body:

```json
{
  "resume_profile_id": 1,
  "job_url": "https://example.com/careers/software-engineer"
}
```

Invalid body because both job sources are present:

```json
{
  "resume_document_id": 1,
  "job_url": "https://example.com/careers/software-engineer",
  "job_description_text": "Pasted job text..."
}
```

Response:

```json
{
  "id": 1,
  "saved_job_id": 1,
  "saved_match_id": 1,
  "job_saved": true,
  "pending_job": null,
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

### `POST /resume-job-matches/pending-job`

Saves a low-compatibility `pending_job` returned by `POST /resume-job-matches` after the user confirms they still want to keep it. The server saves or reuses the job, creates a `job_resume_matches` row, and returns:

```json
{
  "saved_job_id": 1,
  "saved_match_id": 1
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
  "document_id": 1,
  "document_version_id": 1,
  "purpose": "submitted"
}
```

## 8. Resume Engine

### `GET /resume-versions`

Lists resume versions.

### `POST /resume-versions/parse`

Queues parsing from an uploaded resume document into structured resume profile data.

### `POST /applications/{applicationId}/resume/tailor`

Queues tailored resume generation.

Body:

```json
{
  "source_resume_profile_id": 1,
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


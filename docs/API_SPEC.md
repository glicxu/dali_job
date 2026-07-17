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

The browser may show signed-out public previews without an access token. Public previews can include the homepage and read-only versions of major app pages, but they must not call protected APIs, OpenAI-backed endpoints, Apify-backed endpoints, scraping endpoints, document upload endpoints, or user data endpoints. Any live action on a protected app page should require a DaliJob bearer token and direct the user to `/auth` when signed out.

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

## 2.5 Homepage Dashboard

### `GET /dashboard`

Returns the signed-in user's homepage summary. The endpoint should be owner-scoped and should not expose other users' saved jobs, resume profiles, or match data.

The dashboard response should be compact so the homepage does not need to fetch all jobs, all resume profiles, and all match rows separately.

Response:

```json
{
  "setup_alerts": [
    {
      "kind": "missing_resume_profile",
      "message": "Create a resume profile before running reliable job matches.",
      "href": "/profile"
    }
  ],
  "recommended_next_step": {
    "kind": "create_resume_profile",
    "label": "Create resume profile",
    "href": "/profile",
    "reason": "Resume profiles are needed before DaliJob can compare jobs against your background."
  },
  "best_matches": [
    {
      "user_saved_job_id": 42,
      "job_cache_id": 18,
      "title": "Software Engineer",
      "company": "Example Co",
      "match_score": 8,
      "resume_profile_id": 7,
      "resume_label": "Backend Resume",
      "match_summary": "Strong backend API match with a gap around Kubernetes.",
      "href": "/jobs?job_id=42&view=match"
    }
  ],
  "recently_saved_jobs": [
    {
      "user_saved_job_id": 43,
      "job_cache_id": 19,
      "title": "Data Engineer",
      "company": "Example Co",
      "source_url": "https://example.com/jobs/data-engineer",
      "status": "needs_analysis",
      "created_at": "2026-07-02T12:00:00Z",
      "href": "/jobs?job_id=43"
    }
  ]
}
```

Dashboard behavior:

- `setup_alerts` should include missing resume-profile setup and may include no saved jobs, saved jobs that need analysis, or analyzed jobs that have no matches.
- `recommended_next_step` should be a single highest-priority action: create/import resume profile, search/import jobs, analyze saved jobs, run matching, or review best matches.
- `best_matches` should use the current user's saved jobs and match rows, sorted by `match_score` descending, then newest match first. Best-match links should open the saved job's match-data view on the Jobs page.
- `recently_saved_jobs` should use `user_saved_jobs.created_at` descending.
- Saved-job links should use a stable user-saved-job identifier, not the shared `jobs_cache` identifier, because notes and match history are user-specific.

## 3. Resume Profiles

### `GET /resume-profiles`

Lists structured resume profiles owned by the current user. Response ordering should put `is_default = true` first, then sort by `updated_at` descending.

### `POST /resume-profiles`

Creates a structured resume profile. The server validates the expected JSON shape before storage and rejects personal contact fields.

### `GET /resume-profiles/{resumeProfileId}`

Returns one structured resume profile.

### `PATCH /resume-profiles/{resumeProfileId}`

Updates title, structured resume JSON, or default state. Setting `is_default = true` must unset the previous default resume for that user because only one resume profile can be default.

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

Lists jobs saved by the current user. The API returns saved-job rows from `user_saved_jobs` with optional joins to reusable URL details in `jobs_cache` and private edited details in `user_edited_jobs`.

Response fields include `id`, `title`, `company`, `source_url`, `raw_description_text`, nullable `job_data`, `notes`, `match_score`, `matched_resume_profile_id`, `matched_resume_document_id`, `matched_resume_source`, `created_at`, and `updated_at`.

`title`, `company`, `source_url`, `raw_description_text`, and `job_data` come from `user_edited_jobs` when `user_saved_jobs.user_edited_job_id` is set; otherwise they come from `jobs_cache`. `match_score`, `matched_resume_profile_id`, `matched_resume_document_id`, and `matched_resume_source` are response-only convenience fields computed from the current user's latest `job_resume_matches` row for that `user_saved_jobs` record.

Future query params:

- `q`
- `company_id`
- `source_provider`
- `remote_policy`
- `skill`
- `limit`
- `cursor`

### `POST /jobs/draft`

Creates a reviewable job draft from either a public URL or pasted job description text. Single-job drafts may parse with OpenAI because the user is actively reviewing one job, but they do not save the job. If the URL already exists in the job cache and structured `job_data` exists, the server returns the cached raw text and structured `job_data` without another OpenAI parsing call. If the cached row has only raw source data, the server may either return the raw draft or lazily parse for the draft view.

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

Imports a job description foundation record from pasted text or a public URL. For one-job URL imports, the server may store or reuse the cleaned raw text and OpenAI-parsed structured job JSON in `jobs_cache`, then creates a current-user saved-job row in `user_saved_jobs` that points at the cache. If the URL is already cached, the server reuses the stored cache row instead of parsing again. Pasted/manual jobs without a URL create a `user_edited_jobs` row and a `user_saved_jobs` row with `jobs_cache_id = null`.

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

Imports selected candidates from a prior list discovery result. For each selected job URL, the server should use the lazy URL import pipeline: check `jobs_cache`, reuse cached source data when possible, otherwise scrape the detail page, save `raw_description_text` and available metadata, then create a user-specific `user_saved_jobs` row pointing at the cache. Bulk import should not call OpenAI just to save jobs. If `run_matching` is true, the server must lazily create missing `jobs_cache.job_data` and then match each imported job.

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

### `POST /job-search/indeed`

Searches Indeed through the server-side Apify integration. This endpoint does not save jobs. It returns normalized reviewable results that the user can inspect before import.

The server reads `APIFY_API_TOKEN` from the server process environment. The token is never accepted from the client and is never returned in responses.

The first implementation targets Apify actor `misceres/indeed-scraper`. In Apify API paths this actor is addressed as `misceres~indeed-scraper`.

Apify run endpoints:

```text
POST https://api.apify.com/v2/acts/misceres~indeed-scraper/runs?token=<APIFY_API_TOKEN>
POST https://api.apify.com/v2/acts/misceres~indeed-scraper/run-sync-get-dataset-items?token=<APIFY_API_TOKEN>
```

The current MVP uses the synchronous dataset-items endpoint for 5-result searches. If Apify runs regularly exceed the server timeout, switch to the async `/runs` endpoint, poll the run, then fetch dataset items.

Apify actor input body:

```json
{
  "position": "web developer",
  "maxItemsPerSearch": 100,
  "country": "US",
  "location": "San Francisco",
  "parseCompanyDetails": false,
  "saveOnlyUniqueItems": true,
  "followApplyRedirects": false
}
```

DaliJob request `keyword` maps to Apify `position`, and DaliJob request `location` maps to Apify `location`. The first implementation uses `country: "US"`, `saveOnlyUniqueItems: true`, `parseCompanyDetails: false`, and `followApplyRedirects: false`. DaliJob caps `maxItemsPerSearch`; the UI default is 5.

Body:

```json
{
  "keyword": "software engineer",
  "location": "Maryland",
  "max_results": 5
}
```

Response:

```json
{
  "provider": "apify_indeed",
  "keyword": "software engineer",
  "location": "Maryland",
  "results": [
    {
      "external_id": "indeed-job-key-or-apify-id",
      "title": "Software Engineer",
      "company": "Example Co",
      "location": "Baltimore, MD",
      "source_url": "https://www.indeed.com/viewjob?jk=example",
      "summary": "Short description preview.",
      "raw_description_text": "Full job description when returned by Apify.",
      "salary_range": "",
      "employment_type": "",
      "posted_at": "",
      "status": "new",
      "jobs_cache_id": null
    }
  ],
  "warnings": []
}
```

Result `status` values:

- `new`
- `already_cached`
- `duplicate`
- `failed`

The server caps `max_results`; the first implementation defaults to 5. Empty Apify datasets, missing `APIFY_API_TOKEN`, actor failures, Apify quota errors, and timeouts return clear structured errors.

### `POST /job-search/indeed/import`

Imports selected Apify-backed search results. The server normalizes each selected result into `raw_description_text` and metadata, reuses an existing `jobs_cache` row by `source_url` when possible, and creates a lightweight `user_saved_jobs` row for the current user. Import should leave `job_data` empty when matching is not requested, then lazily parse and save `jobs_cache.job_data` only when `run_matching` is true or a later match/profile action needs structured data. Manual/no-URL provider results use `user_edited_jobs`.

Body:

```json
{
  "selected_results": [
    {
      "external_id": "indeed-job-key-or-apify-id",
      "title": "Software Engineer",
      "company": "Example Co",
      "location": "Baltimore, MD",
      "source_url": "https://www.indeed.com/viewjob?jk=example",
      "raw_description_text": "Full job description returned by Apify."
    }
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
      "source_url": "https://www.indeed.com/viewjob?jk=example",
      "title": "Software Engineer",
      "company": "Example Co",
      "match_score": 7,
      "match_id": 44
    }
  ],
  "failed": []
}
```

`run_matching` is optional. If it is true, `resume_profile_id` is required for the first implementation.

### `POST /jobs`

Creates a saved job from a reviewed draft or fully manual input. If a source URL is present and the user did not edit the parsed details, the server reuses or creates a `jobs_cache` row and creates a lightweight `user_saved_jobs` row. If the user edited the parsed details, the server also creates a `user_edited_jobs` row and links it from `user_saved_jobs`. Manual jobs without a URL do not create a cache row; they create `user_edited_jobs` plus `user_saved_jobs` with `jobs_cache_id = null`.

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

Returns a job saved by the current user from `user_saved_jobs`, with optional fallback to `jobs_cache`.

### `PATCH /jobs/{jobId}`

Updates notes on `user_saved_jobs`. If the request changes title, company, source URL, raw description text, or `job_data`, the server creates or updates `user_edited_jobs` and links it from `user_saved_jobs`. This never mutates `jobs_cache`.

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

Before scoring, the server ensures the job source has structured `job_data` JSON, then compares structured resume JSON against structured job JSON. If the selected saved job or URL already has cached `job_data`, the server reuses it. If `job_data` is missing but `raw_description_text` exists, the server lazily parses `raw_description_text`, saves the resulting `job_data` to `jobs_cache`, and then runs the match. If parsing fails, the server returns a clear error instead of spending match tokens on unusable job data. If a structured resume profile is not selected, the server falls back to the supplied resume/document text wrapped as raw resume JSON so the prototype remains usable.

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

### `POST /resume-job-matches/saved-jobs`

Runs one selected resume source against multiple already saved jobs. This powers the Saved Jobs `Bulk Match` flow.

The endpoint accepts saved-job IDs from `user_saved_jobs`, not shared `jobs_cache` IDs. The server verifies each selected job belongs to the current user, resolves effective job details from `user_edited_jobs` first and `jobs_cache` second, lazily creates missing structured `job_data` where needed, compares the selected resume against each job, and stores every result in `job_resume_matches`.

Unlike the single ad hoc matcher, low scores are saved immediately because the jobs are already in the user's saved jobs list.

Body:

```json
{
  "user_job_ids": [12, 13, 14],
  "resume_profile_id": 4
}
```

Response:

```json
{
  "matched": [
    {
      "user_job_id": 12,
      "jobs_cache_id": 8,
      "title": "Software Engineer",
      "company": "Example Co",
      "saved_match_id": 31,
      "match": {
        "id": null,
        "saved_job_id": 12,
        "saved_match_id": 31,
        "job_saved": true,
        "pending_job": null,
        "match_score": 8,
        "score_scale": "0-10",
        "summary": "Strong backend match.",
        "matched_skills": ["Python"],
        "missing_skills": [],
        "matched_keywords": ["API"],
        "missing_keywords": [],
        "supported_requirements": [],
        "unsupported_requirements": [],
        "recommended_resume_updates": []
      }
    }
  ],
  "failed": []
}
```

`match_score` must always be an integer from `0` to `10`, where `0` means no meaningful match and `10` means the resume strongly supports the job's core requirements.

The server should call OpenAI through the AI provider abstraction. The OpenAI API key must come from the server process environment variable `OPENAI_API_KEY`, and the model should come from server-side `ProcessConfig`, not from the client request.

## 6. Applications

### `GET /applications`

Lists applications.

Query params:

- `status`
- `stage`
- `include_archived` (default `false`)

### `POST /applications`

Creates an application from an existing saved job (`user_job_id`). If another active application exists, the server returns `409 duplicate_active_application`; retrying with `confirm_duplicate: true` explicitly permits another attempt.

### `GET /applications/{applicationId}`

Returns application details, job, company, documents, timeline, interviews, tasks, and notes.

### `PATCH /applications/{applicationId}`

Updates priority, notes, salary notes, next action, and other metadata.

### `POST /applications/{applicationId}/status`

Changes status using the server-owned transition graph and appends immutable status history and an actor-attributed event. Invalid transitions return `409 invalid_application_transition`.

Body:

```json
{
  "status": "applied",
  "reason": "Submitted through company portal"
}
```

Lifecycle statuses are `interested`, `applied`, `interviewing`, `offer`, `accepted`, `rejected`, and `withdrawn`. Optional stage values are `recruiter_contact`, `assessment`, `phone_screen`, `technical_interview`, and `final_interview`. Archival is not a status.

### `POST /applications/{applicationId}/archive`

Sets `archived_at` without changing lifecycle status.

### `POST /applications/{applicationId}/restore`

Clears `archived_at`. If restoring would create an accidental active duplicate, the server returns `409`; pass `confirm_duplicate: true` to restore intentionally.

### `GET /applications/{applicationId}/events`

Returns timeline events.

### `POST /applications/{applicationId}/notes`

Adds an application note.

### `POST /applications/{applicationId}/tasks`

Creates a typed task with optional `due_at` and `reminder_at` timestamps.

### `GET /applications/{applicationId}/tasks`

Lists tasks. Optional filters are `task_type` and `status=open|completed`.

### `PATCH /applications/{applicationId}/tasks/{taskId}`

Updates title, task type, due time, reminder time, completion, or reminder dismissal. Changing `due_at` or `reminder_at` reschedules the task without replacing it.

### `GET /applications/{applicationId}/documents`

Lists active application attachments with exact document version metadata.

### `POST /applications/{applicationId}/documents`

Attaches an owner-controlled immutable document version.

```json
{
  "document_version_id": 41,
  "purpose": "resume"
}
```

Purpose is `resume`, `cover_letter`, or `supporting`.

### `DELETE /applications/{applicationId}/documents/{attachmentId}`

Soft-detaches the version and appends an application event.

### `POST /applications/{applicationId}/documents/{attachmentId}/download-ticket`

Creates a five-minute, one-time download ticket for the exact attached version. Ticket creation records owner, workspace, application, version, expiration, and later consumption time.

## 7. Documents

Document uploads use owner-protected API requests and local server storage. Downloads use short-lived, one-time opaque tickets so storage paths and long-lived authorization are not exposed to the client.

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

### `POST /documents/{documentId}/versions`

Uploads a replacement PDF or text file as the next immutable version. Existing versions and application attachments are unchanged.

### `POST /documents/upload-url`

Future production endpoint that creates a signed upload URL.

### `POST /documents/{documentId}/download-ticket`

Creates a five-minute, one-time ticket for the latest version.

### `GET /documents/downloads/{token}`

Consumes a valid ticket and streams the pinned file version. The route does not accept a storage path, and a consumed or expired ticket returns `404`.

## 8. Application Material Engine

### `POST /operations/tailored-resume`

Queues evidence-backed tailored-resume generation using `application_id`, exact `source_document_version_id`, and optional `target_notes`.

### `POST /operations/cover-letter`

Queues cover-letter generation using `application_id`, exact `source_document_version_id`, optional exact `source_material_version_id` for a completed tailored resume, and optional `target_notes`.

### `GET /application-materials`

Lists owner-scoped tailored-resume and cover-letter streams with immutable version history. Optional `application_id` filters the list.

### `GET /application-materials/{materialId}`

Returns one material and all versions. Responses include exact source IDs, source file hash, content, evidence warnings, and provider provenance; raw private source snapshots are not returned.

### `POST /application-materials/{materialId}/versions`

Creates a validated user revision from `parent_version_id` and `content_data`. The parent remains immutable.

### `GET /documents/{documentId}/versions`

Lists every immutable owned document version available for exact-version selection.

PDF/DOCX rendering and attaching rendered outputs to applications remain future endpoints.

## 10. Interviews

### `GET /interviews`

Lists owner-scoped interviews. Optional `application_id` filters the list.

### `POST /interviews`

Creates an interview linked to `application_id`. Type, stage, schedule, timezone, duration, location or meeting URL, and private notes are optional.

### `GET /interviews/{interviewId}`

Returns the interview, application job summary, journal notes, and append-only preparation history.

### `PATCH /interviews/{interviewId}`

Updates type, status, stage, schedule, duration, location, outcome, or private notes. This route does not require an AI provider.

### `POST /interviews/{interviewId}/notes`

Adds interview journal notes.

### `POST /operations/interview-prep`

Queues preparation using `interview_id`, `resume_profile_id`, and optional `company_notes`. The server snapshots the selected resume and effective application job before execution and returns a durable managed operation.

### `GET /operations/{operationId}`

Returns progress and the completed structured guide. The guide is also included in `GET /interviews/{interviewId}`. Regeneration appends a new guide instead of replacing older output.

Talking points must cite an exact string from the selected resume snapshot. The server removes unsupported talking points and adds an evidence warning.

### Future: mock interviews

Mock interview sessions are not part of the current API.

## 11. Analytics And Career Intelligence

### `GET /analytics/summary`

Returns owner-scoped descriptive outcome analytics. Optional `start_date` and `end_date` are inclusive local calendar dates interpreted in the account timezone.

The response includes metric contract version and UTC range boundaries; current status counts and monthly trend; response, interview, offer, rejection, and withdrawal rates; response/interview timing; source and exact resume-version performance; formula definitions; and data-quality diagnostics.

Rate denominators contain applications with `applied_at` in range. Outcomes require qualifying status/application events at or after `applied_at`. Groups with fewer than five applications are marked as small samples and are not presented as recommendations.

### `GET /analytics/funnel`

Deferred. The current summary endpoint exposes lifecycle status counts and versioned outcome formulas without claiming a sequential funnel from incomplete history.

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

## 16. Managed Operations

Provider-backed client workflows enqueue through operation-specific endpoints and receive HTTP `202` with a durable operation object. Existing synchronous provider routes remain compatibility endpoints, but the DaliJob client does not use them for costly work.

Enqueue endpoints:

- `POST /operations/job-search`
- `POST /operations/provider-job-import`
- `POST /operations/job-list-discover`
- `POST /operations/job-list-import`
- `POST /operations/resume-parse` (multipart upload)
- `POST /operations/resume-parse/retry`
- `POST /operations/job-draft`
- `POST /operations/job-analyze`
- `POST /operations/resume-job-match`
- `POST /operations/bulk-resume-job-match`

Clients may send `Idempotency-Key`. The server stores only its SHA-256 digest and returns the existing owner-scoped operation for duplicate keys.

### `GET /operations`

Lists the current user's recent operations. Optional filters are `status`, `operation_type`, and `limit`.

### `GET /operations/summary`

Returns owner-scoped status counts and provider failure counts without request payloads, secrets, or raw provider responses.

### `GET /operations/{operationId}`

Returns status, progress, safe errors, provider/model metadata, usage, and the normalized result. It never returns `request_payload`.

### `POST /operations/{operationId}/retry`

Requeues a failed or cancelled operation when it has attempts remaining. The same durable operation ID is retained.

### `POST /operations/{operationId}/cancel`

Cancels queued work immediately or records a cancellation request for running work.


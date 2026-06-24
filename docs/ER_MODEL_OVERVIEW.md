# DaliJob ER Model Overview

This document explains the current DaliJob database model in plain language. It is meant to preserve the design intent behind the tables, not replace the full field-by-field schema in `DATABASE_DESIGN.md`.

## Core Design Rule

Shared/cache data and user-editable data must stay separate.

- `jobs_cache` stores reusable source data from a job URL.
- `user_jobs` stores each user's editable saved job copy.
- `job_resume_matches` stores match results for one user's saved job and resume.
- `resume_profiles` stores each user-owned structured resume, with favorites used only for ordering.

This prevents one user's edits from changing another user's saved job while still letting the app avoid repeated scraping and OpenAI parsing for the same URL.

## Main Entities

### users

Represents a DaliJob account.

Owns or relates to:

- `workspaces`
- `resume_profiles`
- `documents`
- `user_jobs`
- `job_resume_matches`

For the current MVP, a user effectively has one private workspace.

### workspaces

Represents the user's private job-search space.

Owns or groups:

- `resume_profiles`
- `documents`
- `user_jobs`
- `job_resume_matches`

Workspace sharing is intentionally deferred. Keeping `workspaces` still gives the app a future boundary for collaboration, exports, or multiple career-search spaces.

### resume_profiles

Stores one structured resume JSON document per resume.

Relationship:

```text
users/workspaces 1 -> many resume_profiles
resume_profiles optionally references documents/document_versions
resume_profiles 1 -> many job_resume_matches
resume_profiles 1 -> many resume_versions
```

Important behavior:

- Users can have multiple resume profiles.
- Users can favorite zero, one, or many resume profiles.
- Favorites sort to the top of the Profile page and Match page resume selector.
- There is no single required primary resume.
- Personal contact information should be redacted before AI parsing and excluded from saved `resume_data`.

### documents

Stores uploaded document containers, such as a master resume.

Relationship:

```text
documents 1 -> many document_versions
```

### document_versions

Stores exact uploaded file versions and extracted text.

This lets one logical resume document have multiple uploaded versions later.

### jobs_cache

Stores the shared reusable job posting cache.

This table is for source data from URL scraping and OpenAI job parsing. Users should not directly edit this table.

Typical contents:

- `source_url`
- `source_url_hash`
- `title`
- `company`
- `raw_description_text`
- `job_data`

Relationship:

```text
jobs_cache 1 -> many user_jobs
jobs_cache 1 -> many job_resume_matches, optional
```

Purpose:

If multiple users import the same URL, DaliJob can reuse this cached parsed job instead of scraping and parsing again.

### user_jobs

Stores the user's private editable saved job.

This is what the Jobs page should show and edit.

Typical contents:

- `workspace_id`
- `user_id`
- `jobs_cache_id`
- `title`
- `company`
- `source_url`
- `raw_description_text`
- `job_data`
- `notes`

Relationship:

```text
user_jobs belongs to users/workspaces
user_jobs optionally references jobs_cache
user_jobs 1 -> many job_resume_matches
```

Important behavior:

If a user edits job title, skills, requirements, or raw description, the app updates `user_jobs`, not `jobs_cache`.

### job_resume_matches

Stores a match result between one resume source and one user's saved job.

Typical contents:

- `workspace_id`
- `user_id`
- `user_job_id`
- `jobs_cache_id`
- `resume_document_id`
- `resume_profile_id`
- `resume_source`
- `match_score`
- `match_data`

Relationship:

```text
job_resume_matches belongs to users/workspaces
job_resume_matches belongs to user_jobs
job_resume_matches optionally references jobs_cache
job_resume_matches optionally references resume_profiles
job_resume_matches optionally references documents
```

This table should hold scores instead of putting scores on jobs because the same job can have different scores for different users, resumes, or edited job copies.

## Simplified Relationship View

```text
users
  -> workspaces
  -> resume_profiles
  -> documents
       -> document_versions
  -> user_jobs
       -> job_resume_matches

jobs_cache
  -> user_jobs
  -> job_resume_matches
```

## Job Import Flow

When a user imports a job URL:

1. The server hashes the URL and checks `jobs_cache`.
2. If the URL is cached, the server reuses `jobs_cache.job_data` and `jobs_cache.raw_description_text`.
3. If the URL is not cached, the server scrapes the page and asks OpenAI to parse the job into `job_data`.
4. The server creates or reuses a `jobs_cache` row.
5. The server creates a `user_jobs` row by copying the cached data.
6. The user can edit their `user_jobs` copy without changing the cache.

When a user manually creates a job without a URL, the app can create a `user_jobs` row without a `jobs_cache_id`.

## Bulk Job-List Import Flow

When a user imports from a job search or listing URL:

1. The server fetches the listing page and extracts candidate individual job posting URLs.
2. The server normalizes and deduplicates the URLs.
3. The server checks `jobs_cache` for each candidate URL and marks candidates as already cached or new.
4. The client shows the candidates in a review table and the user selects which jobs to import.
5. Each selected detail URL uses the normal Job Import Flow above.
6. Optional batch matching can create `job_resume_matches` rows after the selected jobs are saved to `user_jobs`.

This flow should not store listing-page results as jobs. Only individual job detail pages should create or reuse `jobs_cache` rows. The listing URL is an import source, not a job entity.

## Resume Match Flow

When a user matches a resume to a job:

1. The server resolves the resume from a structured resume profile, uploaded document, or pasted fallback text.
2. The server resolves the job from URL text, pasted text, or an existing `user_jobs` copy.
3. OpenAI compares the resume data with the job data.
4. If the match score is high enough, the job is saved to `user_jobs`.
5. The score and details are stored in `job_resume_matches`.

Matches should link to `user_job_id` because matching should respect the user's edited job copy.

## Design Health Check

The current model is sound for the MVP because:

- Shared URL parsing is cached in `jobs_cache`.
- User edits are isolated in `user_jobs`.
- Resume/job match scores are isolated in `job_resume_matches`.
- Uploaded files and extracted text are versioned through `documents` and `document_versions`.
- Resume profile data is flexible through `resume_profiles.resume_data` JSON.

The main tradeoff is that JSON fields are flexible but harder to query deeply. That is acceptable for the MVP. If analytics later needs heavy querying across skills, requirements, or job fields, selected values can be indexed, derived, or normalized without replacing the current design.

## Future Application Tracking

When application tracking is implemented, add a separate `applications` table instead of overloading `user_jobs`.

Recommended relationship:

```text
user_jobs 1 -> many applications
```

Example application fields:

- `workspace_id`
- `user_id`
- `user_job_id`
- `status`
- `applied_at`
- `next_action_at`
- `notes`
- `created_at`
- `updated_at`

This keeps a saved job separate from a specific application attempt.

## Rules To Preserve

- Do not let user edits mutate `jobs_cache`.
- Use `user_jobs` for the Jobs page and application tracking entry point.
- Use `job_resume_matches` for scores and match details.
- Link matches to `user_job_id`, not only `jobs_cache_id`.
- Prefer linking matches to `resume_profile_id` when the match used a structured saved resume profile.
- Keep uploaded file identity in `documents`, and exact file versions in `document_versions`.
- Keep `resume_profiles.resume_data` free of personal contact information unless the privacy policy changes intentionally.

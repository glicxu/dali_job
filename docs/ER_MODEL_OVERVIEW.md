# DaliJob ER Model Overview

This document explains the current DaliJob database model in plain language. It is meant to preserve the design intent behind the tables, not replace the full field-by-field schema in `DATABASE_DESIGN.md`.

## Core Design Rule

Shared/cache data and user-specific saved data must stay separate.

- `jobs_cache` stores reusable source data from a job URL.
- `user_saved_jobs` stores each user's saved-job relationship and notes.
- `user_edited_jobs` stores manual job details and user-specific corrections.
- `job_resume_matches` stores match results for one user's saved job and resume.
- `resume_profiles` stores each user-owned structured resume, with one default resume used for ordering.
- `managed_operations` stores durable progress and normalized results for provider-backed work.
- `interviews` and `interview_notes` store provider-independent scheduling, outcomes, and private journal entries.
- `interview_prep_guides` stores append-only preparation inputs, outputs, warnings, and provenance.
- `generated_application_materials` identifies one tailored-resume or cover-letter stream per application.
- `generated_application_material_versions` stores immutable AI outputs and user revisions with exact source snapshots.

This prevents user-specific notes and future application tracking from changing the shared cached job while still letting the app avoid repeated scraping and OpenAI parsing for the same URL.

## Main Entities

### users

Represents a DaliJob account.

Owns or relates to:

- `workspaces`
- `resume_profiles`
- `documents`
- `user_saved_jobs`
- `job_resume_matches`
- `managed_operations`
- `interviews`
- `interview_notes`
- `interview_prep_guides`
- `generated_application_materials`
- `generated_application_material_versions`

For the current MVP, a user effectively has one private workspace.

### workspaces

Represents the user's private job-search space.

Owns or groups:

- `resume_profiles`
- `documents`
- `user_saved_jobs`
- `job_resume_matches`
- `managed_operations`

Workspace sharing is intentionally deferred. Keeping `workspaces` still gives the app a future boundary for collaboration, exports, or multiple career-search spaces.

### resume_profiles

Stores one structured resume JSON document per resume.

Relationship:

```text
users/workspaces 1 -> many resume_profiles
resume_profiles optionally references documents/document_versions
resume_profiles 1 -> many job_resume_matches
```

Important behavior:

- Users can have multiple resume profiles.
- Users can have only one default resume profile.
- The default resume sorts to the top of the Profile page and Match page resume selector.
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

Application materials use the exact version relationship:

```text
applications 1 -> many application_documents
document_versions 1 -> many application_documents
document_versions 1 -> many generated_application_material_versions
```

Detaching an application document timestamps the relationship instead of changing or deleting the underlying version. Download access uses short-lived, one-time `document_download_tickets` containing only a hash of the client-visible token.

### generated_application_materials and generated_application_material_versions

`generated_application_materials` is the stable owner record for one material type on one application. Its versions are append-only: regeneration creates another AI version and a user edit creates another user version instead of mutating prior content.

```text
applications 1 -> many generated_application_materials
generated_application_materials 1 -> many generated_application_material_versions
document_versions 1 -> many generated_application_material_versions
generated_application_material_versions 1 -> many child revisions
tailored resume material version 1 -> many cover letter material versions, optional
managed_operations 1 -> 0 or 1 generated_application_material_versions
```

Each material version snapshots redacted extracted resume text and the effective saved-job data at generation time. The direct `source_document_version_id` remains useful for navigation, but the snapshot preserves historical meaning even if an owned document is later soft-deleted. A cover letter can also reference the exact tailored-resume version used as an input. API responses expose source identifiers and hashes, not the private raw snapshots.

### jobs_cache

Stores the shared reusable job posting cache for URL-based imports.

This table is for source data from URL scraping and optional OpenAI job parsing. Users should not directly edit this table. It exists to reduce repeated scraping and token usage when the same URL is imported again.

Typical contents:

- `source_url`
- `source_url_hash`
- `title`
- `company`
- `raw_description_text`
- `job_data`

Relationship:

```text
jobs_cache 1 -> many user_saved_jobs
jobs_cache 1 -> many job_resume_matches, optional
```

Purpose:

If multiple users import the same URL, DaliJob can reuse this cached source data and, once generated, the cached parsed job JSON instead of scraping and parsing again.

### user_saved_jobs

Stores the user's private saved-job relationship and notes.

This table links a user to either shared cache data, private edited data, or both. URL-imported jobs start with `jobs_cache_id` set and `user_edited_job_id` null. Manual jobs use `jobs_cache_id = null` and `user_edited_job_id` set. If a user edits a URL-imported job, DaliJob creates a `user_edited_jobs` row and links it through `user_edited_job_id`.

Typical contents:

- `workspace_id`
- `user_id`
- `jobs_cache_id`
- `user_edited_job_id`
- `notes`

Relationship:

```text
user_saved_jobs belongs to users/workspaces
user_saved_jobs optionally references jobs_cache
user_saved_jobs optionally references user_edited_jobs
user_saved_jobs 1 -> many job_resume_matches
```

Important behavior:

A user can always edit notes on `user_saved_jobs`. Job-detail edits never mutate `jobs_cache`; they create or update `user_edited_jobs`. Matching should prefer `user_edited_jobs.job_data` when linked, otherwise use or lazily generate `jobs_cache.job_data`.

### user_edited_jobs

Stores private job details for manual jobs and user-specific corrections to imported jobs.

Typical contents:

- `workspace_id`
- `user_id`
- `title`
- `company`
- `source_url`
- `raw_description_text`
- `job_data`

Relationship:

```text
user_edited_jobs belongs to users/workspaces
user_edited_jobs 1 -> many user_saved_jobs, usually one
```

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
job_resume_matches belongs to user_saved_jobs
job_resume_matches optionally references jobs_cache
job_resume_matches optionally references resume_profiles
job_resume_matches optionally references documents
```

This table should hold scores instead of putting scores on jobs because the same job can have different scores for different users, resumes, or edited job copies.

### managed_operations

Stores owner-scoped execution state for searches, imports, parsing, and matching. Each operation has a durable status, progress, bounded attempt count, safe error, provider/model metadata, usage counts, and a normalized result. Request payloads remain server-only and are not returned by operation status APIs.

Relationship:

```text
users/workspaces 1 -> many managed_operations
```

The table is workflow history, not a replacement for domain records. A completed import still creates `jobs_cache` and `user_saved_jobs`; a completed match still creates `job_resume_matches`.

### interviews and interview_notes

Each `interviews` row belongs to one application and its private user/workspace owner. Scheduling, type, stage, status, outcome, private summary notes, and append-only journal entries work without any AI provider.

```text
applications 1 -> many interviews
interviews 1 -> many interview_notes
```

### interview_prep_guides

Each generation snapshots one selected `resume_profiles.resume_data`, the application's effective saved-job data, and optional company notes before enqueueing a managed operation. Completed structured output and prompt/model/schema provenance stay on that guide. Regeneration creates another guide rather than overwriting history.

```text
interviews 1 -> many interview_prep_guides
managed_operations 1 -> 0 or 1 interview_prep_guides
resume_profiles 1 -> many interview_prep_guides (nullable source reference)
```

## Simplified Relationship View

```text
users
  -> workspaces
  -> resume_profiles
  -> documents
       -> document_versions
  -> user_saved_jobs
       -> job_resume_matches
  -> managed_operations

jobs_cache
  -> user_saved_jobs
  -> job_resume_matches
```

## Job Import Flow

When a user imports a single job URL:

1. The server hashes the URL and checks `jobs_cache`.
2. If the URL is cached, the server reuses `jobs_cache.raw_description_text` and `jobs_cache.job_data` when present.
3. If the URL is not cached, the server scrapes the page and saves source data into `jobs_cache`.
4. The server creates or reuses a `jobs_cache` row.
5. The server creates a `user_saved_jobs` row that references the cached data.
6. The user can edit notes without creating duplicate job details. If the user edits job details, DaliJob creates or updates a linked `user_edited_jobs` row without changing the shared cached job.

Single-job draft or manual review flows may parse immediately because the user is actively working on one job. Bulk and provider-backed imports should defer OpenAI parsing until matching or structured viewing needs `job_data`.

When a user manually creates a job without a URL, the app creates a `user_edited_jobs` row and a `user_saved_jobs` row with `jobs_cache_id = null`.

## Bulk Job-List Import Flow

When a user imports from a job search or listing URL:

1. The server fetches the listing page and extracts candidate individual job posting URLs.
2. The server normalizes and deduplicates the URLs.
3. The server checks `jobs_cache` for each candidate URL and marks candidates as already cached or new.
4. The client shows the candidates in a review table and the user selects which jobs to import.
5. Each selected detail URL creates or reuses a `jobs_cache` row with source data and creates a lightweight `user_saved_jobs` row that points at the cache.
6. OpenAI parsing is deferred unless the user also requests match-on-import.
7. Optional batch matching lazily parses missing `job_data`, then creates `job_resume_matches` rows after the selected jobs are saved to `user_saved_jobs`.

This flow should not store listing-page results as jobs. Only individual job detail pages should create or reuse `jobs_cache` rows. The listing URL is an import source, not a job entity.

## Resume Match Flow

When a user matches a resume to a job:

1. The server resolves the resume from a structured resume profile, uploaded document, or pasted fallback text.
2. The server resolves the job from URL text, pasted text, or an existing `user_saved_jobs` row with optional joins to `jobs_cache` and `user_edited_jobs`.
3. The server checks whether linked `user_edited_jobs.job_data` exists; otherwise it falls back to `jobs_cache.job_data`.
4. If `job_data` is missing, the server parses the best available `raw_description_text`, saves the result to `user_edited_jobs` for manual/edited jobs or `jobs_cache` for unmodified URL-backed jobs, then matches.
5. OpenAI compares the resume data with the structured job data.
6. If the match score is high enough, the job is saved to `user_saved_jobs`.
7. The score and details are stored in `job_resume_matches`.

Matches should link to `user_job_id` because matching is tied to the user's saved-job relationship.

## Design Health Check

The current model is sound for the MVP because:

- Shared URL source data and reusable parsed job JSON are cached in `jobs_cache`.
- User notes and editable saved-job details are isolated in `user_saved_jobs`.
- Resume/job match scores are isolated in `job_resume_matches`.
- Uploaded files and extracted text are versioned through `documents` and `document_versions`.
- Resume profile data is flexible through `resume_profiles.resume_data` JSON.

The main tradeoff is that JSON fields are flexible but harder to query deeply. That is acceptable for the MVP. If analytics later needs heavy querying across skills, requirements, or job fields, selected values can be indexed, derived, or normalized without replacing the current design.

## Application Tracking

Application tracking uses a separate `applications` table instead of overloading `user_saved_jobs`.

Recommended relationship:

```text
user_saved_jobs 1 -> many applications
```

Example application fields:

- `workspace_id`
- `user_id`
- `user_job_id`
- `status`
- `stage`
- `applied_at`
- `next_action_at`
- `notes`
- `archived_at`
- `created_at`
- `updated_at`

One saved job can have multiple application attempts. Lifecycle status, optional interview stage, and archival are separate concepts. Status history, events, notes, typed tasks, reminders, and immutable document attachments are child entities of an application. A nullable uniqueness guard prevents concurrent accidental active duplicates while allowing explicitly confirmed duplicates and later attempts after terminal or archived outcomes.

Each new application also snapshots its source URL and normalized source label. Outcome analytics use this immutable source label rather than a potentially edited current job record. Legacy applications without a snapshot remain grouped as unknown and produce a data-quality warning.

## Rules To Preserve

- Do not let user edits mutate `jobs_cache`.
- Use `user_saved_jobs` with an optional `jobs_cache` join for the Jobs page and application tracking entry point.
- Use `job_resume_matches` for scores and match details.
- Link matches to `user_job_id`, not only `jobs_cache_id`.
- Prefer linking matches to `resume_profile_id` when the match used a structured saved resume profile.
- Keep uploaded file identity in `documents`, and exact file versions in `document_versions`.
- Keep `resume_profiles.resume_data` free of personal contact information unless the privacy policy changes intentionally.

# DaliJob Database Design

## 1. Design Principles

- Store career facts as structured data.
- Treat generated files as outputs, not canonical data.
- Preserve immutable versions for resumes, cover letters, and submitted documents.
- Scope all user data by a private owner workspace.
- Store application history as events.
- Keep optional integrations loosely coupled.
- Support future analytics without denormalizing too early.
- Treat workspace sharing as a future optional feature, not an MVP requirement.

## 2. Core Conventions

- Primary keys: auto-incrementing integers.
- Timestamps: `created_at`, `updated_at`, and nullable `deleted_at` where soft delete is useful.
- Ownership: every user-owned entity should include `workspace_id` unless it belongs directly to `user`.
- MVP authorization: a workspace has exactly one owner through `workspaces.owner_user_id`.
- Database access should go through `DaliCommonLib.dali_db_man.DbMan`.
- Runtime database selection should come from `DaliCommonLib.dali_config.ProcessConfig`.
- Local and production databases should be swapped by passing different ini files with `--config`.
- Large files: store in object storage and reference by `storage_key`.
- Sensitive integration secrets: encrypt before storing.
- AI outputs: store model provider, model name, prompt version, input references, and validation status.

## 2.1 DaliCommonLib Database Access

The server should not scatter raw database connection strings or independent SQLAlchemy engine creation across modules. Use a local repository layer backed by `DbMan`.

Required pattern:

- Load `ProcessConfig` once during server startup.
- Read SQL database settings from the loaded config file.
- Use `DbMan.get_db_engine()`, `DbMan.get_db_session()`, `DbMan.session_scope()`, or `DbMan.session_dependency()` for SQLAlchemy access.
- Use `DbMan.fetch_dicts()`, `DbMan.fetch_one()`, `DbMan.fetch_scalar()`, `DbMan.write()`, and `DbMan.write_many()` for simple SQL helpers where appropriate.
- Call `DbMan.dispose_all_engines()` during FastAPI shutdown if the function is available.

Current `DbMan` behavior expects a `mysql` config section and builds MySQL-compatible SQLAlchemy URLs through `mysql+pymysql`. If the project later needs PostgreSQL, update or wrap `DbMan` first rather than bypassing the shared database layer.

## 2.2 DaliJob Schema Setup

DaliJob should use its own schema/database, separate from other projects. The default schema name is:

```text
dali_job
```

The actual schema should come from the active config file:

```ini
[mysql]
active_db_schema = dali_job
```

The project should include Python scripts under `scripts/` that load the same config file used by the server and then operate on the configured schema.

Required scripts:

- `scripts/create_schema.py` - create the configured schema/database if it does not exist.
- `scripts/create_tables.py` - create required DaliJob tables, using Alembic or SQLAlchemy metadata once models exist.
- `scripts/seed_database.py` - insert local development seed data.
- `scripts/validate_database.py` - verify required tables and key indexes exist.

All scripts should accept:

```powershell
python scripts/create_schema.py --config local.ini
python scripts/seed_database.py --config local.ini
```

Scripts must use `ProcessConfig` and `DbMan`; they should not hard-code local or production database credentials.

## 3. Enums

### application_status

- `saved`
- `planning`
- `resume_tailored`
- `cover_letter_ready`
- `applied`
- `recruiter_contact`
- `oa_scheduled`
- `oa_completed`
- `phone_screen`
- `technical_interview`
- `final_interview`
- `offer`
- `accepted`
- `rejected`
- `withdrawn`

### document_type

- `resume`
- `cover_letter`
- `portfolio`
- `transcript`
- `reference`
- `job_description`
- `interview_prep`
- `offer_letter`
- `other`

### ai_job_type

- `parse_resume`
- `parse_job_description`
- `compare_resume_to_job`
- `tailor_resume`
- `generate_cover_letter`
- `classify_email`
- `generate_interview_prep`
- `mock_interview`
- `career_insights`

### integration_provider

- `greenhouse`
- `lever`
- `usajobs`
- `adzuna`
- `remotive`
- `gmail`
- `microsoft_email`
- `google_calendar`
- `microsoft_calendar`
- `other`

## 4. Entity Definitions

### users

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| email | text | Unique |
| display_name | text | Required |
| password_hash | text | Nullable for dev/imported users; required for DaliJob local login users |
| auth_provider | text | `dalijob` for local DaliJob accounts; future providers can use a different value |
| is_active | boolean | Required |
| timezone | text | Default `America/New_York` |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable |

### workspaces

For MVP, a workspace is a private data container owned by one user. It is not a shared collaboration space.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| owner_user_id | integer | FK to users |
| name | text | Required |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### resume_profiles

Stores each structured resume profile as one JSON document. A user can have multiple parsed or manually created resume profiles, such as a backend-focused resume, data-focused resume, federal resume, or internship resume.

`resume_profiles.resume_data` intentionally excludes personal contact information such as name, email, phone number, residential location, personal website, and social profile URLs. Uploaded resume text should be redacted before AI parsing, and only non-contact career facts should be stored in the JSON document.

Favorites are a sorting and usability feature, not an ownership or canonical-data rule. A user may favorite zero, one, or many resume profiles. The UI should display favorited resumes first, then non-favorited resumes by most recently updated.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK to workspaces |
| user_id | integer | FK to users |
| title | text | User-facing resume label |
| resume_data | jsonb | Required structured resume JSON |
| source_document_id | integer | Nullable FK to uploaded source resume document |
| source_document_version_id | integer | Nullable FK to exact uploaded source version |
| is_favorite | boolean | Required, default false |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable |

`resume_data` shape:

```json
{
  "headline": null,
  "summary": null,
  "experience": [],
  "skills": [],
  "education": [],
  "certifications": [],
  "projects": [],
  "awards": [],
  "publications": [],
  "languages": [],
  "volunteer": [],
  "target_roles": [],
  "notes": []
}
```

The old normalized profile-section tables (`skills`, `experiences`, `education`, `projects`, `certifications`, `awards`, `publications`, `profile_links`, `experience_bullets`, and `experience_skills`) are intentionally not part of the active schema.

The older one-row `profiles.resume_data` design is intentionally removed. If DaliJob later needs account-level career preferences, add a clearly named table such as `career_preferences` instead of reintroducing ambiguous resume storage.

### companies

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| name | text | Required |
| website_url | text | Nullable |
| industry | text | Nullable |
| size_range | text | Nullable |
| headquarters | text | Nullable |
| description | text | Nullable |
| research_data | jsonb | Company research cache |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### recruiters

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| company_id | integer | Nullable FK |
| name | text | Required |
| email | text | Nullable |
| phone | text | Nullable |
| title | text | Nullable |
| notes | text | Nullable |

### jobs_cache

The implemented `jobs_cache` table stores the canonical job posting data: cleaned raw posting text plus structured `job_data` JSON. It does not contain `user_id`, `workspace_id`, notes, or match scores. It is used to avoid repeated scraping and OpenAI parsing for the same URL. User-facing saved-job ownership and notes live in `user_saved_jobs`, and resume-specific match scores live in `job_resume_matches`.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| title | text | Copied from `job_data.title` for list/filter display |
| company | text | Copied from `job_data.company` for list/filter display |
| source_url | text | Nullable |
| source_url_hash | text | Nullable SHA-256 hash used for efficient URL cache lookup |
| raw_description_text | text | Cleaned text from pasted input or broad URL scraping |
| job_data | jsonb | Structured job description JSON used for matching |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable soft delete |

`job_data` schema:

```json
{
  "title": "",
  "company": "",
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
}
```

Future application tracking may add or derive columns such as `remote_policy`, `closing_date`, `compensation_min`, and `compensation_max` when those fields need filtering/sorting. The cache JSON remains the canonical parsed job description from the original source URL. When a URL has already been parsed, matching and import flows should reuse `jobs_cache.job_data` and `raw_description_text` as the starting point instead of spending another OpenAI job parsing call.

Bulk job-list import does not require a separate core job table for the MVP. A listing URL discovery step should extract individual posting URLs, then each selected posting URL should flow through the same `jobs_cache` lookup and `user_saved_jobs` relationship pipeline. A future `job_import_runs` table can be added if DaliJob needs persistent import history, retry state, or background progress tracking across many pages.

### user_saved_jobs

Stores the current user's saved-job relationship and notes. The Jobs page should query `user_saved_jobs` joined to `jobs_cache`, so the API can return notes and canonical job details in one database query. Users cannot modify `jobs_cache.job_data` from the saved Jobs page.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK user who saved the job |
| jobs_cache_id | integer | Required FK to `jobs_cache` |
| notes | text | Nullable user-specific notes |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable soft delete |

### job_resume_matches

Stores each saved resume-to-job comparison. This table is user-specific and lets multiple resumes or users have different match scores for the same cached job.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK user who ran or saved the match |
| user_job_id | integer | FK to the user's saved job in `user_saved_jobs` |
| jobs_cache_id | integer | Nullable FK to source cache row |
| resume_profile_id | integer | Nullable FK to structured resume profile |
| resume_document_id | integer | Nullable FK to uploaded resume document |
| resume_source | text | `resume_profile`, `document`, `pasted_text`, or future source label |
| match_score | integer | Required 0-10 |
| match_data | jsonb | Structured match details, including matched/missing skills and recommendations when available |
| created_at | timestamptz | Required |

### applications

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_job_id | integer | FK to user's saved editable job |
| company_id | integer | Nullable FK |
| status | application_status | Required |
| priority | text | `low`, `normal`, `high` |
| match_score | integer | Nullable 0-10 |
| salary_notes | text | Nullable |
| applied_at | timestamptz | Nullable |
| next_action_at | timestamptz | Nullable |
| next_action_label | text | Nullable |
| notes | text | Nullable |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| archived_at | timestamptz | Nullable |

### application_status_history

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| from_status | application_status | Nullable |
| to_status | application_status | Required |
| source | text | `user`, `email`, `ai`, `system` |
| reason | text | Nullable |
| created_at | timestamptz | Required |

### resume_job_matches

Future extended comparison result table for application-aware matching, generated resume versions, and AI job traceability. The implemented MVP score persistence uses `job_resume_matches`; this broader table remains a future design target if comparison history needs application links, snapshots, and generation job traceability.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| resume_version_id | integer | Nullable FK |
| resume_document_id | integer | Nullable FK to documents |
| job_id | integer | Nullable FK |
| application_id | integer | Nullable FK |
| source_url | text | Nullable |
| job_description_snapshot | text | Nullable |
| resume_text_snapshot | text | Nullable |
| match_score | integer | Required 0-10 |
| matched_skills | jsonb | Array |
| missing_skills | jsonb | Array |
| matched_keywords | jsonb | Array |
| missing_keywords | jsonb | Array |
| supported_requirements | jsonb | Array |
| unsupported_requirements | jsonb | Array |
| recommendations | jsonb | Array |
| ai_generation_job_id | integer | Nullable FK |
| created_at | timestamptz | Required |

### application_events

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| event_type | text | Required |
| source | text | Required |
| payload | jsonb | Event details |
| created_at | timestamptz | Required |

### documents

Stores uploaded and generated document containers. For a master resume upload, this table identifies the resume as a document, while `document_versions` stores each exact uploaded or rendered file version.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK to users |
| document_type | document_type | Required |
| title | text | Required |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable |

### document_versions

Stores immutable file versions. The first implementation uses local server storage; production can move `storage_path` to an object-storage key. Uploaded master resumes should be stored here before text extraction or parsing. Generated tailored resume files should also be stored here after rendering.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| document_id | integer | FK |
| version_number | integer | Required |
| file_name | text | Required |
| content_type | text | Required |
| size_bytes | integer | Required |
| sha256 | text | SHA-256 |
| storage_path | text | Local path or future object-storage key |
| extracted_text | text | Nullable redacted extracted text |
| created_at | timestamptz | Required |

### resume_versions

Stores immutable structured resume snapshots. A resume version may come from an uploaded master resume, a user-edited profile snapshot, or an AI-tailored version. When the version came from a file upload, `source_document_version_id` links back to the exact uploaded file.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| resume_profile_id | integer | Nullable FK to source resume profile |
| application_id | integer | Nullable FK |
| version_number | integer | Required |
| label | text | Nullable |
| structured_resume | jsonb | Required |
| source_document_version_id | integer | Nullable FK |
| ai_generation_job_id | integer | Nullable FK |
| created_by | text | Required |
| created_at | timestamptz | Required |

### cover_letter_versions

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| application_id | integer | FK |
| resume_version_id | integer | Nullable FK |
| version_number | integer | Required |
| title | text | Required |
| content | text | Required |
| ai_generation_job_id | integer | Nullable FK |
| document_version_id | integer | Nullable FK |
| created_by | text | Required |
| created_at | timestamptz | Required |

### application_documents

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| document_id | integer | FK |
| document_version_id | integer | FK |
| purpose | text | `draft`, `submitted`, `interview_reference`, `other` |
| submitted_at | timestamptz | Nullable |
| created_at | timestamptz | Required |

### interviews

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| interview_type | text | Recruiter, phone, technical, final, mock |
| scheduled_at | timestamptz | Nullable |
| duration_minutes | integer | Nullable |
| location_or_link | text | Nullable |
| outcome | text | Nullable |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### interview_questions

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| interview_id | integer | Nullable FK |
| application_id | integer | FK |
| category | text | Behavioral, technical, coding, etc. |
| question | text | Required |
| suggested_answer | text | Nullable |
| source | text | AI, user, actual |
| created_at | timestamptz | Required |

### interview_notes

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| interview_id | integer | FK |
| notes | text | Required |
| lessons_learned | text | Nullable |
| follow_up_actions | jsonb | Array |
| created_at | timestamptz | Required |

### interview_prep_guides

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| resume_version_id | integer | Nullable FK |
| company_research | jsonb | Required |
| role_analysis | jsonb | Required |
| study_guide | jsonb | Required |
| question_bank | jsonb | Required |
| ai_generation_job_id | integer | Nullable FK |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### tasks

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| application_id | integer | Nullable FK |
| title | text | Required |
| description | text | Nullable |
| due_at | timestamptz | Nullable |
| completed_at | timestamptz | Nullable |
| created_at | timestamptz | Required |

### reminders

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| task_id | integer | Nullable FK |
| application_id | integer | Nullable FK |
| remind_at | timestamptz | Required |
| channel | text | In-app, email, calendar |
| sent_at | timestamptz | Nullable |

### offers

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| salary_amount | numeric | Nullable |
| salary_currency | text | Nullable |
| equity | text | Nullable |
| bonus | text | Nullable |
| benefits | text | Nullable |
| deadline_at | timestamptz | Nullable |
| accepted_at | timestamptz | Nullable |
| declined_at | timestamptz | Nullable |
| notes | text | Nullable |

### analytics_snapshots

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| snapshot_type | text | Funnel, skills, resume performance |
| metrics | jsonb | Required |
| period_start | date | Nullable |
| period_end | date | Nullable |
| created_at | timestamptz | Required |

### integrations

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| provider | integration_provider | Required |
| status | text | `active`, `paused`, `error`, `revoked` |
| account_identifier | text | Nullable |
| encrypted_credentials | text | Nullable |
| scopes | jsonb | Array |
| last_synced_at | timestamptz | Nullable |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### email_messages

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| integration_id | integer | FK |
| provider_message_id | text | Required |
| thread_id | text | Nullable |
| from_address | text | Required |
| subject | text | Required |
| received_at | timestamptz | Required |
| snippet | text | Nullable |
| encrypted_body_storage_key | text | Nullable |
| classification | text | Nullable |
| confidence | numeric | Nullable |
| created_at | timestamptz | Required |

### email_application_links

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| email_message_id | integer | FK |
| application_id | integer | FK |
| match_method | text | Exact, inferred, user confirmed |
| confidence | numeric | Required |
| user_confirmed_at | timestamptz | Nullable |

### calendar_events

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| integration_id | integer | Nullable FK |
| application_id | integer | Nullable FK |
| interview_id | integer | Nullable FK |
| provider_event_id | text | Nullable |
| title | text | Required |
| starts_at | timestamptz | Required |
| ends_at | timestamptz | Nullable |
| location_or_link | text | Nullable |
| created_at | timestamptz | Required |

### ai_generation_jobs

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| job_type | ai_job_type | Required |
| status | text | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| provider | text | Required |
| model | text | Required |
| prompt_version | text | Required |
| input_refs | jsonb | Required |
| output_refs | jsonb | Nullable |
| validation_result | jsonb | Nullable |
| usage | jsonb | Nullable |
| error_message | text | Nullable |
| created_at | timestamptz | Required |
| started_at | timestamptz | Nullable |
| completed_at | timestamptz | Nullable |

## 5. Indexing Recommendations

- `users.email` unique.
- `workspaces.owner_user_id`.
- `jobs_cache.source_url_hash`.
- `user_saved_jobs.workspace_id, user_id`.
- `user_saved_jobs.jobs_cache_id`.
- `job_resume_matches.workspace_id, user_id, created_at`.
- `job_resume_matches.user_job_id`.
- `job_resume_matches.resume_profile_id`.
- `job_resume_matches.resume_document_id`.
- `applications.workspace_id, status`.
- `applications.workspace_id, applied_at`.
- `resume_job_matches.workspace_id, created_at`.
- `resume_job_matches.job_id`.
- `resume_job_matches.application_id`.
- `application_events.application_id, created_at`.
- `document_versions.document_id, version_number` unique.
- `resume_profiles.workspace_id, user_id, is_favorite, updated_at`.
- `resume_versions.workspace_id, resume_profile_id, version_number`.
- `cover_letter_versions.application_id, version_number`.
- `email_messages.integration_id, provider_message_id` unique.
- `email_application_links.email_message_id, application_id` unique.
- JSON indexes on `jobs_cache.job_data`, selected `resume_profiles.resume_data` paths, and analytics JSON fields if needed.

## 6. Versioning Rules

- `resume_versions` are immutable.
- `cover_letter_versions` are immutable.
- `document_versions` are immutable.
- Updating a resume profile does not mutate existing generated resumes.
- Submitted application documents always point to exact version IDs.
- AI-generated versions must link to `ai_generation_jobs`.

## 7. Data Retention

- Soft-delete user-facing records where recovery is useful.
- Hard-delete OAuth credentials immediately when an integration is revoked.
- Allow full workspace export and deletion.
- Retain AI job metadata without storing sensitive prompt payloads unless explicitly required for audit.

## 8. Future Optional Sharing

Sharing is intentionally excluded from the MVP. If DaliJob later supports career coaches, mentors, school career centers, or paid resume reviewers, add a separate sharing model at that time.

Do not add membership tables, shared roles, invitations, or viewer permissions until the product has a clear sharing workflow and privacy model.


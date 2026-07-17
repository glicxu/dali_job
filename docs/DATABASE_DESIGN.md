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
jobs
```

The actual schema should come from the active config file:

```ini
[mysql]
active_db_schema = jobs
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

- `interested`
- `applied`
- `interviewing`
- `offer`
- `accepted`
- `rejected`
- `withdrawn`

Resume/document readiness and interview stage are separate from lifecycle status. Application stage is nullable and limited to `recruiter_contact`, `assessment`, `phone_screen`, `technical_interview`, and `final_interview`. Archival uses `archived_at`, not a status value.

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

Default resume selection is a sorting and usability feature, not an ownership or canonical-data rule. A user may have only one default resume profile. The UI should display the default resume first, then other resumes by most recently updated. When a user creates their first resume profile, DaliJob should make it the default automatically.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK to workspaces |
| user_id | integer | FK to users |
| title | text | User-facing resume label |
| resume_data | jsonb | Required structured resume JSON |
| source_document_id | integer | Nullable FK to uploaded source resume document |
| source_document_version_id | integer | Nullable FK to exact uploaded source version |
| is_default | boolean | Required, default false |
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

The implemented `jobs_cache` table stores reusable job posting source data from URLs: cleaned raw posting text plus optional structured `job_data` JSON. It does not contain `user_id`, `workspace_id`, notes, or match scores. It is used to avoid repeated scraping and repeated OpenAI parsing for the same URL. User-facing saved-job ownership and notes live in `user_saved_jobs`; private manual or edited job details live in `user_edited_jobs`; resume-specific match scores live in `job_resume_matches`.

DaliJob should use lazy job parsing for bulk imports and Apify-backed imports. Those flows should create or reuse a `jobs_cache` row with title, company, source URL, and raw description text first, then leave `job_data` empty until a feature actually needs structured data. When the user runs resume matching or explicitly requests a structured job profile, the backend checks `jobs_cache.job_data`; if it is missing, the backend parses `raw_description_text` with OpenAI, saves the resulting JSON back to `jobs_cache`, and reuses it for future matches/imports.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| title | text | Best known title from source metadata, manual entry, or `job_data.title` after parsing |
| company | text | Best known company from source metadata, manual entry, or `job_data.company` after parsing |
| source_url | text | Nullable |
| source_url_hash | text | Nullable SHA-256 hash used for efficient URL cache lookup |
| raw_description_text | text | Cleaned text from pasted input or broad URL scraping |
| job_data | jsonb | Nullable structured job description JSON used for matching |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable soft delete |

`job_data` is nullable until parsed. When present, it uses this schema:

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

Future application tracking may add or derive columns such as `remote_policy`, `closing_date`, `compensation_min`, and `compensation_max` when those fields need filtering/sorting. The cache JSON remains the reusable parsed job description from the original source URL after parsing has occurred. When a URL has already been parsed, matching and detail flows should reuse `jobs_cache.job_data` and `raw_description_text` instead of spending another OpenAI job parsing call. If a user corrects missing or inaccurate fields, DaliJob stores the correction in `user_edited_jobs` and leaves `jobs_cache` unchanged.

Bulk job-list import does not require a separate core job table for the MVP. A listing URL discovery step extracts individual posting URLs, then each selected posting URL flows through the same `jobs_cache` lookup and `user_saved_jobs` relationship pipeline. Provider-backed search follows the same storage model: returned results are temporary review data until the user imports them, then selected results create or reuse `jobs_cache` rows and create `user_saved_jobs` rows. Bulk imports do not call OpenAI just to save jobs. Search, discovery, import, parsing, and matching execution history lives in `managed_operations` rather than provider-specific run tables.

### managed_operations

Stores owner-scoped execution state for provider-backed work. The request payload is server-only and is not returned by operation read/list endpoints. Results use DaliJob-normalized schemas; provider credentials and raw provider responses are never stored here.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key and durable operation identifier |
| workspace_id | integer | FK to workspaces |
| user_id | integer | FK to users |
| operation_type | text | Normalized workflow name |
| idempotency_key | text | SHA-256 key, unique per owner and operation type |
| status | text | `queued`, `running`, `succeeded`, `failed`, or `cancelled` |
| progress_current | integer | Completed work units |
| progress_total | integer | Nullable total work units |
| progress_message | text | Safe user-facing progress text |
| attempt_count | integer | Number of execution attempts |
| max_attempts | integer | Bounded retry limit, default 3 |
| request_payload | jsonb | Private validated workflow input |
| result_payload | jsonb | Nullable normalized result |
| error_code | text | Nullable safe error category |
| error_message | text | Nullable user-facing failure reason |
| provider | text | Nullable provider category |
| model_or_actor | text | Nullable model or actor identifier |
| prompt_version | text | Nullable prompt contract version |
| usage | jsonb | Counts available from the workflow |
| cancel_requested_at | timestamptz | Nullable cancellation request time |
| started_at | timestamptz | Nullable latest-attempt start time |
| completed_at | timestamptz | Nullable terminal-state time |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

Abandoned queued or running records are converted to retryable `execution_interrupted` failures when operation state is queried. This prevents an interrupted server process from leaving permanent false progress. Successful operations erase `request_payload` immediately. Failed or cancelled operations retain it only for retry and lazily erase it after seven days, at which point the user must start a new operation.

### user_saved_jobs

Stores the current user's saved-job relationship and notes. The Jobs page should query `user_saved_jobs` with optional joins to `jobs_cache` and `user_edited_jobs`, so the API can return notes and effective job details in one database query. Imported URL jobs normally have `jobs_cache_id` set and `user_edited_job_id` null. Manual jobs have `jobs_cache_id` null and `user_edited_job_id` set. Imported jobs that the user later edits keep `jobs_cache_id` set and also receive `user_edited_job_id`.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK user who saved the job |
| jobs_cache_id | integer | Nullable FK to `jobs_cache`; null for manual/user-only jobs |
| user_edited_job_id | integer | Nullable FK to `user_edited_jobs`; set for manual jobs or user-specific edits |
| notes | text | Nullable user-specific notes |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| archived_at | timestamptz | Nullable; hides the saved job while preserving applications and match history |
| deleted_at | timestamptz | Nullable soft delete |

### user_edited_jobs

Stores private user-specific job details only when needed. This table is used for manual jobs and for imported jobs whose title, company, source URL, raw description, or structured JSON has been modified by the user. If `user_saved_jobs.user_edited_job_id` is null, the app displays and matches from `jobs_cache`.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK owner of the edited job detail |
| title | text | User-owned job title |
| company | text | User-owned company |
| source_url | text | Nullable source URL |
| raw_description_text | text | User-owned raw job description text |
| job_data | jsonb | Nullable user-owned structured job JSON used for display and matching |
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
| resume_data_snapshot | jsonb | Immutable structured resume input used for this run |
| job_data_snapshot | jsonb | Immutable effective job JSON used for this run |
| resume_snapshot_hash | text | Canonical SHA-256 used to detect resume staleness |
| job_snapshot_hash | text | Canonical SHA-256 used to detect job staleness |
| provider | text | AI provider name |
| model_name | text | Nullable provider model identifier |
| prompt_version | text | Version of the matching instructions |
| schema_version | text | Version of the structured output contract |
| provider_execution_reference | text | Nullable provider request/completion identifier |
| created_at | timestamptz | Required |

Match records are append-only through product APIs. A rerun creates a new row, and current-vs-snapshot hash comparison determines whether a historical result is stale. See [DATA_LIFECYCLE.md](DATA_LIFECYCLE.md).

### applications

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | FK |
| user_id | integer | FK to owner |
| user_job_id | integer | FK to user's saved editable job |
| source_url_snapshot | text | Nullable immutable source URL captured at application creation |
| source_label_snapshot | text | Nullable normalized source label captured at application creation |
| status | application_status | Required |
| stage | text | Nullable interview stage |
| active_duplicate_guard | integer | Internal nullable uniqueness guard for accidental active duplicates |
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

The server owns transitions: `interested -> applied/withdrawn`, `applied -> interviewing/rejected/withdrawn`, `interviewing -> offer/rejected/withdrawn`, and `offer -> accepted/rejected/withdrawn`. Terminal statuses have no forward transition. A unique constraint on `(workspace_id, user_id, user_job_id, active_duplicate_guard)` protects concurrent unconfirmed active creation; explicitly confirmed duplicates use a null guard.

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

### generated_application_materials

Stores one owner-scoped material stream per application and material type. Current material types are `tailored_resume` and `cover_letter`.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | Owner workspace FK |
| user_id | integer | Owner user FK |
| application_id | integer | Required application FK |
| material_type | text | `tailored_resume` or `cover_letter` |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

The owner, application, and material type combination is unique.

### generated_application_material_versions

Stores immutable AI generations and user revisions. The source snapshots are server-only and preserve the exact redacted resume text and effective job data used at generation time.

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| material_id | integer | FK to generated material stream |
| version_number | integer | Monotonic within material |
| parent_version_id | integer | Nullable self-FK for user revisions |
| operation_id | integer | Nullable unique managed-operation FK |
| source_document_version_id | integer | Exact uploaded resume version FK |
| source_material_version_id | integer | Nullable exact tailored-resume material version used by a cover letter |
| source_resume_snapshot | json | Immutable redacted source and provenance |
| job_snapshot | json | Immutable effective saved-job input |
| request_notes_snapshot | text | Nullable targeting instructions |
| content_data | json | Nullable while generation is pending; typed output when complete |
| version_source | text | `ai` or `user` |
| warnings | json | Evidence-validation and source warnings |
| provider | text | Provider name |
| model_name | text | Nullable model used |
| prompt_version | text | Prompt contract version |
| schema_version | text | Output schema version |
| provider_execution_reference | text | Nullable provider request ID |
| created_at | timestamptz | Required |
| completed_at | timestamptz | Nullable until complete |

### application_documents

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| document_version_id | integer | FK |
| purpose | text | `resume`, `cover_letter`, `supporting` |
| created_at | timestamptz | Required |
| detached_at | timestamptz | Nullable soft detachment |

The exact `document_version_id` is immutable. Uploading a replacement file creates a new `document_versions` row and never changes an existing application attachment.

### document_download_tickets

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key and audit reference |
| workspace_id | integer | FK |
| user_id | integer | FK to authorizing owner |
| document_version_id | integer | Exact downloadable version |
| application_id | integer | Nullable application context |
| token_hash | text | Unique SHA-256 hash; raw token is never stored |
| expires_at | timestamptz | Five-minute expiration |
| consumed_at | timestamptz | Nullable; enforces one-time use |
| created_at | timestamptz | Required |

### interviews

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | Owner workspace FK |
| user_id | integer | Owner user FK |
| application_id | integer | Required application FK |
| interview_type | text | Recruiter screen, phone, technical, behavioral, hiring manager, panel, final, or other |
| status | text | `scheduled`, `completed`, or `cancelled` |
| stage | text | Application-independent interview stage |
| scheduled_at | timestamptz | Nullable |
| timezone | text | Required IANA timezone label |
| duration_minutes | integer | Nullable |
| location_or_url | text | Nullable |
| outcome | text | Nullable advanced, rejected, offer, withdrawn, or no decision |
| private_notes | text | Nullable private summary notes |
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
| body | text | Required journal entry |
| created_at | timestamptz | Required |

### interview_prep_guides

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| workspace_id | integer | Owner workspace FK |
| user_id | integer | Owner user FK |
| interview_id | integer | Required interview FK |
| operation_id | integer | Nullable unique managed-operation FK |
| resume_profile_id | integer | Nullable source profile FK; snapshot remains authoritative |
| resume_data_snapshot | json | Exact structured resume input |
| job_data_snapshot | json | Exact effective saved-job input, including raw text when available |
| company_notes_snapshot | text | Nullable user-supplied company context |
| source_warnings | json | Warnings captured before provider execution |
| output_data | json | Nullable structured priorities, questions, talking points, and gaps |
| provider | text | Provider name |
| model_name | text | Nullable model used |
| prompt_version | text | Prompt contract version |
| schema_version | text | Output contract version |
| provider_execution_reference | text | Nullable provider trace reference |
| created_at | timestamptz | Required |
| completed_at | timestamptz | Nullable completion time |

Prep-guide rows are append-only through product APIs. Regeneration creates a new row and preserves each run's exact resume, job, and company-note inputs.

### application_tasks

| Field | Type | Notes |
| --- | --- | --- |
| id | integer | Primary key |
| application_id | integer | FK |
| title | text | Required |
| task_type | text | `follow_up`, `interview_prep`, `document`, `deadline`, `other` |
| due_at | timestamptz | Nullable |
| reminder_at | timestamptz | Nullable in-app reminder time |
| reminder_dismissed_at | timestamptz | Nullable |
| completed_at | timestamptz | Nullable |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required for support diagnostics |

Reminder state remains on `application_tasks` for the in-app implementation. A separate delivery table is unnecessary until external notification channels are introduced.

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

Future optional persistence for expensive or historical aggregate snapshots. Phase 6 does not create this table: `GET /analytics/summary` calculates owner-scoped `outcome-analytics-v1` results from applications, status/application events, application-time source snapshots, and exact attached document versions on request.

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
- `resume_profiles.workspace_id, user_id, is_default, updated_at`.
- `generated_application_materials.workspace_id, user_id, application_id, material_type`.
- `generated_application_material_versions.material_id, version_number`.
- `generated_application_material_versions.source_document_version_id`.
- `email_messages.integration_id, provider_message_id` unique.
- `email_application_links.email_message_id, application_id` unique.
- JSON indexes on `jobs_cache.job_data`, selected `resume_profiles.resume_data` paths, and analytics JSON fields if needed.

## 6. Versioning Rules

- `generated_application_material_versions` are immutable; edits create child versions.
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


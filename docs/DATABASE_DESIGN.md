# CareerOS Database Design

## 1. Design Principles

- Store career facts as structured data.
- Treat generated files as outputs, not canonical data.
- Preserve immutable versions for resumes, cover letters, and submitted documents.
- Scope all user data by workspace.
- Store application history as events.
- Keep optional integrations loosely coupled.
- Support future analytics without denormalizing too early.

## 2. Core Conventions

- Primary keys: UUID.
- Timestamps: `created_at`, `updated_at`, and nullable `deleted_at` where soft delete is useful.
- Ownership: every user-owned entity should include `workspace_id` unless it belongs directly to `user`.
- Large files: store in object storage and reference by `storage_key`.
- Sensitive integration secrets: encrypt before storing.
- AI outputs: store model provider, model name, prompt version, input references, and validation status.

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
| id | uuid | Primary key |
| email | text | Unique |
| display_name | text | Required |
| timezone | text | Default `America/New_York` |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |
| deleted_at | timestamptz | Nullable |

### workspaces

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| owner_user_id | uuid | FK to users |
| name | text | Required |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### workspace_members

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK to workspaces |
| user_id | uuid | FK to users |
| role | text | `owner`, `admin`, `member`, `viewer` |
| created_at | timestamptz | Required |

### profiles

The canonical user career profile.

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK to workspaces |
| user_id | uuid | FK to users |
| headline | text | Nullable |
| summary | text | Nullable |
| target_roles | jsonb | Array |
| target_locations | jsonb | Array |
| remote_preference | text | Nullable |
| salary_expectations | jsonb | Nullable |
| portfolio_links | jsonb | Array |
| preferences | jsonb | Document style and search prefs |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### skills

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| name | text | Required |
| category | text | e.g. language, framework, tool, soft skill |
| normalized_name | text | For deduplication |
| created_at | timestamptz | Required |

### experiences

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| company_name | text | Required |
| title | text | Required |
| location | text | Nullable |
| start_date | date | Nullable |
| end_date | date | Nullable |
| is_current | boolean | Required |
| description | text | Nullable |
| sort_order | integer | Required |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### experience_bullets

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| experience_id | uuid | FK |
| text | text | Required |
| impact_metric | text | Nullable |
| evidence_level | text | `verified`, `user_claimed`, `ai_inferred`, `needs_review` |
| sort_order | integer | Required |
| created_at | timestamptz | Required |

### experience_skills

| Field | Type | Notes |
| --- | --- | --- |
| experience_id | uuid | FK |
| skill_id | uuid | FK |

### education

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| institution | text | Required |
| degree | text | Nullable |
| field_of_study | text | Nullable |
| start_date | date | Nullable |
| end_date | date | Nullable |
| notes | text | Nullable |

### projects

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| name | text | Required |
| description | text | Nullable |
| url | text | Nullable |
| repository_url | text | Nullable |
| start_date | date | Nullable |
| end_date | date | Nullable |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### certifications

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| name | text | Required |
| issuer | text | Nullable |
| issued_at | date | Nullable |
| expires_at | date | Nullable |
| credential_url | text | Nullable |

### awards

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| title | text | Required |
| issuer | text | Nullable |
| awarded_at | date | Nullable |
| description | text | Nullable |

### publications

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| profile_id | uuid | FK |
| title | text | Required |
| publisher | text | Nullable |
| published_at | date | Nullable |
| url | text | Nullable |
| description | text | Nullable |

### companies

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
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
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| company_id | uuid | Nullable FK |
| name | text | Required |
| email | text | Nullable |
| phone | text | Nullable |
| title | text | Nullable |
| notes | text | Nullable |

### jobs

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| company_id | uuid | Nullable FK |
| source_provider | text | Manual, plugin, URL, PDF, paste |
| source_url | text | Nullable |
| external_id | text | Nullable |
| title | text | Required |
| description_raw | text | Required |
| description_structured | jsonb | Parsed model |
| location | text | Nullable |
| remote_policy | text | `unknown`, `onsite`, `hybrid`, `remote` |
| employment_type | text | Nullable |
| seniority | text | Nullable |
| compensation_min | numeric | Nullable |
| compensation_max | numeric | Nullable |
| compensation_currency | text | Nullable |
| captured_at | timestamptz | Required |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### applications

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| job_id | uuid | FK |
| company_id | uuid | Nullable FK |
| status | application_status | Required |
| priority | text | `low`, `normal`, `high` |
| match_score | integer | Nullable 0-100 |
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
| id | uuid | Primary key |
| application_id | uuid | FK |
| from_status | application_status | Nullable |
| to_status | application_status | Required |
| source | text | `user`, `email`, `ai`, `system` |
| reason | text | Nullable |
| created_at | timestamptz | Required |

### application_events

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| application_id | uuid | FK |
| event_type | text | Required |
| source | text | Required |
| payload | jsonb | Event details |
| created_at | timestamptz | Required |

### documents

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| document_type | document_type | Required |
| title | text | Required |
| current_version_id | uuid | Nullable FK to document_versions |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### document_versions

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| document_id | uuid | FK |
| version_number | integer | Required |
| storage_key | text | Required |
| mime_type | text | Required |
| file_name | text | Required |
| file_size_bytes | bigint | Required |
| content_hash | text | SHA-256 |
| created_by | text | User, AI, renderer, import |
| ai_generation_job_id | uuid | Nullable FK |
| created_at | timestamptz | Required |

### resume_versions

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| profile_id | uuid | FK |
| application_id | uuid | Nullable FK |
| version_number | integer | Required |
| label | text | Nullable |
| structured_resume | jsonb | Required |
| source_document_version_id | uuid | Nullable FK |
| ai_generation_job_id | uuid | Nullable FK |
| created_by | text | Required |
| created_at | timestamptz | Required |

### cover_letter_versions

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| application_id | uuid | FK |
| resume_version_id | uuid | Nullable FK |
| version_number | integer | Required |
| title | text | Required |
| content | text | Required |
| ai_generation_job_id | uuid | Nullable FK |
| document_version_id | uuid | Nullable FK |
| created_by | text | Required |
| created_at | timestamptz | Required |

### application_documents

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| application_id | uuid | FK |
| document_id | uuid | FK |
| document_version_id | uuid | FK |
| purpose | text | `draft`, `submitted`, `interview_reference`, `other` |
| submitted_at | timestamptz | Nullable |
| created_at | timestamptz | Required |

### interviews

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| application_id | uuid | FK |
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
| id | uuid | Primary key |
| interview_id | uuid | Nullable FK |
| application_id | uuid | FK |
| category | text | Behavioral, technical, coding, etc. |
| question | text | Required |
| suggested_answer | text | Nullable |
| source | text | AI, user, actual |
| created_at | timestamptz | Required |

### interview_notes

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| interview_id | uuid | FK |
| notes | text | Required |
| lessons_learned | text | Nullable |
| follow_up_actions | jsonb | Array |
| created_at | timestamptz | Required |

### interview_prep_guides

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| application_id | uuid | FK |
| resume_version_id | uuid | Nullable FK |
| company_research | jsonb | Required |
| role_analysis | jsonb | Required |
| study_guide | jsonb | Required |
| question_bank | jsonb | Required |
| ai_generation_job_id | uuid | Nullable FK |
| created_at | timestamptz | Required |
| updated_at | timestamptz | Required |

### tasks

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| application_id | uuid | Nullable FK |
| title | text | Required |
| description | text | Nullable |
| due_at | timestamptz | Nullable |
| completed_at | timestamptz | Nullable |
| created_at | timestamptz | Required |

### reminders

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| task_id | uuid | Nullable FK |
| application_id | uuid | Nullable FK |
| remind_at | timestamptz | Required |
| channel | text | In-app, email, calendar |
| sent_at | timestamptz | Nullable |

### offers

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| application_id | uuid | FK |
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
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| snapshot_type | text | Funnel, skills, resume performance |
| metrics | jsonb | Required |
| period_start | date | Nullable |
| period_end | date | Nullable |
| created_at | timestamptz | Required |

### integrations

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
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
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| integration_id | uuid | FK |
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
| id | uuid | Primary key |
| email_message_id | uuid | FK |
| application_id | uuid | FK |
| match_method | text | Exact, inferred, user confirmed |
| confidence | numeric | Required |
| user_confirmed_at | timestamptz | Nullable |

### calendar_events

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
| integration_id | uuid | Nullable FK |
| application_id | uuid | Nullable FK |
| interview_id | uuid | Nullable FK |
| provider_event_id | text | Nullable |
| title | text | Required |
| starts_at | timestamptz | Required |
| ends_at | timestamptz | Nullable |
| location_or_link | text | Nullable |
| created_at | timestamptz | Required |

### ai_generation_jobs

| Field | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| workspace_id | uuid | FK |
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
- `workspace_members.workspace_id, user_id` unique.
- `jobs.workspace_id, title`.
- `jobs.workspace_id, company_id`.
- `applications.workspace_id, status`.
- `applications.workspace_id, applied_at`.
- `application_events.application_id, created_at`.
- `document_versions.document_id, version_number` unique.
- `resume_versions.workspace_id, profile_id, version_number`.
- `cover_letter_versions.application_id, version_number`.
- `email_messages.integration_id, provider_message_id` unique.
- `email_application_links.email_message_id, application_id` unique.
- GIN indexes on `jobs.description_structured`, `profiles.preferences`, and analytics JSONB fields if needed.

## 6. Versioning Rules

- `resume_versions` are immutable.
- `cover_letter_versions` are immutable.
- `document_versions` are immutable.
- Updating the profile does not mutate existing generated resumes.
- Submitted application documents always point to exact version IDs.
- AI-generated versions must link to `ai_generation_jobs`.

## 7. Data Retention

- Soft-delete user-facing records where recovery is useful.
- Hard-delete OAuth credentials immediately when an integration is revoked.
- Allow full workspace export and deletion.
- Retain AI job metadata without storing sensitive prompt payloads unless explicitly required for audit.

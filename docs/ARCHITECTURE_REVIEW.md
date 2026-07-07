# DaliJob Architecture Review

This review captures the current functional and architectural state of DaliJob and highlights useful next steps, risks, and low-value areas to avoid overbuilding.

## Current Assessment

DaliJob has a reasonable MVP foundation:

- Server/client separation with FastAPI under `server/` and Next.js under `client/`.
- Local DaliJob authentication with signed-out read-only previews.
- Resume PDF upload, document storage, and parsed resume profiles.
- Multiple resume profiles with one default used for ordering.
- Shared `jobs_cache` for reusable URL-backed job source data.
- `user_saved_jobs` for user ownership, notes, and saved-job relationships.
- `user_edited_jobs` for manual jobs and user-specific corrections.
- Lazy OpenAI parsing of job descriptions.
- Resume-to-job matching with stored match results in `job_resume_matches`.
- Job search through a provider-backed import path.
- Dashboard with setup alerts, next step, best matches, and recently saved jobs.

The current architecture is directionally sound. The next improvements should focus less on adding more scraping behavior and more on tightening data ownership, authentication safety, long-running work, and true application tracking.

## Main Risks

### Shared Cache Integrity

`jobs_cache` is intended to store shared source data that can be reused across users. User-specific job corrections should live in `user_edited_jobs`.

The backend should enforce this boundary. It should not rely only on a client-provided flag to decide whether submitted job data is safe to write into `jobs_cache`. If the server accepts user-edited title, company, raw text, or `job_data` as shared cache data, one user's corrections could affect other users who later import the same URL.

Recommended fix:

- Treat `jobs_cache` as source-owned or system-owned data.
- Only write scraped/provider-returned source data to `jobs_cache`.
- Write manual entries and user corrections to `user_edited_jobs`.
- If a draft is editable before save, compare it server-side to the source draft before deciding where it belongs.

### Production Auth Safety

The server supports development identity modes. This is useful locally but risky in production.

Recommended fix:

- Fail startup in production if `auth_mode` is `dev` or `disabled`.
- Fail startup if the default JWT secret is still configured.
- Keep signed-out previews in the client, but require authenticated API calls for AI, scraping, uploads, saved jobs, profile writes, and dashboard data.

### Long-Running Requests

OpenAI parsing, matching, bulk matching, Apify searches, and URL scraping currently happen inside API request lifecycles. This is acceptable for early MVP testing, but it will become fragile as imports get larger.

Recommended fix:

- Introduce background jobs for bulk import, bulk match, provider searches, and large parsing tasks.
- Store job status, progress, failures, and retry state.
- Let the UI poll or subscribe for progress.

### Match Result Versioning

`job_resume_matches` stores score and match details, but a match can become misleading if the related resume profile or job data changes later.

Recommended fix:

- Add match-time snapshots of the resume JSON and job JSON, or
- Add version tables for resume profiles and user-edited jobs, then link matches to exact versions.

This becomes more important once match history is used for analytics or decision-making.

### Provider Coupling

The UI now uses generic job-search wording, but the backend implementation is currently shaped around one provider.

Recommended fix:

- Define a `JobSearchProvider` interface.
- Normalize every provider result into DaliJob's internal job-search result schema.
- Keep provider details out of client-facing contracts where practical.

## Functional Gaps

### Application Tracking

Saved jobs and matches are not the same as applications. The original product vision needs a dedicated application-tracking model.

Recommended future table:

- `applications`

Useful fields:

- `id`
- `workspace_id`
- `user_id`
- `user_saved_job_id`
- `status`
- `applied_at`
- `deadline`
- `next_action_at`
- `contact_name`
- `contact_email`
- `interview_at`
- `offer_status`
- `rejection_at`
- `notes`
- `created_at`
- `updated_at`
- `deleted_at`

This should be added separately instead of overloading `user_saved_jobs`.

### Reminders And Deadlines

Deadline data is useful only if the app can act on it.

Recommended features:

- Deadline reminders.
- Follow-up reminders.
- Interview reminders.
- Next action reminders.

### Email Status Ingestion

Email reading was part of the original vision but should wait until application tracking exists.

Recommended approach:

- First implement application statuses.
- Then add email classification that maps messages to application events such as interview request, rejection, assessment, offer, or follow-up.
- Require user approval before automatic state changes, at least in the first version.

### Interview Preparation

After matching, the next strong AI feature is interview preparation from the saved job, resume profile, and company context.

Useful outputs:

- Study guide.
- Likely interview questions.
- Resume talking points.
- Skill gaps to review.
- Company/product research notes.

### Privacy And Account Controls

DaliJob stores sensitive resume and career data.

Recommended features:

- Full account export.
- Full account deletion.
- Document deletion.
- Saved job deletion or archive.
- Clear storage policy for raw scraped text, uploaded documents, and AI outputs.

### Cost And Rate Controls

OpenAI and Apify usage should be controlled before broader use.

Recommended features:

- Per-user usage counters.
- Provider call logging.
- Daily or monthly caps.
- Clear UI feedback when a feature will spend credits.

## Low-Value Or Deferrable Areas

### Universal Scraping

Generic scraping is useful as a fallback, but trying to make it reliable across every job board is likely low return. Some sites require login, block automation, or render content inconsistently.

Recommended direction:

- Keep URL scraping and URL Debug as fallback/developer tools.
- Prefer provider APIs, manual paste, and supported source integrations.

### URL Debug In Normal Navigation

`URL Debug` is useful for development but not a normal user feature.

Recommended fix:

- Hide it behind a development flag or move it to an admin/developer area.

### Workspace Sharing

Private workspaces are useful as an ownership boundary. Collaboration roles are not currently needed.

Recommended direction:

- Keep the private workspace model.
- Defer shared workspaces, admins, members, and viewers until a real collaboration feature is designed.

### Complex Document Versioning UI

Documents and resume profiles are important. A large document-versioning interface is probably not worth building before application tracking and resume tailoring are mature.

Recommended direction:

- Keep source document links.
- Add deeper version UI only when generated resume versions and application-specific documents are implemented.

## Recommended Next Build Order

1. Harden production authentication rules.
2. Enforce `jobs_cache` versus `user_edited_jobs` boundaries on the server.
3. Add application tracking as a separate product area.
4. Add deletion/archive/export controls for user-owned data.
5. Add match snapshots or version references.
6. Move bulk import, bulk match, provider search, and expensive AI work to background jobs.
7. Add interview preparation once saved jobs, resume profiles, and application tracking are stable.

## Architectural Principle

DaliJob should separate shared source facts from user-owned decisions.

- `jobs_cache` should represent reusable source data.
- `user_saved_jobs` should represent a user's relationship to a job.
- `user_edited_jobs` should represent private user corrections or manual jobs.
- `resume_profiles` should represent user-owned resume JSON.
- `job_resume_matches` should represent a comparison result for a specific user, job, and resume.
- Future `applications` should represent actual application progress.

Keeping those boundaries clear will make the app easier to extend without corrupting shared data or mixing product concepts together.

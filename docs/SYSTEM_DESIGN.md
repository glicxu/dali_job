# DaliJob System Design

## 1. Executive Summary

DaliJob is an AI-assisted career management platform that acts as the single source of truth for a user's career search. It helps users import opportunities, analyze roles, tailor documents, track applications, prepare for interviews, record outcomes, and learn from historical data.

DaliJob is not a job board and not simply a resume builder. Job aggregation is optional. AI is a supporting system, not the core product. The app must continue to work when AI providers, email integrations, calendar integrations, or job-source plugins are unavailable.

## 2. Product Principles

- The user's structured resume profiles are the canonical source of truth for resume facts.
- Generated resumes, cover letters, and study guides are outputs derived from structured data.
- AI may rephrase, reorder, emphasize, and summarize. AI may not invent skills, projects, experience, employment, certifications, education, metrics, or dates.
- Every application should preserve the exact resume, cover letter, documents, and notes used for that opportunity.
- External systems such as job boards, email providers, calendar providers, and AI providers must be isolated behind adapters.
- Long-term analytics and career intelligence should improve future applications without making unsupported claims.

## 3. Primary User Journey

```text
Opportunity
  -> Import
  -> Analyze
  -> Tailor Resume
  -> Generate Cover Letter
  -> Apply
  -> Track Progress
  -> Prepare For Interviews
  -> Record Results
  -> Generate Insights
  -> Improve Future Applications
```

## 4. Major Modules

### 4.0 Initial Resume-To-Job Match Prototype

The first functional build should be a narrow prototype before the full application tracker is implemented. Its purpose is to prove that DaliJob can compare a user's master resume against a job description and return useful matching feedback.

Prototype workflow:

```text
User opens barebones client UI
  -> Selects a structured resume profile, uploaded master resume document, or pasted resume text
  -> Pastes either a job description URL or job description text, never both
  -> Server loads the selected structured resume profile JSON when available
  -> Server extracts broad job page text from the URL or accepts pasted fallback text
  -> Server reuses cached job_data when the URL is already stored, otherwise OpenAI parses the job text into structured job_data JSON
  -> OpenAI-backed comparison service compares resume JSON against job_data JSON
  -> Match engine returns score from 0 to 10
  -> If score is 5 or higher, server saves or reuses jobs_cache, creates a user_saved_jobs row, and stores the score/resume reference in job_resume_matches
  -> If score is below 5, UI asks whether to save or discard the low-compatibility job
  -> UI displays score, matched skills, missing skills, keyword overlap, and recommendations
```

Score meaning:

- `0`: no meaningful overlap between resume and job description.
- `5`: partial match with several important gaps.
- `10`: excellent match where the resume strongly supports the job's core requirements.

The first prototype started with pasted text only. After document management is available, the matcher should support selecting a structured resume profile or uploaded resume document and pasting a job URL, while retaining pasted text fallbacks for pages that block extraction. The resume selector should list favorited resume profiles first, followed by other resume profiles, uploaded resume documents, and pasted-text fallback. The job URL field and pasted job description field should be mutually exclusive. In either mode, the server should save high-compatibility jobs automatically and let the user decide whether to save jobs with a score below 5. `jobs_cache` is the canonical job detail cache, `user_saved_jobs` stores each user's saved-job relationship and notes, and match scores are user/resume-specific in `job_resume_matches`.

The comparison should use the OpenAI API through the server-side AI provider abstraction. The OpenAI API key must be read from the server process environment variable `OPENAI_API_KEY`, never from the client and never from a committed config file. The model name should be configurable through `ProcessConfig` so it can be changed without code edits.

This prototype should still preserve the client/server split: the client submits source selections through the API, and the server performs URL fetching, AI parsing, scoring, validation, and persistence.

### 4.1 Resume Profiles Module

Stores multiple structured resume profiles that power resume generation, cover letters, study guides, matching, and analytics.

There is no separate `profiles` table in the active schema. If DaliJob later needs account-level career preferences, add a clearly named table such as `career_preferences`.

Each `resume_profiles.resume_data` object contains sections such as:

- Education.
- Work experience.
- Projects.
- Skills.
- Certifications.
- Awards.
- Publications.
- Preferences such as target roles, remote policy, industries, salary expectations, and document style.

Resume profile JSON should avoid storing personal contact information. Name, email address, phone number, residential location, personal websites, and social profile URLs should be redacted from uploaded resume text before AI parsing and excluded from `resume_profiles.resume_data`.

DaliJob should not require one primary resume. Users can star or favorite any number of resume profiles. The profile page and resume selectors should sort favorited resumes first, then non-favorited resumes by most recently updated. Favorites are a UI prioritization signal only; they do not prevent the user from matching, editing, tailoring, or applying with any resume profile.

### 4.2 Career Knowledge Base

Stores all career-search artifacts in one structured system.

Knowledge base contents:

- Jobs.
- Applications.
- Companies.
- Recruiters and contacts.
- Notes.
- Documents.
- Resume versions.
- Cover letter versions.
- Interview questions.
- Study guides.
- Learning resources.
- Interview feedback.
- Offers.
- Rejections.
- Tasks and reminders.

### 4.3 Job Import Module

Job aggregation is optional. DaliJob must support manual import without any aggregator.

Supported import methods:

- Paste job URL and let the server attempt to extract the job details from the page.
- Paste a job search or listing URL, let the server discover individual job posting URLs, review the discovered jobs, and import selected jobs in bulk.
- Fully manual job entry where the user types or pastes title, company, description, deadline, location, salary, source URL, and notes.
- Upload PDF job description.
- Copy and paste job description.
- Search Indeed through a server-side Apify integration, review returned jobs, and import selected jobs.
- Import from supported integrations.
- Optional aggregation plugins.

Manual entry is a core workflow, not a fallback-only feature. A user must be able to track a job even when it comes from a company website, recruiter email, private posting, personal referral, PDF, or any site that does not have a job search API.

URL extraction is a convenience feature. If the page cannot be fetched, blocks automated access, requires authentication, renders content client-side, or does not expose parseable job data, DaliJob should keep the URL and let the user manually fill or paste the missing fields. URL extraction must not be required for application tracking.

The implemented job import flow creates reviewable drafts from URL or pasted text before saving. Users can also start with a blank manual job form. Saved jobs are represented by `user_saved_jobs` rows that reference `jobs_cache` rows, so the same URL can appear in multiple users' job lists without refetching or reparsing the posting while still allowing private user notes.

Bulk job-list import should be a separate workflow from the one-job Match page. The Match page remains focused on comparing one resume against one job source. Bulk import belongs on a dedicated page such as `/jobs/import` or a clearly separated Jobs page section because it has a review/select/import workflow.

Bulk import methodology:

1. The user pastes a public job search or job listing URL.
2. The server fetches the listing page with conservative timeouts, rate limits, and source access checks.
3. The server extracts candidate individual job posting URLs, normalizes and deduplicates them, and labels each as new, already cached, or failed/unknown when possible.
4. The client shows a review table so the user can select which jobs to import. DaliJob must not silently import every discovered job.
5. For each selected job URL, the server checks `jobs_cache`, reuses existing cached source data when available, otherwise scrapes the detail page, saves `raw_description_text`, title/company when known, and creates a user-specific `user_saved_jobs` row.
6. Bulk import should not call OpenAI just to save jobs. `jobs_cache.job_data` may remain empty until matching or a structured job-profile action needs it.
7. Optional batch matching can run after import when the user selects a resume profile. In that case, matching lazily parses any selected job whose `job_data` is missing, then saves `job_data` back to `jobs_cache`.

The first implementation should cap the number of discovered/imported jobs per request, for example 10 to 25, and can start with the first listing page only. Pagination and JavaScript-rendered listing support should be added after the basic workflow is reliable.

Incremental pagination should use a generalized "Load More" workflow instead of scraping every page automatically. The discovery endpoint returns the best `next_page_url` it can infer from generic signals such as `rel="next"`, next-page text, pagination container classes, and common query parameters like `p`, `page`, `pg`, `start`, and `offset`. The client appends newly discovered candidates, dedupes by `source_url`, and keeps user selection explicit. The scraper must stop when no next page is found, the next URL repeats, no new job URLs are discovered, or a configured page/job limit is reached.

For AI parsing, DaliJob should preserve two forms of each imported posting:

- `raw_description_text`: cleaned pasted text or broadly scraped visible page text.
- `job_data`: nullable structured JSON extracted from `raw_description_text` when matching or structured viewing requires it.

The resume-to-job matching system should compare structured resume JSON against structured job JSON. URL scraping for this path can be broader than the conservative text-only matcher scraper because OpenAI is responsible for categorizing useful fields and ignoring unrelated page text. The original raw text should still be saved so the job can be reparsed when the schema or prompts improve.

Lazy job parsing rules:

- Single-job draft/manual flows may parse immediately because the user is actively reviewing one job.
- Bulk job-list import and Apify search import should save source data first and defer OpenAI parsing.
- Before any match, the backend must ensure structured `job_data` exists. If it does not, parse `raw_description_text`, save `job_data`, and continue matching.
- If parsing fails, return a clear message so the user can retry or paste cleaner text.
- Existing parsed cache rows should be reused by URL before making another OpenAI call.

Manual job fields should include:

- Job title.
- Company.
- Source URL.
- Full job description.
- Application deadline or closing date.
- Posting date when known.
- Location.
- Remote policy.
- Employment type.
- Seniority.
- Compensation range.
- Recruiter or contact.
- User notes.

Initial plugin candidates:

- Greenhouse.
- Lever.
- USAJobs.
- Adzuna.
- Remotive.

Plugins must normalize imported postings into the internal job model and must not be required for the application tracker to work.

URL extraction should respect site terms and use conservative fetching. The product should prefer user-provided content, official APIs, structured data embedded in the page, and plugin-specific importers over brittle broad scraping.

#### Apify Indeed Job Search

Indeed blocks or gates many direct scraper requests. DaliJob should not try to bypass sign-in, verification, or bot-detection pages. Instead, DaliJob provides an optional Apify-backed Indeed search workflow as a separate job search experience.

Apify Indeed search workflow:

1. The user opens a dedicated Job Search page.
2. The user enters a keyword and location, for example `software engineer` and `Maryland`.
3. The client sends the search request to the DaliJob server.
4. The server calls the configured Apify Indeed scraper actor using `APIFY_API_TOKEN` from the server environment.
5. The server normalizes Apify results into DaliJob search result objects.
6. The client displays up to 5 returned jobs in a reviewable list.
7. The user can open a job result to inspect the full description.
8. The user selects one or more jobs to import.
9. Imported jobs flow through the existing `jobs_cache` and `user_saved_jobs` pipeline without immediate OpenAI parsing unless match-on-import is selected.
10. Optional match-on-import can run when the user selects a resume profile; this lazily parses missing `job_data` before matching.

The Apify API token must stay server-side and must never be exposed to the client. The integration should handle Apify actor failures, empty datasets, quota/token errors, and timeouts with clear user-facing errors. Since Apify calls can cost credits, the UI must not trigger searches on every keystroke. Searches should require an explicit submit action.

The first implementation targets Apify actor `misceres/indeed-scraper`. In Apify API paths, the actor ID is encoded as `misceres~indeed-scraper`.

Apify API endpoints:

- Async actor run: `POST https://api.apify.com/v2/acts/misceres~indeed-scraper/runs?token=<APIFY_API_TOKEN>`.
- Synchronous run returning dataset items: `POST https://api.apify.com/v2/acts/misceres~indeed-scraper/run-sync-get-dataset-items?token=<APIFY_API_TOKEN>`.

The current implementation uses the synchronous dataset-items endpoint for the 5-result MVP. If searches regularly exceed the request timeout, switch to the async run endpoint, poll the run status, and then fetch the default dataset items. The actor input shape should be rechecked during maintenance because Apify actors are third-party components and their input schema can change.

Actor input shape for `misceres/indeed-scraper`:

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

DaliJob's client-facing `keyword` maps to Apify `position`, `location` maps to Apify `location`, and the first implementation uses `country: "US"`. DaliJob caps `maxItemsPerSearch` to 5 for the first UI. Keep `parseCompanyDetails: false` and `followApplyRedirects: false` to reduce runtime, cost, and redirect risk. Keep `saveOnlyUniqueItems: true`.

Apify results are external data and should be normalized into DaliJob's internal source-data model before storage. The client should not depend directly on Apify field names. If Apify returns a `source_url` already present in `jobs_cache`, DaliJob should reuse the cached job rather than creating duplicate canonical job rows. Apify import should store `raw_description_text` and metadata first; structured `job_data` should be generated lazily only when matching or a structured job profile requires it.

### 4.4 Job Analysis Pipeline

```text
Job Description
  -> Cleaned raw_description_text
  -> Ensure structured job_data exists, parsing lazily when needed
  -> OpenAI Parser if jobs_cache.job_data is missing
  -> Structured job_data JSON
  -> Skill Extraction
  -> Requirement Extraction
  -> Keyword Extraction
  -> Resume Comparison
  -> Gap Analysis
  -> Application Recommendations
```

Outputs:

- Match score from 0 to 10.
- Missing skills.
- Relevant projects.
- Relevant experience.
- Recommended resume changes.
- Recommended cover letter themes.
- Recommended study topics.

The score should be explainable. The user should see why the job matched or did not match, including which requirements were supported by resume evidence and which requirements were missing.

Initial structured job JSON:

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

### 4.5 Resume Engine

The resume source of truth is structured resume profile data, not only an uploaded PDF or DOCX. DaliJob should still preserve the original uploaded master resume file because the user may want to download it, re-parse it, compare it against later profile edits, or audit where parsed facts came from.

Master resume import workflow:

```text
User uploads or pastes master resume
  -> Store original file as Document + DocumentVersion when a file exists
  -> Extract raw text
  -> Redact personal contact information before AI parsing
  -> Parse into structured resume_data JSON suggestions
  -> User reviews, edits, accepts, or rejects suggestions
  -> Accepted facts create or update a selected resume_profiles row
  -> Create ResumeVersion snapshot linked to the source document version when available
```

Uploaded PDFs and DOCX files are preserved artifacts. Generated tailored PDFs and DOCX files are rendered artifacts. Structured resume profile JSON and immutable resume versions are what the AI uses for matching, tailoring, validation, and analytics.

Before full document management is implemented, DaliJob may provide a PDF resume import prototype that extracts cleaned text, generates reviewable `resume_data` JSON suggestions, and applies accepted suggestions to a resume profile. That prototype should not be treated as permanent document storage until `documents` and `document_versions` are implemented.

Pipeline:

```text
Selected Resume Profile
  + Job Description
  -> Resume Context Builder
  -> AI Resume Engine
  -> Validation Layer
  -> Resume Version
  -> PDF/DOCX Generation
  -> Application Attachment
```

Resume engine requirements:

- Preserve source evidence for generated bullets.
- Store immutable resume versions.
- Render export files from structured resume versions.
- Attach the exact submitted version to an application.
- Show differences between master profile and tailored resume.

### 4.6 Cover Letter Engine

Inputs:

- Job description.
- Company.
- Selected resume version.
- User profile and preferences.

Pipeline:

```text
Context Builder
  -> Prompt Builder
  -> Cover Letter Generator
  -> Validation Layer
  -> Version Store
  -> Application Attachment
```

Each generated cover letter must be tied to a specific application and source resume version.

### 4.7 Application Tracking System

Application states:

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

Each application stores:

- Job.
- Company.
- Resume version.
- Cover letter version.
- Notes.
- Timeline.
- Salary.
- Recruiter.
- Documents.
- Interviews.
- Tasks.
- Reminders.
- Email and calendar links when enabled.

### 4.8 Interview Preparation Engine

Inputs:

- Job description.
- Company information.
- Resume used.
- Application history.
- Notes.
- Interview type and date when known.

Pipeline:

```text
Interview Scheduled
  -> Gather Context
  -> Company Research
  -> Role Analysis
  -> Skill Analysis
  -> Question Generation
  -> Study Guide Generation
  -> Mock Interview Generation
```

Generated company research:

- Company overview.
- Industry overview.
- Products.
- Customers.
- Competitors.
- Recent news.
- Technologies.

Study guide output:

- Priority skills.
- Recommended topics.
- Preparation roadmap.
- Estimated preparation time.
- Suggested resources.

Question categories:

- Behavioral.
- Technical.
- System design.
- Coding.
- Company specific.
- Role specific.

### 4.9 Mock Interview Engine

Mock interviews are a future feature but should be accounted for in the data model.

The user starts interview mode and AI acts as the interviewer. The system stores:

- Questions.
- Answers.
- Feedback.
- Weaknesses.
- Improvement areas.
- Session score or rubric results.

### 4.10 Interview Journal

Every real interview can create a journal entry.

Store:

- Questions asked.
- User answers.
- Mistakes.
- Lessons learned.
- Follow-up actions.
- Interviewer names.
- Sentiment and outcome.

### 4.11 Analytics Engine

Metrics:

- Applications submitted.
- Interviews.
- Offers.
- Rejections.
- Response rate.
- Offer rate.
- Interview conversion rate.
- Time in stage.
- Source performance.
- Resume version performance.

### 4.12 Career Intelligence Engine

Continuously analyzes:

- Saved jobs.
- Applications.
- Interviews.
- Offers.
- Skill trends.
- Resume effectiveness.
- Rejections.
- Learning progress.

Example insights:

- "Redis appears in 42% of saved jobs."
- "Resume Version 8 has the highest response rate."
- "Kubernetes appears frequently in jobs matching your interests."

The engine should expose evidence, sample size, confidence, and recommended actions.

### 4.13 Email Integration

Future module.

Capabilities:

- Detect application confirmations.
- Detect interview requests.
- Detect rejections.
- Detect offers.
- Auto-link emails to applications.
- Propose status updates.

Email access must be opt-in, revocable, and least-privilege.

### 4.14 Calendar Integration

Future module.

Interview emails should generate:

- Calendar events.
- Reminders.
- Preparation tasks.
- Follow-up tasks.

## 5. Service Boundaries

### Client Web App

Next.js application for:

- Career profile editor.
- Job import and analysis screens.
- Application tracker.
- Resume and cover letter review.
- Document management.
- Interview preparation.
- Analytics dashboards.
- Integration settings.

The client is a separate application under `client/`. It communicates with the server through the documented HTTP API only. It must not import server code, access the database, read server secrets, or rely on internal server file structure.

### Server API

FastAPI service for:

- Authentication and authorization.
- CRUD operations.
- Workflow state changes.
- Search and filtering.
- Signed upload and download URLs.
- AI job orchestration endpoints.
- Integration management.

The server is a separate application under `server/`. It owns persistence, authorization, AI orchestration, file storage, integration credentials, background job scheduling, and business rules.

Server startup must support `--config [config_file_name].ini` and load runtime settings through `DaliCommonLib.dali_config.ProcessConfig`. Follow the existing pattern from `app_server`: keep `main.py` thin, parse CLI args there, and delegate ProcessConfig loading to `server/app/config.py`.

Database reads and writes should use `DaliCommonLib.dali_db_man.DbMan` rather than ad hoc engine/session creation throughout the app. Server repository modules should depend on a small local database adapter that wraps DbMan so the app has one consistent place for sessions, queries, writes, migrations, and tests.

### Worker System

Celery or equivalent workers for:

- Resume parsing.
- Resume tailoring.
- Cover letter generation.
- Job analysis.
- PDF/DOCX rendering.
- Email sync.
- Calendar sync.
- Plugin imports.
- Analytics snapshots.
- Career intelligence jobs.

### AI Provider Abstraction

Responsibilities:

- Route requests to configured providers.
- Version prompt templates.
- Validate structured outputs.
- Track usage and cost.
- Keep model-specific details out of business services.

Initial provider:

- Use OpenAI for the resume-to-job comparison prototype.
- Read the API key from `OPENAI_API_KEY` in the server process environment.
- Read non-secret settings such as `model` from `ProcessConfig`, preferably from an `[openai]` section.
- Keep OpenAI calls server-side only.
- Return schema-validated JSON so the match result can be stored and displayed reliably.

### Document Service

Responsibilities:

- Upload validation.
- Object storage.
- Versioning.
- Text extraction.
- Preview generation.
- PDF/DOCX rendering.

### Database Access Layer

DaliJob should use `DaliCommonLib` as the required database/config integration layer.

Required classes:

- `DaliCommonLib.dali_config.ProcessConfig` for process-level ini configuration.
- `DaliCommonLib.dali_db_man.DbMan` for SQLAlchemy engine/session management and SQL helpers.

Useful `DbMan` functions:

- `get_db_engine(schema=None)`.
- `get_session_factory(schema=None)`.
- `get_db_session(schema=None)`.
- `session_scope(schema=None)`.
- `session_dependency(schema=None)` for FastAPI dependencies.
- `create_all(base, schema=None)` and `drop_all(base, schema=None)` for controlled setup tasks.
- `fetch_dicts(sql, params=None, db=None)`.
- `fetch_one(sql, params=None, db=None)`.
- `fetch_scalar(sql, params=None, db=None)`.
- `write(sql, params=None, db=None)`.
- `write_many(sql, params_list, db=None)`.
- `dispose_all_engines()` should be called on app shutdown if available.

The server should avoid creating independent SQLAlchemy engines outside this path. If SQLAlchemy ORM models are used, sessions should still come from `DbMan.session_dependency()` or `DbMan.session_scope()`.

`ProcessConfig` should allow easy switching between local, staging, and production databases by changing only the ini file passed at startup.

The database schema should be DaliJob-specific. The default schema name should be `dali_job` unless a config file specifies another schema through the `mysql.active_db_schema` setting.

Database setup and seed operations should be scriptable. The project should include Python scripts under a top-level `scripts/` folder that load the same `ProcessConfig` ini file and use `DbMan` to create, migrate, validate, and seed the configured schema.

### Authentication Boundary

DaliJob should provide a normal first-party login experience: users can register and log in directly from DaliJob without needing to open or authenticate through app_server. The first implementation should support two modes:

- `local`: DaliJob-owned email/password registration and login. The server stores password hashes in the DaliJob `users` table and issues DaliJob bearer tokens.
- `dev`: local debugging mode that maps every request to the built-in DaliJob development user.

The broader Dalifin goal of registering once and using many apps should be treated as a shared identity architecture decision. That can be handled later by extracting identity into a common auth service or shared user database used by DaliJob, app_server, DaliBible, and other Dalifin apps. It should not mean DaliJob depends on an app_server login token or requires users to visit another application before using DaliJob.

### Integration Adapters

Adapters isolate external dependencies:

- Job source plugins.
- Email providers.
- Calendar providers.
- AI providers.
- Storage providers.

## 5.1 Client/Server Independence Rules

- Keep `client/` and `server/` as separate top-level applications.
- The API specification is the contract between them.
- The client may use generated API types, but generated types should come from OpenAPI or a shared contract artifact, not direct imports from server source files.
- The server must not assume a specific client implementation. Browser, mobile, CLI, or future desktop clients should all be able to use the API.
- The client must not access the SQL database, Redis, object storage credentials, OAuth secrets, or AI provider keys.
- Client and server should have independent build, test, lint, and deployment pipelines.
- Breaking API changes require versioning or a migration path.
- Server-side rendering in Next.js may call the server API, but should still treat the server as an external boundary.

## 6. Event-Driven Workflows

### Resume Tailoring

```text
User requests tailored resume
  -> API creates AI generation job
  -> Worker builds context from profile and job
  -> AI provider generates structured resume draft
  -> Validation checks factual support
  -> ResumeVersion is saved
  -> DocumentVersion is rendered
  -> Application timeline records event
  -> User reviews and approves
```

### Cover Letter Generation

```text
User requests cover letter
  -> API creates AI generation job
  -> Worker loads company, job, profile, and selected resume
  -> AI provider generates draft
  -> Validation checks unsupported claims
  -> CoverLetterVersion is saved
  -> DocumentVersion is rendered
  -> Application timeline records event
```

### Email Status Detection

```text
Email provider webhook or scheduled sync
  -> Worker fetches relevant messages
  -> Classifier identifies job-search message type
  -> Matcher links message to candidate application
  -> Status suggestion is created
  -> User accepts, edits, rejects, or configures low-risk auto-apply
```

### Interview Preparation

```text
Application enters interview stage
  -> System suggests prep guide generation
  -> Worker gathers job, company, resume, notes, and timeline
  -> AI provider generates role analysis, study guide, and questions
  -> InterviewPrepGuide is saved
  -> User edits guide and tracks preparation tasks
```

## 7. Security Requirements

- Authentication required. DaliJob should support direct DaliJob login for MVP.
- Owner-only workspace authorization for MVP.
- Role-based workspace sharing is a future optional feature, not a core requirement.
- Encrypted storage for sensitive data.
- Secure file uploads.
- Signed URLs for document access.
- OAuth token encryption.
- Audit logging.
- Sensitive data protection in logs and AI prompts.
- Explicit consent for email, calendar, and AI-provider use.

## 8. Non-Functional Requirements

- Maintainable module boundaries.
- Modular plugin and provider architecture.
- Scalable worker queues.
- Testable business logic.
- Observable services and jobs.
- Extensible data model.
- AI-provider agnostic implementation.
- Graceful degradation when optional integrations fail.

## 9. Suggested Tech Stack

- Server: Python, FastAPI, SQLAlchemy, Alembic, and `DaliCommonLib`.
- Database access: `DaliCommonLib.dali_db_man.DbMan`.
- Runtime configuration: `DaliCommonLib.dali_config.ProcessConfig` loaded with `--config [config_file_name].ini`.
- SQL database: MySQL-compatible by default because `DbMan` currently uses `mysql+pymysql` configuration.
- Background tasks: Celery or equivalent.
- Cache and broker: Redis.
- Storage: S3-compatible object storage.
- Client: React and Next.js.
- AI: provider abstraction layer.
- Document rendering: server-side renderer behind a worker boundary.

## 10. Open Decisions

- Whether the first version is single-user local-first, hosted SaaS, or both.
- Whether DOCX export is required in Phase 1 or Phase 2.
- Whether the future Dalifin-wide account system should be a shared database, standalone auth service, or common auth package.
- Which AI provider should be default.
- Which email provider should be supported first.
- Whether browser extension import belongs in Phase 2 or later.

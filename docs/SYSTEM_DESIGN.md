# DaliJob System Design

## 1. Executive Summary

DaliJob is an AI-assisted career management platform that acts as the single source of truth for a user's career search. It helps users import opportunities, analyze roles, tailor documents, track applications, prepare for interviews, record outcomes, and learn from historical data.

DaliJob is not a job board and not simply a resume builder. Job aggregation is optional. AI is a supporting system, not the core product. The app must continue to work when AI providers, email integrations, calendar integrations, or job-source plugins are unavailable.

## 2. Product Principles

- The user's profile is the canonical source of truth for career facts.
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
  -> Pastes master resume text
  -> Pastes job description text
  -> Server extracts resume and job text
  -> OpenAI-backed comparison service identifies skills, keywords, requirements, and evidence
  -> Match engine returns score from 0 to 10
  -> UI displays score, matched skills, missing skills, keyword overlap, and recommendations
```

Score meaning:

- `0`: no meaningful overlap between resume and job description.
- `5`: partial match with several important gaps.
- `10`: excellent match where the resume strongly supports the job's core requirements.

The first prototype should support pasted text only for both resume and job description. PDF/DOCX upload, job URL extraction, application tracking, cover letter generation, interview prep, email integration, and analytics should come later after the text-only comparison works.

The comparison should use the OpenAI API through the server-side AI provider abstraction. The OpenAI API key must be read from the server process environment variable `OPENAI_API_KEY`, never from the client and never from a committed config file. The model name should be configurable through `ProcessConfig` so it can be changed without code edits.

This prototype should still preserve the client/server split: the client submits resume/job text through the API, and the server performs AI calls, scoring, validation, and persistence.

### 4.1 User Profile Module

Stores the structured career profile that powers resume generation, cover letters, study guides, and analytics.

Profile sections:

- Education.
- Work experience.
- Projects.
- Skills.
- Certifications.
- Awards.
- Publications.
- Portfolio links.
- Preferences such as target roles, locations, remote policy, industries, salary expectations, and document style.

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
- Fully manual job entry where the user types or pastes title, company, description, deadline, location, salary, source URL, and notes.
- Upload PDF job description.
- Copy and paste job description.
- Import from supported integrations.
- Optional aggregation plugins.

Manual entry is a core workflow, not a fallback-only feature. A user must be able to track a job even when it comes from a company website, recruiter email, private posting, personal referral, PDF, or any site that does not have a job search API.

URL extraction is a convenience feature. If the page cannot be fetched, blocks automated access, requires authentication, renders content client-side, or does not expose parseable job data, DaliJob should keep the URL and let the user manually fill or paste the missing fields. URL extraction must not be required for application tracking.

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

### 4.4 Job Analysis Pipeline

```text
Job Description
  -> Parser
  -> Structured Job Model
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

### 4.5 Resume Engine

The resume source of truth is structured data, not a PDF. PDFs and DOCX files are generated artifacts.

Pipeline:

```text
Master Profile
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

- Authentication required.
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
- Which auth provider to use.
- Which AI provider should be default.
- Which email provider should be supported first.
- Whether browser extension import belongs in Phase 2 or later.

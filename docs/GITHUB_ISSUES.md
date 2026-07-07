# DaliJob GitHub Issues

These starter issues are grouped by milestone and can be copied into GitHub.

## Milestone: Project Foundation

### 1. Scaffold FastAPI Server

Create the `server/` application with FastAPI, SQLAlchemy, Alembic, `DaliCommonLib`, typed settings, logging, and health checks.

Acceptance criteria:

- `/health` returns service status.
- Root `requirements.txt` includes `-e ../DaliCommonLib`.
- Server accepts `--config [config_file_name].ini`.
- `server/app/config.py` loads config through `DaliCommonLib.dali_config.ProcessConfig`.
- Database sessions are provided through `DaliCommonLib.dali_db_man.DbMan`.
- FastAPI shutdown disposes DbMan engines if `dispose_all_engines()` is available.
- Alembic can create and run migrations.
- Tests can run in CI.

### 1a. Add DaliJob Database Setup Scripts

Create top-level Python scripts for creating, seeding, and validating the database selected by the config file.

Acceptance criteria:

- `scripts/create_schema.py --config local.ini` creates the configured DaliJob schema if it does not exist.
- `scripts/create_tables.py --config local.ini` creates or migrates required tables.
- `scripts/seed_database.py --config local.ini` inserts local development seed data.
- `scripts/validate_database.py --config local.ini` verifies required tables exist.
- Scripts load config through `ProcessConfig`.
- Scripts use `DbMan`.
- Scripts do not hard-code local or production database credentials.

### 2. Scaffold Next.js Client

Create the `client/` app shell with routing, layout, API client, and baseline styling.

Acceptance criteria:

- App renders a protected layout placeholder.
- API client supports authenticated requests.
- Basic responsive navigation exists.

### 3. Add Local Docker Compose

Add local services for a MySQL-compatible SQL database, object storage, server, and client. Add Redis when background workers are introduced.

Acceptance criteria:

- `docker compose up` starts local dependencies.
- Server can connect to the configured SQL database through `DbMan`.
- Object storage is reachable in development.

### 3a. Add Client/Server Contract Boundary

Make `/api/v1` the explicit contract between `client/` and `server/`.

Acceptance criteria:

- Client does not import server source files.
- Server does not import client source files.
- OpenAPI schema can be generated from the server.
- Contract tests verify key request and response shapes.

## Milestone: Accounts And Profile

### 3b. Build Resume-To-Job Match Prototype

Build the first functional prototype before the full tracker. The user should be able to paste resume text, paste a job description, run comparison, and receive a 0-10 match score.

Acceptance criteria:

- Barebones client screen accepts pasted resume text.
- Barebones client screen accepts job description text.
- Resume/job file upload and job URL extraction are deferred until after text-only comparison works.
- Server uses OpenAI through the AI provider abstraction.
- OpenAI API key is read from server environment variable `OPENAI_API_KEY`.
- OpenAI model is read from `ProcessConfig`.
- OpenAI API key is never exposed to the client.
- Server returns integer `match_score` from 0 to 10.
- Server returns matched skills, missing skills, matched keywords, missing keywords, supported requirements, unsupported requirements, and recommendations.
- Result is readable in the UI.
- Invalid or empty inputs return useful validation errors.

### 4. Implement Users And Private Workspaces

Create user and private workspace tables with owner-only authorization helpers. Sharing, membership, and roles are out of scope for the MVP.

Acceptance criteria:

- Users can own one or more private workspaces.
- Each workspace has exactly one `owner_user_id`.
- Server rejects cross-workspace access unless the authenticated user owns the workspace.
- Tests cover authorization checks.
- No `workspace_members` table is required for MVP.

### 5. Build Resume Profile Data Model

Add JSON-backed resume profile storage and APIs for reading/updating the user's structured resume data.

Acceptance criteria:

- User can create multiple structured resume profiles.
- Each resume profile stores one validated `resume_data` JSON document.
- User can set exactly one default resume profile.
- Resume profile list endpoints return the default resume first, then most recently updated resumes.

### 6. Build Profile And Resume Editor UI

Create client screens for editing structured resume profiles.

Acceptance criteria:

- User can manage skills, experience, projects, education, and certifications through the JSON-backed resume profile editor.
- User can star or unstar resumes from the resume profile list.
- The default resume displays first on the profile page and in resume selectors.
- Form validation prevents invalid dates and empty required fields.

## Milestone: Jobs And Applications

### 7. Implement Manual Job Import

Allow users to create jobs without any job board API or aggregation plugin. Users can fully type or paste job details from any source, including company sites, recruiter messages, PDFs, referrals, or private postings.

Acceptance criteria:

- Job stores title, company, URL, location, raw description, deadline, posting date, compensation, remote policy, employment type, seniority, and notes.
- User can view saved jobs.
- User can create a job when no URL is available.
- User can create a job when URL extraction fails.

### 7a. Implement URL-Based Job Extraction

Allow users to paste a job posting URL and have the server attempt to extract job details into a reviewable draft.

Acceptance criteria:

- URL import attempts to extract title, company, description, location, salary, and deadline.
- Extracted jobs are marked `needs_review` until the user confirms them.
- Failed extraction preserves the source URL and opens the manual entry flow.
- URL extraction failure does not block application creation.
- Fetching uses conservative timeouts and respects source limitations.

### 8. Implement PDF Job Description Import

Allow upload of PDF job descriptions and extract text for storage.

Acceptance criteria:

- PDF upload creates a document version.
- Extracted text can create a job.
- Upload errors are user-visible.

### 9. Implement Application Tracker

Create application CRUD, status transitions, notes, timeline events, and list filters.

Acceptance criteria:

- User can create an application from a job.
- User can move through all required statuses.
- Every status transition creates history.

### 10. Build Application Detail Screen

Build the main application workspace with job details, status, documents, notes, tasks, and timeline.

Acceptance criteria:

- User can see application state in one screen.
- User can add notes and tasks.
- User can attach documents.

## Milestone: Documents

### 11. Implement Document Versioning

Create document and document version models with signed upload/download URLs.

Acceptance criteria:

- Document versions are immutable.
- Current version is tracked.
- Application attachments point to exact versions.

### 12. Build Document Library

Create UI for uploaded and generated documents.

Acceptance criteria:

- User can list, upload, download, and attach documents.
- Document type and version are visible.

## Milestone: AI Foundation

### 13. Implement AI Provider Abstraction

Add provider interface, prompt templates, AI job table, and worker execution.

Acceptance criteria:

- AI jobs can be queued and completed.
- Prompt version and model name are stored.
- Mock provider exists for tests.

### 14. Add Job Description Analysis

Parse job descriptions into structured requirements, skills, keywords, and recommended study topics.

Acceptance criteria:

- Analysis output validates against schema.
- Job detail screen shows analysis.

### 15. Add Resume Tailoring

Generate tailored resume versions from profile and job description.

Acceptance criteria:

- AI cannot add unsupported claims without warning.
- Generated resume is reviewable before attachment.
- Resume version links to AI job and source job.

### 16. Add Cover Letter Generation

Generate cover letters from application context.

Acceptance criteria:

- Cover letter is tied to application and resume version.
- User can edit and create a new immutable version.

## Milestone: Interview Preparation

### 17. Implement Interview Records

Add interview schedule, type, outcome, questions, and notes.

Acceptance criteria:

- User can create interviews for applications.
- User can record interview journal notes.

### 18. Generate Interview Prep Guides

Generate company research, role analysis, study guide, and interview questions.

Acceptance criteria:

- Prep guide links to application and resume version.
- Output includes priority skills, roadmap, estimated prep time, and questions.

### 19. Prototype Mock Interview

Create first mock interview session model and UI.

Acceptance criteria:

- User can start a mock interview.
- System stores questions, answers, feedback, weaknesses, and improvement areas.

## Milestone: Integrations

### 20. Add Email Integration

Implement first email provider integration with OAuth, sync, classification, and application linking.

Acceptance criteria:

- User can connect and revoke email.
- Messages can be classified as confirmation, interview, rejection, offer, or unrelated.
- Status suggestions require review.

### 21. Add Calendar Integration

Create calendar events from interviews and preparation reminders.

Acceptance criteria:

- User can connect and revoke calendar.
- Interview event can be created from application.
- Preparation tasks can create reminders.

### 22. Add Job Source Plugin Interface

Create plugin manifest, plugin runner, and normalized job contract.

Acceptance criteria:

- Greenhouse and Lever URL import prototypes implement the contract.
- Plugin failures do not break manual job tracking.

## Milestone: Analytics And Intelligence

### 23. Implement Analytics Dashboard

Show applications submitted, interviews, offers, rejections, response rate, offer rate, and interview conversion rate.

Acceptance criteria:

- Metrics update from application state.
- Funnel is filterable by date range.

### 24. Implement Career Intelligence Insights

Generate trend insights from jobs, applications, interviews, offers, and resume versions.

Acceptance criteria:

- Insight includes evidence, sample size, confidence, and recommended actions.
- User can dismiss or pin insight.

## Milestone: Security And Release

### 25. Add Audit Logging

Log sensitive actions such as login, document access, AI generation, integration changes, and status changes.

Acceptance criteria:

- Audit events are queryable by workspace.
- Sensitive content is not logged.

### 26. Add Data Export And Deletion

Allow users to export and delete workspace data.

Acceptance criteria:

- Export includes profile, jobs, applications, documents metadata, and analytics.
- Deletion removes or anonymizes data according to retention policy.

### 27. Production Deployment

Deploy server, client, workers, database, Redis, object storage, and monitoring.

Acceptance criteria:

- Staging and production environments exist.
- CI/CD deploys repeatably.
- Monitoring and alerts are configured.

# CareerOS GitHub Issues

These starter issues are grouped by milestone and can be copied into GitHub.

## Milestone: Project Foundation

### 1. Scaffold FastAPI Server

Create the `server/` application with FastAPI, SQLAlchemy, Alembic, typed settings, logging, and health checks.

Acceptance criteria:

- `/health` returns service status.
- Database session is configured.
- Alembic can create and run migrations.
- Tests can run in CI.

### 2. Scaffold Next.js Client

Create the `client/` app shell with routing, layout, API client, and baseline styling.

Acceptance criteria:

- App renders a protected layout placeholder.
- API client supports authenticated requests.
- Basic responsive navigation exists.

### 3. Add Local Docker Compose

Add local services for PostgreSQL, Redis, object storage, server, and client.

Acceptance criteria:

- `docker compose up` starts local dependencies.
- Server can connect to PostgreSQL and Redis.
- Object storage is reachable in development.

### 3a. Add Client/Server Contract Boundary

Make `/api/v1` the explicit contract between `client/` and `server/`.

Acceptance criteria:

- Client does not import server source files.
- Server does not import client source files.
- OpenAPI schema can be generated from the server.
- Contract tests verify key request and response shapes.

## Milestone: Accounts And Profile

### 4. Implement Users, Workspaces, And Memberships

Create user, workspace, and membership tables with workspace-scoped authorization helpers.

Acceptance criteria:

- Users can belong to workspaces.
- Backend rejects cross-workspace access.
- Tests cover authorization checks.

### 5. Build Career Profile Data Model

Add tables and APIs for profile, skills, experience, education, projects, certifications, awards, publications, and portfolio links.

Acceptance criteria:

- User can create and edit all profile sections.
- Experience bullets can be linked to skills.
- Profile endpoints return structured data.

### 6. Build Profile Editor UI

Create client screens for editing the career profile.

Acceptance criteria:

- User can manage skills, experience, projects, education, and certifications.
- Form validation prevents invalid dates and empty required fields.

## Milestone: Jobs And Applications

### 7. Implement Manual Job Import

Allow users to create jobs from pasted job descriptions and source URLs.

Acceptance criteria:

- Job stores title, company, URL, location, and raw description.
- User can view saved jobs.

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

# DaliJob Implementation Checklist

## Phase 0: Project Foundation

- [ ] Create top-level `server/` FastAPI project.
- [ ] Create top-level `client/` Next.js project.
- [ ] Configure client/server API boundary through `/api/v1`.
- [ ] Add OpenAPI generation or documented contract workflow.
- [ ] Add PostgreSQL, Redis, and object storage to local Docker Compose.
- [ ] Configure Alembic migrations.
- [ ] Add typed server settings.
- [ ] Add client environment configuration for public values only.
- [ ] Add structured logging.
- [ ] Add health check endpoints.
- [ ] Add separate CI jobs for server linting, server tests, client linting, client tests, and migrations.
- [ ] Add API contract tests so client and server can change independently.
- [ ] Add basic design system and app shell.

## Phase 1: MVP Core

### Accounts And Workspaces

- [ ] Implement user model.
- [ ] Implement private workspace model with `owner_user_id`.
- [ ] Add authentication.
- [ ] Add owner-only workspace authorization.
- [ ] Defer workspace sharing, membership, and roles until a future collaboration feature is intentionally designed.

### Profile

- [ ] Create profile schema and tables.
- [ ] Add CRUD for skills.
- [ ] Add CRUD for experience.
- [ ] Add CRUD for education.
- [ ] Add CRUD for projects.
- [ ] Add CRUD for certifications, awards, publications, and links.
- [ ] Build profile editor UI.

### Job Import

- [ ] Add full manual job creation with title, company, description, deadline, location, salary, source URL, and notes.
- [ ] Add copy/paste job description import.
- [ ] Add URL import that attempts extraction and creates a reviewable draft.
- [ ] Add fallback flow for failed URL extraction so the user can manually complete the job.
- [ ] Add PDF job description upload.
- [ ] Store raw and structured job data.
- [ ] Build jobs list and detail UI.

### Application Tracking

- [ ] Create application table and status enum.
- [ ] Add application CRUD.
- [ ] Add status transition endpoint.
- [ ] Add application timeline events.
- [ ] Add notes.
- [ ] Add tasks and reminders.
- [ ] Build tracker UI.
- [ ] Build application detail UI.

### Document Management

- [ ] Add documents and document versions.
- [ ] Add signed upload URL flow.
- [ ] Add signed download URL flow.
- [ ] Add application document attachments.
- [ ] Add document list and preview UI.

### Basic Analytics

- [ ] Add application count metrics.
- [ ] Add status funnel metrics.
- [ ] Add response-rate calculations.
- [ ] Build analytics summary UI.

## Phase 2: AI Documents And Job Analysis

### AI Infrastructure

- [ ] Add AI provider abstraction.
- [ ] Add prompt versioning.
- [ ] Add AI generation job table.
- [ ] Add worker queue for AI jobs.
- [ ] Add schema validation for AI outputs.
- [ ] Add AI usage logging.

### Resume Engine

- [ ] Define structured resume schema.
- [ ] Add resume version table.
- [ ] Parse uploaded resumes into structured profile suggestions.
- [ ] Build resume version viewer.
- [ ] Implement resume tailoring.
- [ ] Add validation for unsupported claims.
- [ ] Add resume diff UI.
- [ ] Render PDF.
- [ ] Render DOCX if required.
- [ ] Attach tailored resume to application.

### Cover Letter Engine

- [ ] Add cover letter version table.
- [ ] Implement cover letter generation.
- [ ] Validate unsupported claims.
- [ ] Add review and edit UI.
- [ ] Render PDF/DOCX.
- [ ] Attach cover letter to application.

### Job Analysis

- [ ] Parse job descriptions.
- [ ] Extract skills, requirements, keywords, and seniority.
- [ ] Compare job against profile.
- [ ] Generate match score.
- [ ] Generate gap analysis.
- [ ] Generate recommended resume changes.
- [ ] Generate recommended study topics.

## Phase 3: Interview Preparation

- [ ] Add interviews table.
- [ ] Add interview scheduling fields.
- [ ] Add interview journal notes.
- [ ] Add interview prep guide table.
- [ ] Generate company overview.
- [ ] Generate industry overview.
- [ ] Generate product, customer, competitor, and technology notes.
- [ ] Generate question bank.
- [ ] Generate study guide.
- [ ] Generate preparation roadmap.
- [ ] Add suggested resources.
- [ ] Build interview prep UI.
- [ ] Add mock interview data model.
- [ ] Build first mock interview prototype.

## Phase 4: Integrations And Career Intelligence

### Email

- [ ] Add integration table.
- [ ] Add OAuth flow for first email provider.
- [ ] Add encrypted credential storage.
- [ ] Add email sync worker.
- [ ] Classify application confirmations.
- [ ] Classify interview requests.
- [ ] Classify rejections.
- [ ] Classify offers.
- [ ] Link emails to applications.
- [ ] Add reviewable status suggestions.

### Calendar

- [ ] Add calendar integration model.
- [ ] Add OAuth flow for first calendar provider.
- [ ] Create events from interviews.
- [ ] Create preparation reminders.
- [ ] Sync changes back to provider.

### Career Intelligence

- [ ] Add analytics snapshots.
- [ ] Add skill trend analysis.
- [ ] Add resume version performance analysis.
- [ ] Add source performance analysis.
- [ ] Add learning recommendations.
- [ ] Add insight dismiss and pin actions.

### Job Source Plugins

- [ ] Define plugin manifest schema.
- [ ] Define plugin interface.
- [ ] Implement Greenhouse URL import.
- [ ] Implement Lever URL import.
- [ ] Implement USAJobs integration if API access is available.
- [ ] Implement Adzuna integration if API access is available.
- [ ] Implement Remotive integration if API access is available.

## Hardening Before Public Release

- [ ] Add full audit log.
- [ ] Add account deletion and export.
- [ ] Add integration revocation.
- [ ] Add malware scanning or safe file processing boundary.
- [ ] Add rate limiting.
- [ ] Add backup and restore process.
- [ ] Add production monitoring.
- [ ] Add privacy policy and AI disclosure copy.

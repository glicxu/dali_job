# DaliJob Implementation Checklist

## Phase 0: Project Foundation

- [ ] Create top-level `server/` FastAPI project.
- [ ] Create top-level `client/` Next.js project.
- [ ] Configure client/server API boundary through `/api/v1`.
- [ ] Add OpenAPI generation or documented contract workflow.
- [ ] Add MySQL-compatible SQL database and object storage to local Docker Compose.
- [ ] Add Redis only when background jobs are introduced.
- [ ] Configure Alembic migrations.
- [ ] Add `server/requirements.txt` with `../DaliCommonLib`.
- [ ] Add typed server settings backed by `DaliCommonLib.dali_config.ProcessConfig`.
- [ ] Add `--config [config_file_name].ini` support to the server entrypoint.
- [ ] Add `_load_process_config` helper in `server/app/config.py`, following the `app_server` pattern.
- [ ] Add database adapter using `DaliCommonLib.dali_db_man.DbMan`.
- [ ] Use `DbMan.session_dependency()` or `DbMan.session_scope()` for server database access.
- [ ] Ensure server shutdown calls `DbMan.dispose_all_engines()` if available.
- [ ] Create top-level `scripts/` folder for database setup and seed utilities.
- [ ] Add database creation script that loads `--config` and creates the configured DaliJob schema.
- [ ] Add database seed script that loads `--config` and inserts local development seed data.
- [ ] Add database validation script that loads `--config` and verifies required tables exist.
- [ ] Add client environment configuration for public values only.
- [ ] Add structured logging.
- [ ] Add health check endpoints.
- [ ] Add separate CI jobs for server linting, server tests, client linting, client tests, and migrations.
- [ ] Add API contract tests so client and server can change independently.
- [ ] Add barebones client app shell.
- [ ] Add barebones server API shell.

## Phase 0.5: Resume-To-Job Match Prototype

This is the first functional slice. It should happen before the full tracker, cover letter engine, interview prep, email integration, or job aggregation work.

### Barebones UI

- [ ] Add a simple page for pasting master resume text.
- [ ] Add a simple page or panel for pasting job description text.
- [ ] Defer PDF/DOCX upload until after text-only comparison works.
- [ ] Defer job URL extraction until after text-only comparison works.
- [ ] Add a "Compare Resume To Job" action.
- [ ] Show a 0-10 match score.
- [ ] Show matched skills and keywords.
- [ ] Show missing skills and keywords.
- [ ] Show job requirements that appear supported by resume evidence.
- [ ] Show recommended resume improvements.

### Server Capability

- [ ] Add resume pasted-text input.
- [ ] Add job description pasted-text input.
- [ ] Add OpenAI provider implementation for the comparison.
- [ ] Read OpenAI API key from server environment variable `OPENAI_API_KEY`.
- [ ] Read OpenAI model from `ProcessConfig` `[openai].model`.
- [ ] Keep OpenAI API key server-side only.
- [ ] Add prompt/schema for extracting resume skills and job requirements.
- [ ] Add match scoring logic with score range 0-10.
- [ ] Add endpoint for ad hoc resume/job comparison.
- [ ] Store comparison result if the user is authenticated.
- [ ] Add tests for scoring, missing skills, matched skills, and invalid inputs.

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
- [ ] Add URL import that attempts extraction and creates a reviewable draft after the text-only comparison prototype works.
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
- [ ] Generate match score from 0 to 10.
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

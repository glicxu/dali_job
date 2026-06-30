# DaliJob Implementation Checklist

## Phase 0: Project Foundation

- [x] Create top-level `server/` FastAPI project.
- [x] Create top-level `client/` Next.js project.
- [x] Configure client/server API boundary through `/api/v1`.
- [x] Add OpenAPI generation or documented contract workflow.
- [x] Add MySQL-compatible SQL database and object storage to local Docker Compose.
- [x] Add Redis only when background jobs are introduced.
- [x] Configure Alembic migrations.
- [x] Add root `requirements.txt` with `-e ../DaliCommonLib`.
- [x] Add typed server settings backed by `DaliCommonLib.dali_config.ProcessConfig`.
- [x] Add `--config [config_file_name].ini` support to the server entrypoint.
- [x] Add `_load_process_config` helper in `server/app/config.py`, following the `app_server` pattern.
- [x] Add database adapter using `DaliCommonLib.dali_db_man.DbMan`.
- [x] Use `DbMan.session_dependency()` or `DbMan.session_scope()` for server database access.
- [x] Ensure server shutdown calls `DbMan.dispose_all_engines()` if available.
- [x] Create top-level `scripts/` folder for database setup and seed utilities.
- [x] Add database creation script that loads `--config` and creates the configured DaliJob schema.
- [x] Add database seed script that loads `--config` and inserts local development seed data.
- [x] Add database validation script that loads `--config` and verifies required tables exist.
- [x] Add client environment configuration for public values only.
- [x] Add structured logging.
- [x] Add health check endpoints.
- [ ] Add separate CI jobs for server linting, server tests, client linting, client tests, and migrations.
- [x] Add API contract tests so client and server can change independently.
- [x] Add barebones client app shell.
- [x] Add barebones server API shell.

## Phase 0.5: Resume-To-Job Match Prototype

This is the first functional slice. It should happen before the full tracker, cover letter engine, interview prep, email integration, or job aggregation work.

### Barebones UI

- [x] Add a simple page for pasting master resume text.
- [x] Add a simple page or panel for pasting job description text.
- [x] Defer PDF/DOCX upload until after text-only comparison works.
- [x] Defer job URL extraction until after text-only comparison works.
- [x] Add uploaded resume document selection for matching.
- [x] Add job URL input with server-side text extraction for matching.
- [x] Keep pasted resume and job description text as fallback inputs.
- [x] Make job URL input and pasted job description input mutually exclusive in the matcher UI.
- [x] Add a "Compare Resume To Job" action.
- [x] Show a 0-10 match score.
- [x] Show matched skills and keywords.
- [x] Show missing skills and keywords.
- [x] Show job requirements that appear supported by resume evidence.
- [x] Show recommended resume improvements.

### Server Capability

- [x] Add resume pasted-text input.
- [x] Add resume document ID input using stored redacted extracted text.
- [x] Add job description pasted-text input.
- [x] Add job URL extraction input for ad hoc matching.
- [x] Parse the job description as structured job JSON before matching.
- [x] Use structured resume JSON and structured job JSON for the OpenAI match request when available.
- [x] Save pasted job-description fallback text to `jobs_cache` and create a `user_saved_jobs` row when the match is saved.
- [x] Auto-save matched jobs only when the score is 5 or higher.
- [x] Ask the user whether to save low-compatibility jobs below score 5.
- [x] Store match score and selected resume reference in `job_resume_matches`, not on saved jobs.
- [x] Link matches to `resume_profile_id` when the selected resume source is a saved structured resume profile.
- [x] Add OpenAI provider implementation for the comparison.
- [x] Read OpenAI API key from server environment variable `OPENAI_API_KEY`.
- [x] Read OpenAI model from `ProcessConfig` `[openai].model`.
- [x] Keep OpenAI API key server-side only.
- [x] Add prompt/schema for extracting resume skills and job requirements.
- [x] Add match scoring logic with score range 0-10.
- [x] Add endpoint for ad hoc resume/job comparison.
- [x] Store saved comparison result if the user is authenticated.
- [x] Add tests for scoring, missing skills, matched skills, document input, URL extraction, and invalid inputs.

## Phase 1: MVP Core

Recommended implementation order:

1. Database foundation: users, private workspaces, base migrations, seed script, validation script, and migration CI.
2. Resume profile foundation: multiple JSON-backed resume profiles, favorite resume sorting, PDF resume import, and basic resume editor UI.
3. Job import: manual job creation, pasted job descriptions, jobs list, and job detail UI.
4. Application tracking: application table, status transitions, timeline events, notes, tasks, reminders, tracker UI, and application detail UI.
5. Document management: documents, document versions, signed upload/download flow, document library, and application attachments.
6. Resume/job match persistence: save comparison results for authenticated users and link results to jobs, applications, resume versions, or uploaded resume documents.
7. Basic analytics: application counts, status funnel, response-rate calculations, and analytics summary UI.

The sections below are grouped by product area. The order above should guide implementation so each slice leaves the app runnable and reviewable.

### Accounts And Workspaces

- [x] Implement user model.
- [x] Implement private workspace model with `owner_user_id`.
- [x] Add first-pass authentication dependency with `dev` mode and DaliJob local bearer-token mode.
- [x] Add DaliJob email/password registration and login API.
- [x] Add login/register client UI.
- [x] Map authenticated DaliJob users into private DaliJob users/workspaces.
- [ ] Decide future shared Dalifin identity architecture for one registration across multiple Dalifin apps.
- [ ] Add owner-only workspace authorization beyond the current private-workspace profile scope.
- [ ] Defer workspace sharing, membership, and roles until a future collaboration feature is intentionally designed.

### Profile

- [x] Create initial profile schema with JSON-backed resume data.
- [x] Split structured resume data into `resume_profiles.resume_data` so one user can maintain multiple parsed resumes.
- [x] Remove the legacy `profiles` table so `resume_profiles` is the only structured resume JSON storage.
- [x] Add `resume_profiles.is_favorite` so users can star any number of resumes and see favorites first.
- [x] Replace separate skills, experience, education, projects, certifications, awards, publications, and links tables with one resume JSON document.
- [x] Add list/create/read/update/delete API for structured resume profiles.
- [x] Add favorite/unfavorite support without requiring a single primary resume.
- [x] Add master resume upload or paste flow that preserves the original document when a file is provided.
- [x] Add PDF master resume import prototype that extracts structured profile suggestions.
- [x] Redact common personal contact information from uploaded resume text before AI parsing.
- [x] Exclude name, email, phone, location, personal website, and social profile URL fields from saved resume JSON.
- [x] Extract master resume text into reviewable structured profile suggestions.
- [x] Let the user accept or reject parsed profile suggestions before saving resume JSON.
- [x] Let the user apply parsed suggestions into a new resume profile instead of overwriting one global profile JSON.
- [x] Let the user edit parsed profile suggestions after applying them in the JSON-backed editor.
- [x] Build resume profile list UI with favorites displayed first.
- [x] Build profile editor UI.

### Job Import

- [x] Add backend `jobs_cache` table for shared URL scrape/parse cache.
- [x] Store user saved-job relationships and notes in `user_saved_jobs`.
- [x] Add backend OpenAI parser contract for the structured job description JSON schema.
- [x] Add backend endpoint that saves pasted or URL-scraped job descriptions as raw text plus parsed JSON.
- [x] Add full manual job creation with title, company, description, deadline, location, salary, source URL, and notes.
- [x] Add copy/paste job description import.
- [x] Add URL import that attempts extraction and creates a reviewable draft after the text-only comparison prototype works.
- [x] Add fallback flow for failed URL extraction so the user can manually complete the job.
- [x] Store raw and structured job data.
- [x] Reuse existing parsed job data by URL when a matching job URL is already cached.
- [x] Build jobs list and detail UI.
- [x] Add bulk job-list discovery endpoint that extracts individual job posting URLs from a search/listing page without saving them.
- [x] Add bulk import review UI where the user selects discovered jobs before import.
- [x] Add selected-job bulk import endpoint that reuses `jobs_cache` and creates `user_saved_jobs` rows.
- [x] Add optional batch matching for imported jobs after the user selects a resume profile.
- [x] Add conservative limits, deduplication, source-access checks, and clear warnings for unsupported listing pages.
- [x] Add incremental Load More pagination for bulk job-list discovery using generalized next-page heuristics.
- [ ] Make `jobs_cache.job_data` nullable so bulk and provider-backed imports can save source data before OpenAI parsing.
- [ ] Change bulk job-list import to save `raw_description_text` and metadata without immediate OpenAI parsing unless match-on-import is selected.
- [ ] Add backend helper that ensures `job_data` exists by lazily parsing `raw_description_text`, saving the result, and reusing cached parsed data later.
- [ ] Update resume-job matching to call the lazy parse helper before scoring when selected jobs have no `job_data`.
- [ ] Add parse failure handling that shows a user-facing retry/manual-paste path.

### Apify Indeed Job Search

- [x] Add server-side `APIFY_API_TOKEN` environment variable support. The token must never be exposed to the client or committed config.
- [x] Use Apify actor `misceres/indeed-scraper` for the first Indeed integration.
- [x] Document the Apify run endpoints for actor `misceres~indeed-scraper`.
- [x] Document the `misceres/indeed-scraper` input shape using `position`, `location`, `country`, `maxItemsPerSearch`, `parseCompanyDetails`, `saveOnlyUniqueItems`, `followApplyRedirects`, and `startUrls`.
- [x] Add Apify service wrapper for running the synchronous dataset-items endpoint, handling failures, and reading dataset results.
- [x] Normalize Apify Indeed results into DaliJob job search result DTOs with title, company, location, source URL, raw description text, salary, employment type, posting date, and full description when available.
- [x] Add `POST /api/v1/job-search/indeed` endpoint accepting keyword, location, and max results with a default cap of 5.
- [x] Add server-side validation, timeouts, and clear errors for Apify token exhaustion, actor failure, empty results, or invalid input.
- [ ] Add request rate limiting and cost controls before production use.
- [x] Add new client Job Search page where the user enters keyword and location.
- [x] Display up to 5 Apify-sourced Indeed results in a reviewable list.
- [x] Add result detail view so the user can inspect the full job description before importing.
- [x] Add selection flow so the user can import one or more Apify search results.
- [x] Import selected Apify results through the existing `jobs_cache` and `user_saved_jobs` pipeline.
- [x] Reuse existing `jobs_cache` rows by `source_url` when Apify returns a job URL that is already cached.
- [x] Optionally support match-on-import after the user selects a resume profile, matching the existing bulk import behavior.
- [x] Add tests for Apify result normalization, search endpoint errors, import deduplication, and selected-job import.
- [x] Update README setup notes to document `APIFY_API_TOKEN` in `server/.env` after implementation.
- [ ] Change Apify selected-result import to defer OpenAI job parsing unless match-on-import is selected.

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

- [x] Add documents and document versions.
- [x] Add owner-protected local document upload endpoint.
- [x] Add owner-protected local document download endpoint.
- [x] Store redacted extracted text for supported uploaded documents.
- [ ] Add signed upload URL flow.
- [ ] Add signed download URL flow.
- [ ] Add application document attachments.
- [x] Add document list and preview UI.

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
- [ ] Link resume versions back to source document versions when created from uploaded files.
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

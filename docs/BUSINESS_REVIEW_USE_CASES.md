# Business Review And Use Cases

Status checked on 2026-07-08.

Implementation sequencing for these use cases is defined in the [DaliJob Implementation Plan](IMPLEMENTATION_PLAN.md). This review remains the current-state and business rationale; the plan is the executable delivery document.

## Executive View

DaliJob is best understood as a private career-search operating system for job seekers, not as a public job board and not as a standalone resume builder. The strongest business position in the current repo is:

- Help a candidate keep resume facts, uploaded documents, saved jobs, and match analysis in one private workspace.
- Use AI to turn messy resume/job text into structured, reviewable data.
- Use provider integrations as accelerators, not as requirements. Manual entry and pasted text remain core workflows.

The current implemented product is a Phase 1 career-matching MVP. It supports login, resume profile management, document upload/extraction, saved jobs, job import/search, and resume-to-job matching. Application tracking, cover letters, interview preparation, company/recruiter tracking, analytics, and background AI job queues are still roadmap items.

## Primary Business Users

### Job Seeker

The job seeker is the current primary user. They need to:

- Create a private account.
- Build reusable structured resume profiles.
- Upload or paste resume materials.
- Find or import job opportunities.
- Compare their resume against job descriptions.
- Save jobs and review match gaps.
- Decide which roles are worth applying to.

### Future Career Power User

The future power user has a larger search pipeline and will need:

- Application status tracking.
- Cover letter and tailored resume versioning.
- Interview preparation.
- Recruiter/company relationship history.
- Analytics across applications and outcomes.

### Ops/Admin User

The ops/admin user is not currently represented by a first-class admin UI. Today, ops/admin work is performed through repo configuration, database scripts, secret tables, deployment scripts, Apache, nanny, logs, and CI.

Ops/admin users need to:

- Keep the service deployed and healthy.
- Manage provider credentials and cost controls.
- Run migrations and validate database state.
- Monitor logs, errors, and abuse signals.
- Maintain DNS/TLS/routing/process management.
- Handle production support without exposing or modifying user data unnecessarily.

## Current Product Use Cases

### 1. Public Product Preview

Actor: anonymous visitor

Current implementation:

- Visit the homepage without logging in.
- See static preview cards for resume profiles, job search/import, saved jobs, matching, and match data.
- Navigate to login/register.

Business purpose:

- Explain product value before account creation.
- Keep costly and sensitive operations behind login.

Boundary:

- No live AI, scraping, upload, saved data, or provider calls should run for anonymous users.

### 2. Account Registration And Login

Actor: job seeker

Current implementation:

- Register with email, password, and display name.
- Log in with email/password.
- Receive a DaliJob bearer token.
- Access `/me` and private workspace-scoped APIs.

Business purpose:

- Establish a private user workspace for career data.
- Avoid requiring users to authenticate through another Dalifin app for the MVP.

Open business/security issue:

- Local auth still has a code fallback JWT secret documented in `docs/ISSUES_IDENTIFIED.md`.

### 3. Dashboard And Recommended Next Step

Actor: logged-in job seeker

Current implementation:

- See setup alerts.
- See recommended next step.
- See best matches.
- See recently saved jobs.

Business purpose:

- Reduce user confusion by telling them the next useful action.
- Move the user through the funnel: create resume profile -> import jobs -> analyze jobs -> run matching -> review best matches.

### 4. Resume Profile Management

Actor: job seeker

Current implementation:

- Create, update, delete, and list multiple resume profiles.
- Maintain one default resume.
- Edit structured resume data sections: headline, summary, experience, skills, education, certifications, projects, awards, publications, languages, volunteer, target roles, and notes.
- Sort default resume first.

Business purpose:

- Make structured resume facts the canonical source for matching and future document generation.
- Support multiple resume variants without mixing facts across target roles.

### 5. Resume PDF Import To Structured Profile

Actor: job seeker

Current implementation:

- Upload a PDF resume.
- Extract and redact resume text.
- Use OpenAI to parse the resume into structured `resume_data`.
- Review parsed suggestions before applying them.
- Apply suggestions into a new resume profile.

Business purpose:

- Reduce setup friction.
- Turn an existing resume into reusable structured data.

Important behavior:

- Parsing does not automatically overwrite saved profile data.
- Contact information is intentionally excluded from structured resume JSON.

### 6. Document Library

Actor: job seeker

Current implementation:

- Upload PDF or plain-text documents.
- Store document metadata and versions.
- Store redacted extracted text.
- Preview extracted text.
- Download uploaded document files.

Business purpose:

- Preserve source materials for later matching and profile workflows.
- Establish a foundation for future application attachments and resume/cover-letter versioning.

Risk:

- Uploaded documents are sensitive. Ops controls should include retention, access logging, backup policy, and eventually signed upload/download URLs.

### 7. Manual Job Creation And Saved Jobs

Actor: job seeker

Current implementation:

- Create manual jobs with title, company, source URL, raw description, structured job data, and notes.
- List saved jobs.
- Edit saved jobs and notes.
- Review match data on saved jobs.

Business purpose:

- Keep DaliJob useful when scraping, job boards, or AI providers fail.
- Let users track private referrals, recruiter emails, PDFs, and company-site postings.

### 8. Single Job URL/Text Import

Actor: job seeker

Current implementation:

- Create a reviewable job draft from a URL or pasted description.
- Parse one active draft with OpenAI into structured job data.
- Save the reviewed job.
- Reuse cached job data for known URLs.

Business purpose:

- Convert unstructured job postings into structured data that can be compared against resumes.

Open issue:

- `/jobs/draft` currently lacks API auth enforcement and can invoke OpenAI. See `docs/ISSUES_IDENTIFIED.md`.

### 9. Bulk Job List Import

Actor: job seeker

Current implementation:

- Paste a job-list/search-results URL.
- Discover individual job posting URLs.
- Review candidates before saving.
- Import selected jobs.
- Optionally run matching after import.
- Use lazy parsing so bulk import can save source data without immediate OpenAI cost.

Business purpose:

- Let a user build a candidate job pipeline quickly while keeping review control.

Open issue:

- `/jobs/import-list/discover` currently lacks API auth enforcement. See `docs/ISSUES_IDENTIFIED.md`.

### 10. Indeed Job Search Through Apify

Actor: job seeker

Current implementation:

- Enter keyword and location.
- Server calls Apify actor `misceres/indeed-scraper`.
- Show up to 5 results.
- Review full job descriptions.
- Select and import jobs.
- Optionally match imported jobs against a resume profile.

Business purpose:

- Provide convenient job discovery without making DaliJob a job board.
- Keep the provider token server-side.

Operational note:

- This is cost-bearing and should have rate limiting and quota controls before broad public use.

### 11. Resume-To-Job Matching

Actor: job seeker

Current implementation:

- Select a structured resume profile or paste resume text.
- Provide a job URL, pasted job text, or selected saved jobs.
- Ensure job data exists through lazy parsing.
- Run OpenAI comparison.
- Show score from 0 to 10, matched/missing skills, matched/missing keywords, supported/unsupported requirements, and recommended resume updates.
- Auto-save jobs with score >= 5.
- Ask whether to save low-score jobs.
- Store match results in `job_resume_matches`.

Business purpose:

- Help users decide which jobs deserve effort.
- Give actionable gap analysis rather than only a score.

Open issue:

- `/resume-job-matches/job-url-extract` currently lacks API auth enforcement. See `docs/ISSUES_IDENTIFIED.md`.

## Roadmap Use Cases Not Yet Implemented

These are described in docs/checklists but are not current product capabilities:

- Application tracker with statuses and timeline events.
- Company and recruiter/contact management.
- Tasks, reminders, and follow-ups.
- Tailored resume generation.
- Cover letter generation.
- Interview preparation and mock interview support.
- Offer/rejection/outcome tracking.
- Analytics such as response rate, funnel metrics, and historical learning.
- Background AI job queue, prompt versioning, usage logging, and provider abstraction beyond the current direct OpenAI calls.
- Admin console for user/support/provider management.

## Recommended Split: User Functions

User-facing product functions should be the workflows a job seeker directly understands and controls:

| Area | User functions |
| --- | --- |
| Account | Register, login, view current account |
| Dashboard | Review setup alerts, recommended next step, best matches, recent jobs |
| Resume profiles | Import, create, edit, delete, set default, review parsed suggestions |
| Documents | Upload, list, preview extracted text, download |
| Jobs | Search, import, manually create, edit, save, add notes, analyze |
| Matching | Compare resume to one job, compare resume to selected saved jobs, review match gaps |
| Public preview | Browse static read-only product previews before login |
| Future applications | Track application status, attach documents, log interviews, record outcomes |

User functions should not expose:

- Provider keys.
- OpenAI/Apify implementation details.
- Apache/nanny/process state.
- Raw DB schema details.
- Global usage/cost controls.
- Other users' data.

## Recommended Split: Ops/Admin Functions

Ops/admin functions should be isolated from the job seeker experience. They are currently CLI/config/database responsibilities, not in-app UI features.

| Area | Ops/admin functions |
| --- | --- |
| Deployment | Deploy code, configure Apache vhosts, manage TLS, route `jobmatch.dalifin.com` |
| Process management | Manage nanny entries, ports, logs, restarts, Node/Python runtime versions |
| Config | Manage ProcessConfig ini files, DB VIP settings, client origins, storage paths |
| Secrets | Manage `secret.key_store` provider keys, `dali_job.env`, JWT secret rotation |
| Database | Create schema, run Alembic migrations, validate schema, backfill/repair data |
| Provider operations | OpenAI/Apify key health, quota, rate limiting, timeout tuning, cost monitoring |
| Security | Auth mode policy, endpoint protection, abuse monitoring, file-retention policy |
| CI/release | Keep GitHub Actions green, validate OpenAPI, run server/client tests |
| Support | Investigate server logs, diagnose failed imports/matches, inspect user-owned records only when necessary |

Recommended future admin UI modules:

- Service health page: API, DB, client, provider status.
- Provider configuration status without showing full secrets.
- AI/Apify usage and cost dashboard.
- Failed job/import/match queue.
- User support lookup with audit logging and least-privilege access.
- Database maintenance dashboard for duplicate jobs, orphan documents, and migration status.

## Business Risk Review

### Cost Risk

OpenAI and Apify calls cost money. The code has useful lazy-parsing behavior, but several helper endpoints still need stronger auth and rate limiting. Before broad launch:

- Require auth for scraping/AI helper endpoints.
- Add per-user and per-IP rate limits.
- Add daily/monthly provider usage caps.
- Log provider calls by feature, user, and status.

### Privacy Risk

Resume documents and job search activity are sensitive. Current design redacts extracted resume text for structured storage, but the platform still stores uploaded files and document versions.

Before broader user adoption:

- Define retention policy.
- Restrict support access.
- Add audit logs for document access/download.
- Consider object storage with signed URLs.

### Reliability Risk

External providers can fail or change behavior:

- OpenAI models and schema behavior can change.
- Apify actor input/output shape can change.
- Job websites can block or alter pages.

Mitigation:

- Keep manual entry and pasted text as first-class fallbacks.
- Version prompts and schemas.
- Add provider health checks and clearer user-facing error messages.

### Data Quality Risk

The product promise depends on not inventing resume facts. Current prompts and schema design emphasize factual extraction and redaction, but the user still needs review control.

Mitigation:

- Keep AI output reviewable before saving.
- Preserve source text/document references.
- Store prompt/model metadata in future AI-generation records.

### Operational Risk

The repo still has known operational issues:

- CI likely fails on clean checkout because `DaliCommonLib` is a sibling editable dependency.
- Job-cache URL dedupe is not race-safe.
- Auth fallback behavior should be hardened.

These are tracked in `docs/ISSUES_IDENTIFIED.md`.

## Recommended Next Business Priorities

1. Close the high-severity security/cost issues in `docs/ISSUES_IDENTIFIED.md`.
2. Add rate limiting and provider usage logging for OpenAI and Apify.
3. Improve user-facing AI/provider error messages so failures do not appear as generic 500s.
4. Add application tracking, because that completes the core career-search loop after matching.
5. Add document/version relationships to saved jobs and future applications.
6. Add basic analytics only after applications and outcomes exist.
7. Defer admin UI until operational tasks repeat enough to justify productizing them.

## Current Business Boundary

In its current state, DaliJob is production-usable as a private MVP for:

- Resume profile setup.
- Job import/search.
- Saved jobs.
- Resume-to-job matching.
- Document upload/extraction.

It is not yet a full application-tracking CRM. It also does not yet have an in-app admin console. Ops/admin work remains outside the product UI and should stay separated from candidate-facing workflows.

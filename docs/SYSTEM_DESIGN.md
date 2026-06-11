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

- Paste job URL.
- Upload PDF job description.
- Copy and paste job description.
- Import from supported integrations.
- Optional aggregation plugins.

Initial plugin candidates:

- Greenhouse.
- Lever.
- USAJobs.
- Adzuna.
- Remotive.

Plugins must normalize imported postings into the internal job model and must not be required for the application tracker to work.

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

- Match score.
- Missing skills.
- Relevant projects.
- Relevant experience.
- Recommended resume changes.
- Recommended cover letter themes.
- Recommended study topics.

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

### Document Service

Responsibilities:

- Upload validation.
- Object storage.
- Versioning.
- Text extraction.
- Preview generation.
- PDF/DOCX rendering.

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
- The client must not access PostgreSQL, Redis, object storage credentials, OAuth secrets, or AI provider keys.
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
- Role-based permissions.
- Workspace-scoped authorization.
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

- Server: Python, FastAPI, SQLAlchemy, PostgreSQL, Alembic.
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

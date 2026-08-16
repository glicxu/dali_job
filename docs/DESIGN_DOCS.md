# DaliJob Design Documents

This folder contains the active project design package for DaliJob, an AI-assisted career management platform.
Documents unchanged from `main` have been moved to [`archive/`](archive/) so the top level stays focused on current work.

DaliJob is designed as a long-term career operating system, not a job board and not only a resume builder. The application should remain useful without AI enabled, while AI adds resume tailoring, cover letters, job analysis, interview preparation, email classification, and career intelligence.

## Documents

- [SYSTEM_DESIGN.md](archive/SYSTEM_DESIGN.md) - archived product architecture, modules, service boundaries, workflows, AI boundaries, security, and non-functional requirements.
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - entities, fields, enums, relationships, indexing, and versioning rules.
- [ER_MODEL_OVERVIEW.md](archive/ER_MODEL_OVERVIEW.md) - archived plain-English explanation of entities, relationships, and database design rules.
- [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) - functional and architectural review of current risks, gaps, low-value areas, and recommended next steps.
- [IMPLEMENTATION_PLAN.md](archive/IMPLEMENTATION_PLAN.md) - archived use-case-first delivery plan with dependencies, work packages, acceptance criteria, and release boundaries.
- [MOBILE_AUTOMATED_MATCHING_IMPLEMENTATION_PLAN.md](MOBILE_AUTOMATED_MATCHING_IMPLEMENTATION_PLAN.md) - mobile-first account onboarding, tier-based recurring searches, automatic resume matching, quotas, notifications, and phased delivery plan.
- [GUEST_TRYOUT_EXPERIENCE_DESIGN.md](GUEST_TRYOUT_EXPERIENCE_DESIGN.md) - account-free trial journey, profile-readiness gate, one-result guest matching, conversion and claim semantics, privacy, abuse controls, APIs, and rollout plan.
- [3-step_matching_v2.md](3-step_matching_v2.md) - revised evidence-based matching architecture with separated model/code responsibilities, deterministic qualification and preference scoring, bounded trial execution, versioned artifacts, and migration guidance.
- [THREE_STEP_MATCHING_IMPLEMENTATION_PLAN.md](THREE_STEP_MATCHING_IMPLEMENTATION_PLAN.md) - phased delivery plan for schemas, persistence, extraction, deterministic assessment and scoring, orchestration, guest and scheduled integration, clients, testing, and controlled rollout of the three-step matcher.
- [MATCHING_EVALUATION_PLAN.md](MATCHING_EVALUATION_PLAN.md) - frozen benchmark and golden-set plan for evaluating Candidate Profiles, Job Profiles, and Qualification Assessments with an initial curated ten-job tier-1 company set and a later one-hundred-job expansion.
- [ASK_SCOUT_IMPLEMENTATION_PLAN.md](archive/ASK_SCOUT_IMPLEMENTATION_PLAN.md) - archived passive AI navigation assistant implementation plan.
- [ASK_SCOUT_V2_IMPROVEMENT_PLAN.md](archive/ASK_SCOUT_V2_IMPROVEMENT_PLAN.md) - archived Ask Scout V2 improvement plan.
- [JOB_SCRAPER_GENERALIZATION_PLAN.md](archive/JOB_SCRAPER_GENERALIZATION_PLAN.md) - archived job URL extraction plan.
- [UI_OVERHAUL_IMPLEMENTATION_PLAN.md](archive/UI_OVERHAUL_IMPLEMENTATION_PLAN.md) - archived UI overhaul implementation plan.
- [UI_OVERHAUL_BASELINE.md](archive/UI_OVERHAUL_BASELINE.md) - archived UI overhaul baseline.
- [DATA_LIFECYCLE.md](DATA_LIFECYCLE.md) - archive/delete semantics, immutable match history, retention, export, and account cleanup contract.
- [API_SPEC.md](API_SPEC.md) - versioned REST API specification for the client, workers, and integrations.
- [ER_DIAGRAM.md](archive/ER_DIAGRAM.md) - archived Mermaid ER diagram and relationship notes.
- [FOLDER_STRUCTURE.md](archive/FOLDER_STRUCTURE.md) - archived application and infrastructure layout.
- [IMPLEMENTATION_CHECKLIST.md](archive/IMPLEMENTATION_CHECKLIST.md) - archived phased build checklist.
- [GITHUB_ISSUES.md](archive/GITHUB_ISSUES.md) - archived starter backlog.
- [TESTING_STRATEGY.md](archive/TESTING_STRATEGY.md) - archived testing strategy.
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - local, staging, production, CI/CD, observability, and operations guidance.
- [US3_PROD_DEPLOYMENT_PLAN.md](US3_PROD_DEPLOYMENT_PLAN.md) - concrete plan for deploying DaliJob on us3 at `https://jobmatch.dalifin.com`.
- [PRODUCTION_READINESS.md](archive/PRODUCTION_READINESS.md) - archived launch readiness tracker.
- [OPERATIONS_RUNBOOK.md](archive/OPERATIONS_RUNBOOK.md) - archived operations runbook.
- [RELEASE_AND_ROLLBACK.md](RELEASE_AND_ROLLBACK.md) - versioned artifact, deployment readback, retention, and database roll-forward policy.

## Product Phases

0. Phase 0.5: barebones server/client plus pasted-text resume-to-job matching prototype with OpenAI and a 0-10 score.
1. Phase 1: accounts, multiple resume profiles with one default, job import, application tracking, document management, notes, and basic analytics.
2. Phase 2: AI resume tailoring, cover letters, job analysis, match scoring, and gap analysis.
3. Phase 3: interview preparation, company summaries, study guides, question generation, interview journal, and mock interviews.
4. Phase 4: email integration, calendar integration, career intelligence, trend analysis, and learning recommendations.

## Preferred Stack

- Server: Python, FastAPI, SQLAlchemy, Alembic, and `DaliCommonLib`.
- Database access: `DaliCommonLib.dali_db_man.DbMan`.
- Runtime config: `DaliCommonLib.dali_config.ProcessConfig` loaded with `--config [config_file_name].ini`.
- SQL database: MySQL-compatible by default because `DbMan` currently uses `mysql+pymysql` configuration.
- Background work: Celery or equivalent queue workers.
- Cache and broker: Redis.
- Storage: S3-compatible object storage.
- Client: React and Next.js.
- AI: provider abstraction layer with versioned prompts and schema-validated outputs.

## Client And Server Separation

DaliJob should use a clear client/server split. All server-side code belongs in a top-level `server/` folder, and all client-side code belongs in a top-level `client/` folder.

The client and server communicate only through documented API contracts. The client must not import server modules, read server configuration, access the database directly, or depend on server implementation details. This allows either side to be changed, deployed, tested, or replaced independently as long as the API contract remains compatible.

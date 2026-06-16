# DaliJob Design Documents

This folder contains the project design package for DaliJob, an AI-assisted career management platform.

DaliJob is designed as a long-term career operating system, not a job board and not only a resume builder. The application should remain useful without AI enabled, while AI adds resume tailoring, cover letters, job analysis, interview preparation, email classification, and career intelligence.

## Documents

- [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) - product architecture, modules, service boundaries, workflows, AI boundaries, security, and non-functional requirements.
- [DATABASE_DESIGN.md](DATABASE_DESIGN.md) - entities, fields, enums, relationships, indexing, and versioning rules.
- [API_SPEC.md](API_SPEC.md) - versioned REST API specification for the client, workers, and integrations.
- [ER_DIAGRAM.md](ER_DIAGRAM.md) - Mermaid ER diagram and relationship notes.
- [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) - recommended FastAPI, Next.js, worker, plugin, and infrastructure layout.
- [IMPLEMENTATION_CHECKLIST.md](IMPLEMENTATION_CHECKLIST.md) - phased build checklist aligned to the MVP and later roadmap.
- [GITHUB_ISSUES.md](GITHUB_ISSUES.md) - starter backlog that can be copied into GitHub issues.
- [TESTING_STRATEGY.md](TESTING_STRATEGY.md) - unit, integration, end-to-end, AI evaluation, and security testing.
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - local, staging, production, CI/CD, observability, and operations guidance.

## Product Phases

0. Phase 0.5: barebones server/client plus pasted-text resume-to-job matching prototype with OpenAI and a 0-10 score.
1. Phase 1: accounts, profile, resume storage, job import, application tracking, document management, notes, and basic analytics.
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

# DaliJob Folder Structure

## Recommended Repository Layout

```text
dali-job/
  server/
    app/
      main.py
      core/
        config.py
        security.py
        logging.py
        errors.py
      db/
        base.py
        session.py
        migrations/
      modules/
        auth/
          router.py
          service.py
          schemas.py
          models.py
        workspaces/
        profiles/
        jobs/
        applications/
        documents/
        resumes/
        cover_letters/
        interviews/
        analytics/
        integrations/
        email/
        calendar/
        ai/
        job_sources/
      workers/
        celery_app.py
        resume_tasks.py
        cover_letter_tasks.py
        job_analysis_tasks.py
        document_tasks.py
        email_tasks.py
        calendar_tasks.py
        analytics_tasks.py
      shared/
        enums.py
        pagination.py
        permissions.py
        storage.py
        events.py
    tests/
      unit/
      integration/
      e2e/
      factories/
    pyproject.toml
    alembic.ini

  client/
    app/
      layout.tsx
      page.tsx
      applications/
      jobs/
      profile/
      documents/
      interviews/
      analytics/
      settings/
    components/
      ui/
      forms/
      tracker/
      resume/
      documents/
      charts/
    lib/
      api.ts
      auth.ts
      dates.ts
      validation.ts
    hooks/
    styles/
    tests/
    package.json

  plugins/
    job_sources/
      base/
        contract.py
        manifest.schema.json
      greenhouse/
      lever/
      usajobs/
      adzuna/
      remotive/

  infrastructure/
    docker/
      Dockerfile.server
      Dockerfile.client
      docker-compose.yml
    terraform/
      staging/
      production/
    scripts/
      run_local.ps1
      seed_dev_data.py

  scripts/
    create_schema.py
    create_tables.py
    seed_database.py
    validate_database.py

  requirements.txt

  docs/
    DESIGN_DOCS.md
    SYSTEM_DESIGN.md
    DATABASE_DESIGN.md
    API_SPEC.md
    ER_DIAGRAM.md
    FOLDER_STRUCTURE.md
    IMPLEMENTATION_CHECKLIST.md
    GITHUB_ISSUES.md
    TESTING_STRATEGY.md
    DEPLOYMENT_GUIDE.md
```

## Client/Server Boundary Rules

All server-side code belongs under `server/`. This includes API routes, database models, business services, workers, AI orchestration, document rendering, integrations, migrations, and server tests.

All client-side code belongs under `client/`. This includes Next.js routes, React components, browser-facing state, client API wrappers, UI tests, and client styling.

Boundary rules:

- The client calls the server through `/api/v1` endpoints.
- The client does not import Python modules, SQLAlchemy models, server settings, or database code.
- The server does not import React components or client-only code.
- Shared types should be generated from OpenAPI or stored as explicit contract artifacts.
- Client and server can be built, tested, and deployed independently.
- API compatibility should be protected by contract tests.

## Server Module Pattern

Each server module should follow the same internal shape where useful:

```text
module_name/
  router.py       # FastAPI routes
  service.py      # Business workflow
  repository.py   # Database access
  schemas.py      # Pydantic request/response schemas
  models.py       # SQLAlchemy models
  events.py       # Event payloads and handlers
  permissions.py  # Module-specific auth checks
```

Keep business rules in services, not routers. Keep database queries in repositories, not services. Keep external provider calls behind adapters.

Database repositories should use a small local adapter around `DaliCommonLib.dali_db_man.DbMan`. Do not create independent SQLAlchemy engines or direct database connection strings inside feature modules.

`server/app/main.py` should parse `--config [config_file_name].ini`, call `create_app(config_path)`, and stay small. `server/app/config.py` should own the `_load_process_config` style function that calls `DaliCommonLib.dali_config.ProcessConfig.load_config()`, following the existing `app_server` pattern.

## AI Package Structure

```text
server/app/modules/ai/
  router.py
  service.py
  jobs.py
  providers/
    base.py
    openai_provider.py
    mock_provider.py
  prompts/
    parse_resume_v1.md
    parse_job_description_v1.md
    tailor_resume_v1.md
    cover_letter_v1.md
    classify_email_v1.md
    interview_prep_v1.md
  validators/
    resume_validator.py
    cover_letter_validator.py
    job_analysis_validator.py
  schemas/
    resume.py
    job_analysis.py
    interview_prep.py
```

## Plugin Contract Structure

```text
plugins/job_sources/{plugin_id}/
  plugin.json
  client.py
  normalizer.py
  tests/
```

Plugin manifest:

```json
{
  "id": "greenhouse",
  "display_name": "Greenhouse",
  "version": "0.1.0",
  "supports_search": false,
  "supports_url_import": true,
  "requires_auth": false,
  "allowed_domains": ["greenhouse.io", "job-boards.greenhouse.io"],
  "rate_limit_policy": "conservative"
}
```

## Client Route Groups

Recommended first-screen app areas:

- `/applications` - main tracker.
- `/applications/[id]` - application detail, documents, timeline, interviews.
- `/jobs` - imported jobs and analysis.
- `/jobs/import` - bulk job-list import discovery, review, selection, and selected-job import.
- `/profile` - career source-of-truth editor.
- `/documents` - uploaded and generated files.
- `/analytics` - funnel, skills, and resume performance.
- `/settings/integrations` - email, calendar, and job source settings.

## Configuration Boundaries

Server settings should live in server config:

- Database settings from `ProcessConfig` `mysql` section.
- Redis URL.
- Object storage config.
- AI provider config.
- OAuth provider config.
- Feature flags.
- Encryption keys.

Do not read environment variables directly throughout the codebase. Use a typed settings object loaded from `ProcessConfig` and optional environment overrides.

The server should support:

```powershell
python -m app.main --config local.ini
python -m app.main --config production.ini
```

The root `requirements.txt` should include the local shared library path:

```text
-e ../DaliCommonLib
```

## Database Scripts

Top-level database scripts should use the same config mechanism as the server:

```powershell
python scripts/create_schema.py --config local.ini
python scripts/create_tables.py --config local.ini
python scripts/seed_database.py --config local.ini
python scripts/validate_database.py --config local.ini
```

Rules:

- Load config through `DaliCommonLib.dali_config.ProcessConfig`.
- Use `DaliCommonLib.dali_db_man.DbMan`.
- Operate on the DaliJob schema specified by the config file.
- Do not hard-code local or production credentials.
- Keep scripts safe by requiring explicit flags before destructive reset/drop behavior.

Client configuration should be limited to public runtime values such as API base URL, feature flags safe for browser exposure, and analytics settings. Secrets must never be placed in `client/`.

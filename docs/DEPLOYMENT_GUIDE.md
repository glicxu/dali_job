# DaliJob Deployment Guide

## 1. Environments

Recommended environments:

- Local development.
- Staging.
- Production.

Each environment should have separate:

- Database.
- Redis or queue broker.
- Object storage bucket.
- OAuth app credentials.
- AI provider keys.
- Encryption keys.
- Monitoring project.

## 2. Runtime Components

Required:

- Next.js client.
- FastAPI server.
- MySQL-compatible SQL database accessed through `DaliCommonLib.dali_db_man.DbMan`.
- Private server filesystem storage for the current single-instance document implementation.
- A scheduler that runs the bounded guest-retention purge command against the same database and private filesystem.

Future optional:

- External worker and queue broker.
- S3-compatible object storage.
- Search service.
- Dedicated document rendering service.
- Dedicated plugin runner.
- Dedicated analytics worker.

## 3. Local Development

Recommended local commands:

```powershell
docker compose up -d mysql minio
pip install -r requirements.txt
cd server
alembic -x config=local.ini upgrade head
python -m app.main --config local.ini
```

```powershell
cd client
npm install
npm run dev
```

Run workers after Redis and background queues are introduced:

```powershell
docker compose up -d redis
cd server
celery -A app.workers.celery_app worker --loglevel=info
```

Run and verify guest retention locally:

```powershell
python scripts/purge_guest_trials.py --config local.ini --dry-run --limit 100
python scripts/purge_guest_trials.py --config local.ini --limit 100
```

Assign the internal unlimited test entitlement only through the audited operator command. The account must already exist and have signed in once:

```powershell
python scripts/set_subscription_tier.py --config local.ini --email job@dalifin.local --tier super
```

Use the same command with `--tier free` to remove the override. Never map an Apple or Google subscription product to `super`; customer products remain Free, Starter, and Plus.

In an immutable release, use the release-contained module instead:

```powershell
cd server
python -m app.modules.guest_trials.purge_service --config production.ini --limit 100
```

Schedule that one-pass command at least every 15 minutes for the guest beta. It is bounded and idempotent, so the scheduler may invoke it again after interruption. Exit code `2` means at least one trial could not be safely purged; alert operators and retain the database record for retry. The purge process must mount the same document storage root as the API. Run `--dry-run` after deployment and before enabling the destructive schedule.

## 4. Configuration

Required server variables:

- `OPENAI_API_KEY`
- `DALIJOB_SMTP_PASSWORD`
- `APIFY_API_TOKEN` when provider-backed job search is enabled

Future worker/object-storage deployments will also require broker, object-storage, and encryption credentials. They are not required for the current single-instance architecture.

Required server dependency:

- The root `requirements.txt` must include `-e ../DaliCommonLib` so pip installs the shared library locally.

Required runtime config:

- The server must accept `--config [config_file_name].ini`.
- `server/app/config.py` must load that file through `DaliCommonLib.dali_config.ProcessConfig`.
- Local, staging, and production database switching should happen by passing different ini files, not by editing code.
- Production must configure exact HTTPS client origins, `public_client_url`, SMTP delivery, database-backed session lifetimes, rotating logs, and audit retention metadata as shown in `server/config.example.ini`.

Required `ProcessConfig` database section:

```ini
[mysql]
user = dali_user
passwd = local_password
active_server = local_db_host
active_db_schema = jobs
port = 3306
pool_size = 5
pool_max_overflow = 10
pool_timeout = 30
```

Required OpenAI config for the resume-to-job match prototype:

```ini
[openai]
model = configured_model_name
```

The OpenAI API key must be set as an environment variable for the server process:

```powershell
$env:OPENAI_API_KEY = "your_openai_api_key"
```

For a persistent user-level Windows environment variable:

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your_openai_api_key", "User")
```

The OpenAI API key must stay server-side. The client should never receive or store it, and config files should not contain it.

Database setup scripts:

```powershell
python scripts/create_schema.py --config local.ini
python scripts/create_tables.py --config local.ini
python scripts/seed_database.py --config local.ini
python scripts/validate_database.py --config local.ini
```

These scripts should operate on the schema specified by the config file, such as `mysql.active_db_schema = jobs`.

Future integration variables:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `MICROSOFT_CLIENT_ID`
- `MICROSOFT_CLIENT_SECRET`
- `GOOGLE_CALENDAR_CLIENT_ID`
- `GOOGLE_CALENDAR_CLIENT_SECRET`
- `MICROSOFT_CALENDAR_CLIENT_ID`
- `MICROSOFT_CALENDAR_CLIENT_SECRET`
- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`
- `USAJOBS_API_KEY`

Feature flags:

- `FEATURE_AI_RESUME`
- `FEATURE_COVER_LETTERS`
- `FEATURE_EMAIL_INTEGRATION`
- `FEATURE_CALENDAR_INTEGRATION`
- `FEATURE_JOB_SOURCE_PLUGINS`
- `FEATURE_MOCK_INTERVIEWS`
- `FEATURE_CAREER_INTELLIGENCE`

Required client variables:

- `NEXT_PUBLIC_API_BASE_URL`

Client variables must be safe to expose in a browser. Secrets belong only in server or infrastructure configuration.

## 5. Deployment Topology

```text
Browser
  -> CDN / Client Host
  -> FastAPI Server
       -> SQL Database via DbMan
       -> Private local document storage
       -> Secrets Manager
  -> Future Worker Pool
       -> AI Provider
       -> Email Providers
       -> Calendar Providers
       -> Job Source Plugins
       -> Document Renderer
```

Worker queues should be separated by workload:

- `default`
- `ai`
- `documents`
- `email`
- `calendar`
- `plugins`
- `analytics`

This prevents slow document rendering or plugin imports from blocking email status detection or core app jobs.

## 6. Database Migrations

Rules:

- Run migrations before deploying application code that depends on new schema.
- Prefer backward-compatible migrations.
- Do not drop columns in the same release where code stops using them.
- Backfill derived data with worker jobs when possible.
- Test migrations against a copy of production-sized data before major releases.

Deployment sequence:

1. Build server and client artifacts.
2. Run database migrations.
3. Deploy server API.
4. Deploy workers.
5. Deploy client.
6. Run smoke tests.

Build and deploy the versioned CI artifact rather than rebuilding independently on the host. Keep at least two successful artifacts. Use the readback and roll-forward rules in [RELEASE_AND_ROLLBACK.md](RELEASE_AND_ROLLBACK.md); production Alembic downgrade is never automatic.

## 7. Object Storage

Use separate prefixes:

- `uploads/`
- `generated/resumes/`
- `generated/cover-letters/`
- `generated/interview-prep/`
- `email-bodies/`
- `previews/`

Security requirements:

- Buckets are private.
- Access only through short-lived signed URLs.
- Server-side encryption enabled.
- File content hashes stored in database.

## 8. Secrets Management

Use a managed secrets system in staging and production.

Never store these in source control:

- Session secrets.
- Encryption keys.
- AI provider keys.
- OAuth client secrets.
- Object storage secret keys.
- Database credentials.

Rotate:

- OAuth credentials after suspected exposure.
- AI keys after suspected exposure.
- Encryption keys using planned key versioning.

## 9. Observability

Metrics:

- API latency and error rate.
- Worker queue depth.
- AI job duration and failure rate.
- Document render duration and failure rate.
- Email sync latency.
- Calendar sync latency.
- Plugin failure rate.
- Database connection pool saturation.
- Guest trials eligible, purged, files deleted/missing, and purge failures.

Logs:

- Structured JSON logs.
- Request ID and user/workspace ID where appropriate.
- AI job ID and prompt version.
- Provider error codes.

Do not log:

- OAuth tokens.
- Full resume contents.
- Full email body.
- Generated document content.
- AI prompt payloads containing sensitive data.

Alerts:

- API 5xx rate spike.
- Worker queue backlog.
- Failed migration.
- AI provider error spike.
- Email sync failure spike.
- Object storage failures.
- Disk or memory pressure.
- Guest purge failures or expired-trial backlog.

## 10. Backups And Recovery

SQL database:

- Daily backups.
- Point-in-time recovery where available.
- Regular restore drills.

Object storage:

- Versioning if supported.
- Lifecycle rules for deleted temporary files.
- Backup strategy for critical generated and uploaded documents.

Redis:

- Treat queues as recoverable.
- Persist only if the selected queue system requires it.

## 11. Security Checklist

- HTTPS only.
- Secure cookies.
- Workspace authorization enforced.
- OAuth tokens encrypted.
- Signed URLs expire quickly.
- File upload validation enabled.
- Rate limits configured.
- Audit logging enabled.
- Dependency scanning enabled.
- CORS restricted to known client origins.
- Client cannot access database, Redis, object storage credentials, OAuth secrets, or AI provider keys.
- Admin operations protected.

## 12. Release Strategy

Recommended release phases:

1. Internal local prototype.
2. Private alpha with manual import, tracker, documents, and profile.
3. AI beta with resume tailoring, cover letters, and job analysis.
4. Interview beta with prep guides and journal.
5. Integrations beta with email and calendar.
6. Public release after security, privacy, export, deletion, monitoring, and backup processes are complete.

## 13. Rollback Strategy

- Keep previous server image available.
- Keep previous client build available.
- Use backward-compatible migrations where possible.
- For risky data changes, create rollback scripts or restore points.
- Feature-flag new AI and integration capabilities.

## 14. Production Readiness Gates

- All critical E2E flows pass.
- Owner-only cross-workspace authorization tests pass.
- Backup restore has been tested.
- Error monitoring is active.
- AI evals pass minimum thresholds.
- Email/calendar integrations can be revoked.
- Account data export and deletion are implemented.
- Privacy and AI disclosure copy is ready.

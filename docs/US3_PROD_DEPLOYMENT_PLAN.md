# DaliJob us3 Production Deployment Plan

This plan describes how to deploy DaliJob to the existing us3 production host and expose it at:

```text
https://jobmatch.dalifin.com
```

Keep this legacy/convenience entry point as a redirect:

```text
https://dalifin.com/job_match -> https://jobmatch.dalifin.com
```

This is a plan only. Do not change us3 until the repo/config diffs are reviewed and the target runtime ports are confirmed on the host.

## Goals

- Run the FastAPI DaliJob API as a private localhost service on us3.
- Run the Next.js DaliJob client as a private localhost service on us3.
- Expose the client through Apache at `https://jobmatch.dalifin.com/`.
- Expose the API through Apache at `https://jobmatch.dalifin.com/api/v1`.
- Redirect `https://dalifin.com/job_match` to `https://jobmatch.dalifin.com`.
- Use the production MySQL VIP and `jobs` schema.
- Keep secrets out of source control.

## Assumptions

- us3 is the Apache host for `dalifin.com`.
- us3 will also serve the new `jobmatch.dalifin.com` vhost.
- The tracked root-domain Apache vhost lives in `DaliConfigFile/web/apache2/dalifin.conf`.
- The live root-domain Apache vhost is `/etc/apache2/sites-available/dalifin.conf`.
- Add a dedicated tracked vhost for `jobmatch.dalifin.com`, likely `DaliConfigFile/web/apache2/jobmatch_dalifin.conf`.
- Existing Apache catch-all traffic for `dalifin.com` currently proxies `/` to another service, so `/job_match` should be a redirect rule on the root vhost, not a proxied Next.js subpath.
- Existing service ports must be checked before finalizing DaliJob ports.
- DaliJob uses `DaliCommonLib.dali_config.ProcessConfig` and `DaliCommonLib.dali_db_man.DbMan`.

## Proposed Runtime Ports

Confirm these on us3 before use:

```text
DaliJob API:     127.0.0.1:5020
DaliJob client:  127.0.0.1:3020
```

Avoid known existing ports:

```text
5002  Dali gateway
5003  Dali user/company service
5005  app_server
5010  may already be used by Dali AI
```

## Required Repo Changes

### Client Host

Serve the Next.js client at the root of `jobmatch.dalifin.com`.

Do not add a Next.js `basePath`. The app should keep generating normal root-relative Next assets such as:

```text
/_next/static/...
```

Build the production client with:

```text
NEXT_PUBLIC_API_BASE_URL=https://jobmatch.dalifin.com/api/v1
```

### Server CORS

The production DaliJob config should allow the public origin:

```ini
[dali_job]
client_origins = https://jobmatch.dalifin.com
```

Since the public client and API are on the same origin once routed through Apache, CORS should be simple. Keep it restrictive.

### Production Config

Add a DaliConfigFile-style production config, likely:

```text
DaliConfigFile/prod/config/app_dali_job.ini
```

Proposed shape:

```ini
[config file]
app_common = /data/dali/prod/config/app_common_mysql_vip.ini

[dali_job]
env = prod
host = 127.0.0.1
port = 5020
log_level = info
client_origins = https://jobmatch.dalifin.com
auth_mode = local

[dali_job_auth]
access_ttl_seconds = 604800

[mysql]
active_server = 10.0.0.10
active_db_schema = jobs
port = 3306
pool_size = 2
pool_max_overflow = 2
pool_timeout = 30

[documents]
storage_dir = /data/dali/prod/storage/dali_job/documents

[openai]
model = gpt-4.1-mini
```

Secrets must not be committed in plaintext unless this follows an existing protected production-config convention in `DaliConfigFile`.

Required server environment variables:

```text
DALIJOB_JWT_SECRET
OPENAI_API_KEY
APIFY_API_TOKEN
```

## Deployment Layout

Proposed us3 paths:

```text
/home/dali-op/dali/dali_job
/home/dali-op/dali/dali_job/.venv
/data/dali/prod/storage/dali_job/documents
/data/log/prod/service/dali_job_api
/data/log/prod/service/dali_job_client
```

us3 keeps source repositories under `/home/dali-op/dali`. Production config, logs, storage, and nanny scripts remain under `/data/dali/prod`.

## Build And Install

On us3:

```bash
cd /home/dali-op/dali/dali_job
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium firefox
```

Client:

```bash
cd /home/dali-op/dali/dali_job/client
npm ci
NEXT_PUBLIC_API_BASE_URL=https://jobmatch.dalifin.com/api/v1 npm run build
```

## Database Initialization

The production schema name is:

```text
jobs
```

Create and migrate this schema through the MySQL VIP configuration, not by pointing the application directly at a single MySQL node. In the current DaliConfigFile pattern, the VIP-backed common config is:

```text
/data/dali/prod/config/app_common_mysql_vip.ini
```

and the VIP host is:

```text
10.0.0.10
```

Before deployment, confirm with ops/DB inspection that `jobs` is created on the replicated MySQL topology and will fail over with the VIP.

Run only after confirming the config points at the intended production database:

```bash
cd /home/dali-op/dali/dali_job
.venv/bin/python scripts/create_schema.py --config /data/dali/prod/config/app_dali_job.ini

cd /home/dali-op/dali/dali_job/server
../.venv/bin/python -m alembic -x config=/data/dali/prod/config/app_dali_job.ini upgrade head

cd /home/dali-op/dali/dali_job
.venv/bin/python scripts/validate_database.py --config /data/dali/prod/config/app_dali_job.ini
```

Expected validation:

```text
Database validation passed for schema: jobs
```

## Runtime Entrypoints

Add DaliConfigFile-style scripts:

```text
DaliConfigFile/prod/bin/run_dali_job_api.sh
DaliConfigFile/prod/bin/run_dali_job_client.sh
```

API script shape:

```bash
#!/usr/bin/env bash
set -euo pipefail

ENV_FILE=/data/dali/prod/config/dali_job.env
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

cd /home/dali-op/dali/dali_job/server
exec ../.venv/bin/python -m app.main --config /data/dali/prod/config/app_dali_job.ini
```

Client script shape:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd /home/dali-op/dali/dali_job/client
exec npm run start -- --hostname 127.0.0.1 --port 3020
```

## Process Management

Use the existing Dali service nanny pattern, not one-off cron entries for the API/client processes.

Current production pattern:

- `DaliConfigFile/crontab/dali_ubuntu.cron` runs `/data/dali/prod/bin/dali_service_nanny.sh` every minute.
- `DaliConfigFile/prod/bin/dali_service_nanny.sh` selects a host-specific process list. For `us3`, it starts any missing service command.
- For several long-running services, the nanny checks the listening port instead of relying only on process name.
- Example: `dali_ai` is started through `run_ai_service.sh`, and the nanny treats port `5010` as the authoritative running signal.

Add DaliJob to the `us3` process list only after manual startup and localhost smoke tests pass:

```bash
"dali_job_api:/data/dali/prod/bin/run_dali_job_api.sh"
"dali_job_client:/data/dali/prod/bin/run_dali_job_client.sh"
```

Also extend `managed_service_port()` so the nanny can verify these generic Python/Node processes by listener port:

```bash
dali_job_api) printf '5020\n' ;;
dali_job_client) printf '3020\n' ;;
```

This is important because the actual OS process names will be generic (`python` and `node`), so `pgrep -x dali_job_api` or `pgrep -x dali_job_client` would not be reliable.

If the nanny's outside-window shutdown behavior must be authoritative for DaliJob, also extend stop logic to terminate by listener port for port-managed services. The current main benefit we need is automatic restart if the API or client stops.

Do not add separate cron lines for DaliJob API or DaliJob client. Cron should continue to run only the nanny.

## Secrets Handling

DaliJob should not commit OpenAI, Apify, JWT, or other production secrets into this repo.

The Dali AI service uses a DaliConfigFile config for non-secret settings such as model names and server ports. Its startup code can load a dotenv file from `[dali_ai].env_path` when configured. That is the useful pattern to follow: keep provider secrets outside source control and load them into the process environment before the service starts.

For DaliJob, use a protected env file sourced by `run_dali_job_api.sh`:

```text
/data/dali/prod/config/dali_job.env
```

Suggested contents:

```bash
DALIJOB_JWT_SECRET=<long random production jwt secret>
OPENAI_API_KEY=<production openai key>
APIFY_API_TOKEN=<production apify token>
```

Permissions:

```bash
sudo chown dali-op:dali-op /data/dali/prod/config/dali_job.env
sudo chmod 600 /data/dali/prod/config/dali_job.env
```

The DaliJob server reads all production secrets from the process environment:

- `DALIJOB_JWT_SECRET` signs and verifies local-auth bearer tokens.
- `OPENAI_API_KEY` is used by OpenAI-backed parsing and matching.
- `APIFY_API_TOKEN` is used by the Indeed job-search integration.

The run script source step is enough for these values. Keep non-secret runtime settings in `/data/dali/prod/config/app_dali_job.ini`.

Do not copy the legacy hardcoded API-key pattern found in older AI code. DaliJob should use environment/config-only secrets.

## Apache Routing Plan

### Dedicated App Vhost

Create a new tracked Apache vhost in:

```text
DaliConfigFile/web/apache2/jobmatch_dalifin.conf
```

The vhost should proxy the app root to the Next.js client and `/api/v1` to the FastAPI server:

```apache
<VirtualHost *:80>
    ServerName jobmatch.dalifin.com

    Alias /.well-known/acme-challenge/ /var/www/dalifin/.well-known/acme-challenge/
    <Directory /var/www/dalifin/.well-known/acme-challenge/>
        Options None
        AllowOverride None
        Require all granted
    </Directory>

    RewriteEngine On
    RewriteCond %{REQUEST_URI} ^/\.well-known/acme-challenge/ [NC]
    RewriteRule ^ - [L]
    RewriteRule ^ https://jobmatch.dalifin.com%{REQUEST_URI} [R=301,L]
</VirtualHost>

<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName jobmatch.dalifin.com
    ServerAdmin webmaster@dalifin.com

    ErrorLog  ${APACHE_LOG_DIR}/jobmatch_error.log
    CustomLog ${APACHE_LOG_DIR}/jobmatch_access.log combined

    ProxyPreserveHost On
    ProxyRequests Off
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Host "jobmatch.dalifin.com"

    ProxyPass        /api/v1 http://127.0.0.1:5020/api/v1
    ProxyPassReverse /api/v1 http://127.0.0.1:5020/api/v1

    ProxyPass        / http://127.0.0.1:3020/
    ProxyPassReverse / http://127.0.0.1:3020/

    SSLEngine on
    Include /etc/letsencrypt/options-ssl-apache.conf
    SSLCertificateFile /etc/letsencrypt/live/jobmatch.dalifin.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/jobmatch.dalifin.com/privkey.pem
</VirtualHost>
</IfModule>
```

### Root Domain Redirect

Patch the tracked root-domain vhost in:

```text
DaliConfigFile/web/apache2/dalifin.conf
```

Insert a redirect for `/job_match` before the existing root catch-all proxy:

```apache
RedirectMatch 302 ^/job_match/?$ https://jobmatch.dalifin.com/
```

Apache validation on us3:

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

## Verification Plan

Before Apache change, verify localhost services on us3:

```bash
curl -s http://127.0.0.1:5020/api/v1/health
curl -I http://127.0.0.1:3020/
```

After Apache reload:

```bash
curl -I https://jobmatch.dalifin.com/
curl -s https://jobmatch.dalifin.com/api/v1/health
curl -I https://dalifin.com/job_match
```

Browser smoke test:

- Open `https://jobmatch.dalifin.com`.
- Open `https://dalifin.com/job_match` and confirm it redirects to `https://jobmatch.dalifin.com`.
- Register or log in.
- Confirm browser API requests go to `/api/v1/...` on `jobmatch.dalifin.com`.
- Create or view a resume profile.
- Save or import a job.
- Run a resume-to-job match if OpenAI and Apify credentials are configured.

## Rollback Plan

Apache rollback:

- Disable or remove the `jobmatch.dalifin.com` vhost.
- Remove or comment the `/job_match` redirect entry from the root `dalifin.com` vhost.
- Run `sudo apache2ctl configtest`.
- Reload Apache.

Runtime rollback:

- Stop DaliJob API and client processes.
- Restore the previous deployed repo revision if needed.

Database rollback:

- Prefer leaving the `jobs` schema in place unless a destructive rollback is explicitly required.
- If data rollback is needed, restore from backup or a pre-deployment snapshot.

## Open Questions

- Final us3 ports for API and client after live port inspection.
- Whether account identity should remain DaliJob-local for the first production release.
- Confirm the MySQL VIP replication/failover contract for the new `jobs` schema before public launch.
- Internal DNS should resolve `jobmatch.dalifin.com` to the same internal us3 address used by `dalifin.com`; current external DNS works for ACME, but this Windows environment cannot reach the public NAT address directly.
- Add real Apify credential under `secret.key_store` key `apify` or as `APIFY_API_TOKEN` in `/data/dali/prod/config/dali_job.env` before using Apify-backed job search in production. OpenAI uses `secret.key_store` key `openai` with `OPENAI_API_KEY` as local/dev fallback.

## Worklog

- 2026-07-08: Started deployment preparation. Local `dali_job` repo has pending deployment/config/doc changes; `DaliConfigFile` is on `master` with one pre-existing untracked `win_config/www_app_server_local.ini` file that is unrelated and will not be touched.
- 2026-07-08: Added local DaliConfigFile deployment artifacts: `prod/config/app_dali_job.ini`, `prod/bin/run_dali_job_api.sh`, `prod/bin/run_dali_job_client.sh`, `web/apache2/jobmatch_dalifin.conf`, root-domain `/job_match` redirect, and nanny entries for `dali_job_api`/`dali_job_client` with port checks on `5020`/`3020`.
- 2026-07-08: Re-ran focused auth tests after moving the JWT secret source to `DALIJOB_JWT_SECRET`; result: `3 passed, 1 warning`.
- 2026-07-08: Built the Next.js client with `NEXT_PUBLIC_API_BASE_URL=https://jobmatch.dalifin.com/api/v1`; result: production build completed successfully.
- 2026-07-08: Local Windows shell does not have `bash`, so `bash -n` checks for the new us3 shell scripts still need to run on us3 before enabling or restarting nanny-managed services.
- 2026-07-08: Verified DNS for `jobmatch.dalifin.com` resolves to us3 public IPv4 `67.160.35.181`; us3 SSH access works and reports Python 3.12.3, Node v18.19.1, npm 9.2.0, and bash 5.2.
- 2026-07-08: Confirmed us3 repo convention is `/home/dali-op/dali`; DaliJob source should deploy to `/home/dali-op/dali/dali_job`, not `/data/dali/prod/dali_job`. us3 does not yet have `/data/dali/prod/config/dali_job.env`; no local DaliJob `.env` exists. A generated JWT secret can bootstrap auth, but OpenAI/Apify credentials still need to be provided for full matching/import behavior.
- 2026-07-08: Deployed DaliJob source to `/home/dali-op/dali/dali_job`, installed Python dependencies using existing `/home/dali-op/dali/DaliCommonLib`, installed Playwright Chromium/Firefox runtimes, and built the Next.js client for `https://jobmatch.dalifin.com/api/v1`.
- 2026-07-08: Fixed the client lockfile after us3 npm rejected the previous lock as out of sync; clean `npm ci` plus production `next build` now succeeds on us3. npm emits an engine warning because `eslint-visitor-keys@5.0.1` wants Node 20.19+ while us3 has Node 18.19.1, but the build completes.
- 2026-07-08: Created `/data/dali/prod/config/dali_job.env` with generated `DALIJOB_JWT_SECRET` and mode `0600`; did not add placeholder OpenAI or Apify secrets.
- 2026-07-08: Initialized and migrated the VIP-backed MySQL schema `jobs`; `scripts/validate_database.py --config /data/dali/prod/config/app_dali_job.ini` reported `Database validation passed for schema: jobs`.
- 2026-07-08: Started API and client through `/data/dali/prod/bin/run_dali_job_api.sh` and `/data/dali/prod/bin/run_dali_job_client.sh`; API listens on `127.0.0.1:5020`, client listens on `127.0.0.1:3020`, and localhost smoke tests pass.
- 2026-07-08: Issued Let's Encrypt certificate for `jobmatch.dalifin.com`, expiring 2026-10-06, and reloaded Apache.
- 2026-07-08: Fixed `https://dalifin.com/job_match` by adding `ProxyPass /job_match !` before the root catch-all proxy; it now returns `302` to `https://jobmatch.dalifin.com/`.
- 2026-07-08: Verified Apache host-local HTTPS routes for `jobmatch.dalifin.com`: `/` returns the Next.js app and `/api/v1/health` returns DaliJob prod health. From the local Windows environment, direct public `jobmatch.dalifin.com` access still needs internal DNS/NAT resolution alignment.
- 2026-07-08: Updated DaliJob provider secret handling to read OpenAI from `secret.key_store` key `openai` and Apify from key `apify`, with `OPENAI_API_KEY` and `APIFY_API_TOKEN` environment variables as local/dev fallbacks.
- 2026-07-08: Created/updated `secret.key_store` row `access_id='apify'` with type `api_token` and `used_by='dali_job'`; credential is currently an empty JSON string placeholder until the full Apify token is entered directly on us3.
- 2026-07-08: Upgraded us3 system Node.js from Ubuntu package `18.19.1` to NodeSource `20.20.2-1nodesource1` with npm `10.8.2`. Rebuilt the DaliJob client with clean `npm ci` and production `next build`, restarted the client on `127.0.0.1:3020`, and verified Apache `/` plus `/api/v1/health` routes.

# DaliJob

DaliJob is an AI-assisted career management platform for managing the full career-search lifecycle: importing opportunities, analyzing jobs, tailoring resumes and cover letters, tracking applications, preparing for interviews, recording outcomes, and learning from historical data.

DaliJob is not a job board and not only a resume builder. Job aggregation is optional, and the application should remain useful even when AI or external integrations are disabled.

## Design Docs

The project design package is indexed in [docs/DESIGN_DOCS.md](docs/DESIGN_DOCS.md).

Key documents:

- [System Design](docs/SYSTEM_DESIGN.md)
- [Database Design](docs/DATABASE_DESIGN.md)
- [API Specification](docs/API_SPEC.md)
- [ER Diagram](docs/ER_DIAGRAM.md)
- [Folder Structure](docs/FOLDER_STRUCTURE.md)
- [Implementation Checklist](docs/IMPLEMENTATION_CHECKLIST.md)
- [GitHub Issues](docs/GITHUB_ISSUES.md)
- [Testing Strategy](docs/TESTING_STRATEGY.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)

## Architecture Direction

- `server/` will contain the FastAPI server, database models, workers, AI orchestration, integrations, and business logic.
- `client/` will contain the Next.js client application.
- The client and server communicate through the documented `/api/v1` API contract.
- Optional job aggregation belongs behind plugins and must not be required for the core app to run.

## Run Locally

Server settings come from a `ProcessConfig` ini file. Server secrets, including `OPENAI_API_KEY`, belong in `server/.env`, which is ignored by git.

Create a local server config from the safe example:

```powershell
Copy-Item server\config.example.ini server\config.ini
```

Then edit `server\config.ini` for your local database. Start the server from the `server` folder:

```powershell
python -m pip install -r requirements.txt
cd server
python -m app.main --config config.ini
```

Start the client from the `client` folder:

```powershell
cd client
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

The API defaults to `http://127.0.0.1:5010`; the client defaults to `http://127.0.0.1:3000`. Stop either process with `Ctrl+C` in its terminal.

## Planned Stack

- Server: Python, FastAPI, SQLAlchemy, Alembic, and `DaliCommonLib`.
- Database access: `DaliCommonLib.dali_db_man.DbMan` backed by `ProcessConfig` ini files.
- SQL database: MySQL-compatible by default because `DbMan` currently uses `mysql+pymysql` configuration.
- Initial AI feature: OpenAI-backed pasted-text resume-to-job matching with a 0-10 score.
- Client: React and Next.js.
- Workers: Celery or equivalent.
- Cache and broker: Redis.
- Storage: S3-compatible object storage.
- AI: provider abstraction layer with versioned prompts and schema-validated outputs.

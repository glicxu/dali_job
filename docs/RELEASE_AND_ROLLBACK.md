# Release And Rollback

## Artifact Policy

CI produces one versioned ZIP named with the DaliJob commit. It contains the compiled Next.js output, FastAPI source, migrations, runtime package inputs, release manifest, and retained Python/Node SBOMs. Keep at least the two most recent successful artifacts available on the deployment host in addition to CI retention.

## Deployment

1. Confirm the intended commit and all CI jobs.
2. Download and verify the versioned artifact and release manifest.
3. Extract into a new immutable release directory, such as `releases/<commit>`.
4. Install exactly from the artifact inputs and configure secrets outside the release directory.
5. Run `alembic -x config=<production.ini> upgrade head` before switching traffic to code that requires the new schema.
6. Start the API and client from the new release directory.
7. Run `scripts/check_readiness.py` and retain its output with the release record.
8. Run the guest purge module with `--dry-run`, confirm its document storage root matches the API, and retain the report.
9. Switch the `current` release pointer only after readiness passes.
10. Enable or update the scheduled one-pass guest purge only after the new release is active.

## Rollback

- Prefer application rollback to the immediately previous retained artifact only when its code is compatible with the current database schema.
- Never automatically run Alembic downgrades in production. Database changes use a roll-forward corrective migration unless a separately reviewed restore plan explicitly requires otherwise.
- If the current schema is incompatible with the previous application artifact, keep the current artifact active and deploy a forward fix.
- After any rollback, rerun API/database and client readiness probes and record the active commit, database revision, reason, and operator.

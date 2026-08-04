# DaliJob Operations Runbook

## Local Logs

The API writes rotating JSON-lines logs to the configured `[logging] directory`:

- `api.log` contains application and request records.
- `alerts.log` contains unhandled request failures and HTTP 5xx alerts.

Each request receives an `X-Request-ID`; the same value is included in API log records. Log files rotate at `max_bytes` and retain `backup_count` files. Keep the directory readable only by the service account.

Useful PowerShell queries:

```powershell
Get-Content server\logs\api.log -Tail 100
Get-Content server\logs\alerts.log -Tail 100
Get-Content server\logs\api.log | Select-String '"request_id":"the-id"'
```

## Account Support

1. Ask the user to use **Forgot password**. The response is deliberately identical whether an account exists or not.
2. A password-reset link expires after one hour, works once, and revokes every existing session when used.
3. An unverified user can request another verification email from the registration screen.
4. A soft-deleted or disabled account cannot sign in or reset its password. Restoring such an account is an explicit database-administration action until an administrative support workflow exists.
5. Never ask for a password or copy verification/reset tokens into tickets or logs.

## Readiness And Incident Triage

Run the release probe after deployment:

```powershell
python scripts\check_readiness.py --api-url https://example.com/api/v1 --client-url https://example.com
```

For a reported failure, record the UTC time and request ID, check `alerts.log`, then check `/api/v1/health/db`. If the database revision is behind, stop the release and apply the expected forward migration before serving the new API code.

The current alert destination is the local `alerts.log` file by product decision. External paging, host resource alerts, certificate alerts, and backup alerts remain deferred.

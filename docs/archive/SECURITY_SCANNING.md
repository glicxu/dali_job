# Security Scanning Policy

The DaliJob CI workflow applies the following baseline checks to every pull request and push to `main`:

- `pip-audit` scans `requirements-runtime.txt`. Any known vulnerability reported by the tool fails CI.
- `npm audit --omit=dev --audit-level=high` fails CI for high or critical vulnerabilities in production dependencies.
- Gitleaks scans the complete checked-out Git history and fails on detected committed credentials or tokens.

Local consistency checks such as `pip check` do not replace vulnerability scanning. Development-only Node findings are reviewed during dependency upgrades but do not block this initial production policy unless they affect generated production assets or build integrity.

## Exceptions

A scan finding may be temporarily excepted only when all of the following are recorded in a tracked issue:

1. The affected package, advisory, severity, and reachable DaliJob behavior.
2. Why an upgrade or removal is not currently viable.
3. Compensating controls and a named owner.
4. An expiration date no later than 30 days from approval.

Never suppress a secret finding by committing an allowlisted real credential. Revoke and rotate the credential, remove it from repository history where necessary, and allowlist only a verified false-positive pattern.

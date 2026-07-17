# DaliJob Data Lifecycle

This document defines the Phase 1 lifecycle contract for user-owned records, shared cache data, uploaded files, and AI results. It distinguishes behavior implemented now from account-level cleanup that requires a background worker.

## Implemented Record Lifecycle

### Saved jobs

- Archive hides a `user_saved_jobs` row from the normal Jobs list without removing its notes, effective job data, applications, or match history.
- Archived jobs can be listed with `include_archived=true` and restored.
- Delete is an owner-scoped soft delete using `deleted_at`.
- Delete is rejected with HTTP 409 while any application references the saved job, including an archived application. The user must remove that relationship or keep the saved job archived.
- Bulk delete reports deleted, missing, and application-blocked jobs independently.

### Resume profiles and documents

- Resume profile and document delete operations are owner scoped and soft-delete the selected record.
- A dependency endpoint reports active resume profiles and historical matches that reference the record.
- The first delete request is rejected with HTTP 409 when dependencies exist. The client displays those dependencies and requires an explicit confirmation before sending `force=true`.
- Foreign keys use `SET NULL` where the original record may be removed. Immutable match snapshots preserve the historical inputs after the reference is cleared.
- Soft deletion does not immediately remove an uploaded file from storage. Physical cleanup belongs to the retention worker described below.

### Shared job cache

- `jobs_cache` is server-owned shared source data and is never deleted through a user saved-job action.
- A soft-deleted cache row may be reactivated only by a trusted source-extraction or provider-normalization path.
- Reactivation clears `deleted_at` and fills only missing cache content; user payloads cannot overwrite shared cache data.

## Match History Contract

Every new `job_resume_matches` row stores:

- the exact structured resume input and effective job JSON used for the comparison;
- canonical SHA-256 hashes of both snapshots;
- provider, model, prompt version, output schema version, provider execution reference when available, and creation timestamp;
- the structured result and score.

Match rows are append-only through normal product APIs. Running Match again creates another row. The API compares stored hashes with the current resume profile and effective saved-job data and reports resume, job, and aggregate staleness. Rows created before Phase 1 have empty snapshots and are presented as legacy history rather than claiming inputs that were never stored.

## Retention Policy

Initial production defaults should be configurable and documented in the privacy notice:

| Data | Active retention | After user deletion |
| --- | --- | --- |
| Uploaded file and document version | Until user deletes the document or account | Soft deleted immediately; physical object removed within 30 days |
| Redacted extracted text | Same as its document version | Removed with the document cleanup job within 30 days |
| Resume and private edited-job JSON | Until user deletes the record or account | Soft deleted immediately; hard deleted within 30 days unless a legal hold applies |
| Match snapshots and AI output | Until the saved job/account is deleted | Hard deleted during account cleanup; individual source deletion may retain the snapshot after explicit warning |
| Interview records, journal notes, and prep snapshots | Until the application/account is deleted | Cascade with the owned application/account; operation payload follows the shorter operational retention window |
| Application source snapshot and derived analytics | Source snapshot follows the application; analytics are calculated on request and are not separately persisted | Removed with the application/account; no analytics artifact remains |
| Managed-operation request payloads | Retained only while queued/running or for a bounded failed/cancelled retry window | Erased immediately after success; failed/cancelled retry payloads are erased after seven days |
| Provider execution references and operational logs | 90 days by default | Expire on schedule; security audit records may use a separately disclosed period |
| Shared job cache | While useful and source-compliant | Server retention policy; never contains user notes or resume data |

Secrets, raw authorization headers, and unredacted resume contact data must not be written to application logs.

## Account And Workspace Export Design

Account export is a future asynchronous operation:

1. Create an owner-scoped export request with status, requested time, completion time, and expiry.
2. A worker reads a consistent workspace snapshot and emits JSON for profiles, saved jobs, applications, notes, tasks, events, and match history.
3. Include owned uploaded files and a manifest containing hashes and schema versions.
4. Store the encrypted archive behind a short-lived signed download URL.
5. Audit request, completion, download, expiry, and failure without logging exported content.
6. Delete the generated archive after seven days by default.

## Account And Workspace Deletion Design

Account deletion must be asynchronous and resumable:

1. Reauthenticate the owner, record consent, revoke sessions, and place the workspace in `deletion_pending` state.
2. Stop new provider jobs and writes for that workspace.
3. Delete owned database records in dependency order inside bounded transactions, while preserving shared `jobs_cache` rows.
4. Delete document objects and generated export artifacts, then verify storage keys no longer exist.
5. Pseudonymize any operational audit entry that must be retained and remove provider execution references from product rows.
6. Record completion/failure using a non-content audit identifier and retry partial cleanup idempotently.

The future implementation needs a deletion-request table, worker queue, retry/dead-letter handling, object-storage inventory, and an administrator-visible reconciliation report. A synchronous HTTP request must not attempt the entire cleanup.

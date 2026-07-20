"use client";

import { useCallback, useEffect, useState } from "react";
import {
  cancelManagedOperation,
  getAuthToken,
  getManagedOperationSummary,
  listManagedOperations,
  ManagedOperation,
  ManagedOperationSummary,
  retryManagedOperation,
} from "../lib/api";

function operationLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function progressLabel(operation: ManagedOperation): string {
  if (operation.progress_total && operation.progress_total > 1) {
    return `${operation.progress_current} of ${operation.progress_total}`;
  }
  return operation.progress_message || operation.status;
}

export function OperationsManager() {
  if (!getAuthToken()) {
    return (
      <section className="profile-card">
        <h2>Login required</h2>
        <p className="metadata">Log in to run provider-backed work and review its progress.</p>
        <a className="primary-link" href="/auth">Login / Register</a>
      </section>
    );
  }
  return <AuthenticatedOperationsManager />;
}

function AuthenticatedOperationsManager() {
  const [operations, setOperations] = useState<ManagedOperation[]>([]);
  const [summary, setSummary] = useState<ManagedOperationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [operationPayload, summaryPayload] = await Promise.all([
        listManagedOperations({ limit: 50 }),
        getManagedOperationSummary(),
      ]);
      setOperations(operationPayload.operations);
      setSummary(summaryPayload);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operations could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  async function retry(operationId: number) {
    setBusyId(operationId);
    try {
      await retryManagedOperation(operationId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The operation could not be retried.");
    } finally {
      setBusyId(null);
    }
  }

  async function cancel(operationId: number) {
    setBusyId(operationId);
    try {
      await cancelManagedOperation(operationId);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The operation could not be cancelled.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="operations-manager">
      {error ? <div className="error-banner">{error}</div> : null}
      {summary ? (
        <dl className="operation-summary">
          <div><dt>Queued</dt><dd>{summary.queued}</dd></div>
          <div><dt>Running</dt><dd>{summary.running}</dd></div>
          <div><dt>Failed</dt><dd>{summary.failed}</dd></div>
          <div><dt>Completed</dt><dd>{summary.succeeded}</dd></div>
        </dl>
      ) : null}

      <section className="profile-card">
        <div className="profile-card-header">
          <div>
            <h2>Recent Operations</h2>
            <p className="metadata">Searches, imports, parsing, and matching continue here if you leave their page.</p>
          </div>
          <button type="button" className="secondary-button" onClick={() => void refresh()}>Refresh</button>
        </div>
        {operations.length ? (
          <ul className="operation-list">
            {operations.map((operation) => (
              <li key={operation.id}>
                <div className="operation-main">
                  <div className="operation-title-row">
                    <strong>{operationLabel(operation.operation_type)}</strong>
                    <span className={`operation-status status-${operation.status}`}>{operation.status}</span>
                  </div>
                  <span className="metadata">{progressLabel(operation)} · Attempt {operation.attempt_count} of {operation.max_attempts}</span>
                  {operation.error_message ? <p className="operation-error">{operation.error_message}</p> : null}
                  {operation.provider ? <span className="metadata">Provider: {operation.provider}</span> : null}
                </div>
                <div className="button-row operation-actions">
                  {operation.status === "queued" || operation.status === "running" ? (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={busyId === operation.id}
                      onClick={() => void cancel(operation.id)}
                    >Cancel</button>
                  ) : null}
                  {(operation.status === "failed" || operation.status === "cancelled") && operation.attempt_count < operation.max_attempts ? (
                    <button
                      type="button"
                      disabled={busyId === operation.id}
                      onClick={() => void retry(operation.id)}
                    >Retry</button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="empty">No managed operations have run yet.</p>}
      </section>
    </div>
  );
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, RotateCcw, XCircle } from "lucide-react";
import {
  cancelManagedOperation,
  getAuthToken,
  getManagedOperationSummary,
  listManagedOperations,
  ManagedOperation,
  ManagedOperationSummary,
  retryManagedOperation,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, SectionHeader, SkeletonRows } from "./ui";

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

function operationTone(status: ManagedOperation["status"]): "info" | "success" | "danger" | "warning" {
  if (status === "succeeded") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "running") return "info";
  return "warning";
}

export function OperationsManager() {
  if (!getAuthToken()) {
    return (
      <EmptyState icon={Activity} title="Login required" description="Log in to run provider-backed work and review its progress." action={<a className="button-link" href="/auth">Login / Register</a>} />
    );
  }

  return <AuthenticatedOperationsManager />;
}

function AuthenticatedOperationsManager() {
  const [operations, setOperations] = useState<ManagedOperation[]>([]);
  const [summary, setSummary] = useState<ManagedOperationSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);

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
    } finally {
      setLoaded(true);
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
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
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
          <SectionHeader title="Recent operations" description="Searches, imports, parsing, and matching continue here if you leave their page." />
          <Button type="button" variant="secondary" size="compact" icon={RefreshCw} onClick={() => void refresh()}>Refresh</Button>
        </div>
        {!loaded ? <SkeletonRows count={4} /> : operations.length ? (
          <ul className="operation-list">
            {operations.map((operation) => (
              <li key={operation.id}>
                <div className="operation-main">
                  <div className="operation-title-row">
                    <strong>{operationLabel(operation.operation_type)}</strong>
                    <Badge tone={operationTone(operation.status)}>{operation.status}</Badge>
                  </div>
                  <span className="metadata">{progressLabel(operation)} | Attempt {operation.attempt_count} of {operation.max_attempts}</span>
                  {operation.error_message ? <p className="operation-error">{operation.error_message}</p> : null}
                  {operation.provider ? <span className="metadata">Provider: {operation.provider}</span> : null}
                </div>
                <div className="button-row operation-actions">
                  {operation.status === "queued" || operation.status === "running" ? (
                    <Button
                      type="button"
                      variant="secondary"
                      size="compact"
                      icon={XCircle}
                      disabled={busyId === operation.id}
                      onClick={() => void cancel(operation.id)}
                    >Cancel</Button>
                  ) : null}
                  {(operation.status === "failed" || operation.status === "cancelled") && operation.attempt_count < operation.max_attempts ? (
                    <Button
                      type="button"
                      size="compact"
                      icon={RotateCcw}
                      disabled={busyId === operation.id}
                      onClick={() => void retry(operation.id)}
                    >Retry</Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : <EmptyState icon={Activity} title="No managed operations" description="Provider-backed searches, imports, parsing, and matching will appear here." />}
      </section>
    </div>
  );
}

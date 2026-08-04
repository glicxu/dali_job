"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AdminReport,
  getCurrentUser,
  listAdminReports,
  updateAdminReport,
  UserReportStatus,
} from "../lib/api";

const STATUSES: UserReportStatus[] = ["new", "in_review", "resolved", "closed"];

export function AdminReports() {
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filter, setFilter] = useState<UserReportStatus | "all">("all");
  const [status, setStatus] = useState<UserReportStatus>("new");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => reports.find((report) => report.id === selectedId) ?? null,
    [reports, selectedId],
  );

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        if (user.role !== "admin") throw new Error("Admin access is required.");
        return listAdminReports();
      })
      .then((items) => {
        setReports(items);
        if (items.length > 0) selectReport(items[0]);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load admin reports."))
      .finally(() => setLoading(false));
  }, []);

  function selectReport(report: AdminReport) {
    setSelectedId(report.id);
    setStatus(report.status);
    setNotes(report.admin_notes ?? "");
  }

  async function saveReport() {
    if (!selected) return;
    setSaving(true);
    setError("");
    try {
      const updated = await updateAdminReport(selected.id, { status, admin_notes: notes || null });
      setReports((current) => current.map((report) => report.id === updated.id ? updated : report));
      selectReport(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the report.");
    } finally {
      setSaving(false);
    }
  }

  const visibleReports = filter === "all" ? reports : reports.filter((report) => report.status === filter);

  return (
    <>
      {error ? <p className="error-banner">{error}</p> : null}
      <section className="admin-diagnostics" aria-labelledby="admin-diagnostics-heading">
        <div>
          <p className="eyebrow">Diagnostics</p>
          <h2 id="admin-diagnostics-heading">System tools</h2>
        </div>
        <div className="button-row">
          <a className="button-link secondary-button" href="/health">System Health</a>
          <a className="button-link secondary-button" href="/job-url-debug">URL Debug</a>
        </div>
      </section>

      <section className="admin-report-section" aria-labelledby="admin-reports-heading">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">Support queue</p>
            <h2 id="admin-reports-heading">Submitted reports</h2>
          </div>
          <label className="compact-label">
            Status
            <select value={filter} onChange={(event) => setFilter(event.target.value as UserReportStatus | "all")}>
              <option value="all">All reports</option>
              {STATUSES.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
            </select>
          </label>
        </div>

        {loading ? <p className="empty">Loading report queue.</p> : null}
        {!loading && visibleReports.length === 0 ? <p className="empty">No reports match this filter.</p> : null}
        {visibleReports.length > 0 ? (
          <div className="admin-report-workspace">
            <div className="admin-report-list" aria-label="Submitted reports">
              {visibleReports.map((report) => (
                <button
                  type="button"
                  className={selectedId === report.id ? "selected" : ""}
                  key={report.id}
                  onClick={() => selectReport(report)}
                >
                  <span className={`report-status ${report.status}`}>{report.status.replace("_", " ")}</span>
                  <strong>{report.title}</strong>
                  <small>{report.reporter_display_name} · {new Date(report.created_at).toLocaleDateString()}</small>
                </button>
              ))}
            </div>

            <div className="admin-report-detail">
              {selected ? (
                <>
                  <div>
                    <p className="eyebrow">{selected.category}</p>
                    <h2>{selected.title}</h2>
                    <p className="metadata">{selected.reporter_display_name} · {selected.reporter_email}</p>
                  </div>
                  <p className="report-description">{selected.description}</p>
                  <label>
                    Status
                    <select value={status} onChange={(event) => setStatus(event.target.value as UserReportStatus)}>
                      {STATUSES.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
                    </select>
                  </label>
                  <label>
                    Internal notes
                    <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
                  </label>
                  <div className="button-row">
                    <button type="button" disabled={saving} onClick={saveReport}>{saving ? "Saving..." : "Save changes"}</button>
                  </div>
                </>
              ) : <p className="empty">Select a report to review it.</p>}
            </div>
          </div>
        ) : null}
      </section>
    </>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { Bug, HeartPulse, Inbox, Save } from "lucide-react";
import {
  AdminReport,
  getCurrentUser,
  listAdminReports,
  updateAdminReport,
  UserReportStatus,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, SectionHeader, SkeletonRows } from "./ui";

const STATUSES: UserReportStatus[] = ["new", "in_review", "resolved", "closed"];

function reportStatusTone(status: UserReportStatus): "neutral" | "info" | "success" | "warning" {
  if (status === "resolved") return "success";
  if (status === "in_review") return "warning";
  if (status === "new") return "info";
  return "neutral";
}

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
      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <section className="admin-diagnostics" aria-label="System tools">
        <SectionHeader title="System tools" description="Restricted diagnostic views for validating the client/server boundary and scraper output." />
        <div className="admin-diagnostic-links">
          <a className="admin-diagnostic-link" href="/health"><HeartPulse size={20} aria-hidden="true" /><span><strong>System health</strong><small>Review the configured API boundary.</small></span></a>
          <a className="admin-diagnostic-link" href="/job-url-debug"><Bug size={20} aria-hidden="true" /><span><strong>URL Debug</strong><small>Inspect extracted job posting text.</small></span></a>
        </div>
      </section>

      <section className="admin-report-section" aria-label="Submitted reports">
        <div className="section-heading-row">
          <SectionHeader title="Submitted reports" description={`${visibleReports.length} report${visibleReports.length === 1 ? "" : "s"} in this view`} />
          <label className="compact-label">
            Status
            <select value={filter} onChange={(event) => setFilter(event.target.value as UserReportStatus | "all")}>
              <option value="all">All reports</option>
              {STATUSES.map((value) => <option key={value} value={value}>{value.replace("_", " ")}</option>)}
            </select>
          </label>
        </div>

        {loading ? <SkeletonRows count={4} /> : null}
        {!loading && visibleReports.length === 0 ? <EmptyState icon={Inbox} title="No matching reports" description="No submitted support reports match this status filter." /> : null}
        {visibleReports.length > 0 ? (
          <div className="admin-report-workspace">
            <div className="admin-report-list" aria-label="Submitted reports">
              {visibleReports.map((report) => (
                <button
                  type="button"
                  className={selectedId === report.id ? "selected" : ""}
                  aria-pressed={selectedId === report.id}
                  key={report.id}
                  onClick={() => selectReport(report)}
                >
                  <Badge tone={reportStatusTone(report.status)}>{report.status.replace("_", " ")}</Badge>
                  <strong>{report.title}</strong>
                  <small>{report.reporter_display_name} | {new Date(report.created_at).toLocaleDateString()}</small>
                </button>
              ))}
            </div>

            <div className="admin-report-detail">
              {selected ? (
                <>
                  <div>
                    <p className="eyebrow">{selected.category}</p>
                    <h2>{selected.title}</h2>
                    <p className="metadata">{selected.reporter_display_name} | {selected.reporter_email}</p>
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
                    <Button type="button" icon={Save} loading={saving} onClick={saveReport}>Save changes</Button>
                  </div>
                </>
              ) : <EmptyState compact icon={Inbox} title="Report details" description="Select a report to review its description and update its status." />}
            </div>
          </div>
        ) : null}
      </section>
    </>
  );
}

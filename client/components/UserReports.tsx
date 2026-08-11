"use client";

import { FormEvent, useEffect, useState } from "react";
import { MessageSquarePlus, MessagesSquare } from "lucide-react";
import {
  createUserReport,
  listUserReports,
  UserReport,
  UserReportCategory,
} from "../lib/api";
import { AlertBanner, Badge, Button, EmptyState, SectionHeader, SkeletonRows, ToastRegion } from "./ui";

const CATEGORY_LABELS: Record<UserReportCategory, string> = {
  bug: "Bug or broken behavior",
  feedback: "Product feedback",
  account: "Account issue",
  other: "Other",
};

function reportStatusTone(status: UserReport["status"]): "neutral" | "info" | "success" | "warning" {
  if (status === "resolved") return "success";
  if (status === "in_review") return "warning";
  if (status === "new") return "info";
  return "neutral";
}

export function UserReports() {
  const [reports, setReports] = useState<UserReport[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState<UserReportCategory>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    listUserReports()
      .then(setReports)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load reports."))
      .finally(() => setLoading(false));
  }, []);

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const report = await createUserReport({ category, title, description });
      setReports((current) => [report, ...current]);
      setTitle("");
      setDescription("");
      setShowForm(false);
      setMessage("Your report was submitted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the report.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="account-tools support-reports" aria-label="Reports and feedback">
      <div className="section-heading-row">
        <SectionHeader title="Reports and feedback" description="Report a problem or share feedback, then track its review status here." />
        <Button type="button" variant={showForm ? "ghost" : "primary"} icon={MessageSquarePlus} onClick={() => setShowForm((current) => !current)}>{showForm ? "Cancel" : "Submit report"}</Button>
      </div>

      {error ? <AlertBanner tone="danger">{error}</AlertBanner> : null}
      <ToastRegion message={message || null} onDismiss={() => setMessage("")} />

      {showForm ? (
        <form className="stack-form report-form" onSubmit={submitReport}>
          <label>
            Category
            <select value={category} onChange={(event) => setCategory(event.target.value as UserReportCategory)}>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Title
            <input value={title} minLength={3} maxLength={160} required onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            Details
            <textarea value={description} minLength={10} maxLength={20000} required onChange={(event) => setDescription(event.target.value)} />
          </label>
          <div className="button-row">
            <Button type="submit" icon={MessageSquarePlus} loading={submitting}>Submit report</Button>
          </div>
        </form>
      ) : null}

      {loading ? <SkeletonRows count={3} /> : null}
      {!loading && reports.length === 0 ? <EmptyState icon={MessagesSquare} title="No submitted reports" description="Reports and feedback you submit will appear here with their review status." /> : null}
      {reports.length > 0 ? (
        <div className="report-history">
          {reports.map((report) => (
            <article key={report.id}>
              <div>
                <Badge tone={reportStatusTone(report.status)}>{report.status.replace("_", " ")}</Badge>
                <h3>{report.title}</h3>
                <p>{CATEGORY_LABELS[report.category]} | {new Date(report.created_at).toLocaleString()}</p>
              </div>
              <p>{report.description}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

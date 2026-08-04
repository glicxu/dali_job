"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  createUserReport,
  listUserReports,
  UserReport,
  UserReportCategory,
} from "../lib/api";

const CATEGORY_LABELS: Record<UserReportCategory, string> = {
  bug: "Bug or broken behavior",
  feedback: "Product feedback",
  account: "Account issue",
  other: "Other",
};

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
    <section className="account-tools support-reports" aria-labelledby="support-reports-heading">
      <div className="section-heading-row">
        <div>
          <p className="eyebrow">Support</p>
          <h2 id="support-reports-heading">Reports and feedback</h2>
          <p>Report a problem or share feedback, then track its review status here.</p>
        </div>
        <button type="button" onClick={() => setShowForm((current) => !current)}>
          {showForm ? "Cancel" : "Submit report"}
        </button>
      </div>

      {error ? <p className="error-banner">{error}</p> : null}
      {message ? <p className="status-banner">{message}</p> : null}

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
            <button type="submit" disabled={submitting}>{submitting ? "Submitting..." : "Submit report"}</button>
          </div>
        </form>
      ) : null}

      {loading ? <p className="empty">Loading reports.</p> : null}
      {!loading && reports.length === 0 ? <p className="empty">You have not submitted any reports.</p> : null}
      {reports.length > 0 ? (
        <div className="report-history">
          {reports.map((report) => (
            <article key={report.id}>
              <div>
                <span className={`report-status ${report.status}`}>{report.status.replace("_", " ")}</span>
                <h3>{report.title}</h3>
                <p>{CATEGORY_LABELS[report.category]} · {new Date(report.created_at).toLocaleString()}</p>
              </div>
              <p>{report.description}</p>
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

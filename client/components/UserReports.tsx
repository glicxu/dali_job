"use client";

import { FormEvent, useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import {
  createUserReport,
  UserReportCategory,
} from "../lib/api";
import { AlertBanner, Button, SectionHeader, ToastRegion } from "./ui";

const CATEGORY_LABELS: Record<UserReportCategory, string> = {
  bug: "Bug or broken behavior",
  feedback: "Product feedback",
  account: "Account issue",
  other: "Other",
};

export function UserReports() {
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState<UserReportCategory>("bug");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      await createUserReport({ category, title, description });
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
        <SectionHeader title="Reports and feedback" description="Report a problem or share feedback." />
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

    </section>
  );
}

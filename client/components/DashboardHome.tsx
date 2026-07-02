"use client";

import { useEffect, useState } from "react";
import {
  DashboardBestMatch,
  DashboardRecentJob,
  DashboardResponse,
  getDashboard,
} from "../lib/api";

function statusLabel(status: DashboardRecentJob["status"]): string {
  if (status === "needs_analysis") return "Needs analysis";
  if (status === "ready_to_match") return "Ready to match";
  if (status === "matched") return "Matched";
  return status;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function DashboardHome() {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function loadDashboard() {
    setError(null);
    setIsLoading(true);
    try {
      setDashboard(await getDashboard());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load homepage.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadDashboard();
  }, []);

  if (isLoading) {
    return (
      <section className="panel">
        <p className="empty">Loading homepage.</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <div className="error-banner">{error}</div>
      </section>
    );
  }

  if (!dashboard) {
    return null;
  }

  return (
    <section className="panel dashboard-page">
      <div className="dashboard-header">
        <div>
          <p className="eyebrow">Home</p>
          <h1>DaliJob dashboard</h1>
          <p className="lede">Review setup items, best matches, and recently saved jobs.</p>
        </div>
        <button type="button" className="secondary-button" onClick={() => void loadDashboard()}>
          Refresh
        </button>
      </div>

      <section className="dashboard-next-step">
        <div>
          <p className="eyebrow">Recommended Next Step</p>
          <h2>{dashboard.recommended_next_step.label}</h2>
          <p className="summary">{dashboard.recommended_next_step.reason}</p>
        </div>
        <a className="button-link" href={dashboard.recommended_next_step.href}>
          Open
        </a>
      </section>

      <section className="dashboard-grid">
        <section className="profile-card">
          <h2>Setup Alerts</h2>
          {dashboard.setup_alerts.length ? (
            <div className="dashboard-alert-list">
              {dashboard.setup_alerts.map((alert) => (
                <a className="dashboard-alert" href={alert.href} key={alert.kind}>
                  {alert.message}
                </a>
              ))}
            </div>
          ) : (
            <p className="empty">No setup alerts.</p>
          )}
        </section>

        <section className="profile-card">
          <h2>Best Matches</h2>
          {dashboard.best_matches.length ? (
            <div className="dashboard-card-list">
              {dashboard.best_matches.map((job) => (
                <BestMatchCard job={job} key={job.user_saved_job_id} />
              ))}
            </div>
          ) : (
            <p className="empty">No match scores yet.</p>
          )}
        </section>
      </section>

      <section className="profile-card">
        <h2>Recently Saved Jobs</h2>
        {dashboard.recently_saved_jobs.length ? (
          <div className="dashboard-card-list">
            {dashboard.recently_saved_jobs.map((job) => (
              <RecentJobCard job={job} key={job.user_saved_job_id} />
            ))}
          </div>
        ) : (
          <p className="empty">No saved jobs yet.</p>
        )}
      </section>
    </section>
  );
}

function BestMatchCard({ job }: { job: DashboardBestMatch }) {
  return (
    <a className="dashboard-job-card" href={job.href}>
      <span className="score-badge">{job.match_score}/10</span>
      <div>
        <h3>{job.title}</h3>
        <p className="metadata">{job.company}</p>
        <p className="metadata">Compared resume: {job.resume_label}</p>
        {job.match_summary ? <p className="summary">{job.match_summary}</p> : null}
      </div>
    </a>
  );
}

function RecentJobCard({ job }: { job: DashboardRecentJob }) {
  return (
    <a className="dashboard-job-card" href={job.href}>
      <span className="status-pill">{statusLabel(job.status)}</span>
      <div>
        <h3>{job.title}</h3>
        <p className="metadata">
          {job.company} | Saved {formatDate(job.created_at)}
        </p>
        {job.source_url ? <p className="metadata dashboard-url">{job.source_url}</p> : null}
      </div>
    </a>
  );
}

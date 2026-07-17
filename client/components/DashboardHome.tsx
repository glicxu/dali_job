"use client";

import { useEffect, useState } from "react";
import {
  DashboardApplicationAction,
  DashboardBestMatch,
  DashboardRecentJob,
  DashboardResponse,
  getDashboard,
  getAuthToken,
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
  const [homeMode, setHomeMode] = useState<"checking" | "public" | "dashboard">("checking");
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function loadDashboard() {
    if (!getAuthToken()) {
      setHomeMode("public");
      setIsLoading(false);
      return;
    }
    setHomeMode("dashboard");
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

  if (homeMode === "public") {
    return <PublicHome />;
  }

  if (homeMode === "checking" || isLoading) {
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
        <h2>Application Actions</h2>
        {dashboard.application_actions.length ? (
          <div className="dashboard-card-list">
            {dashboard.application_actions.map((action) => (
              <ApplicationActionCard action={action} key={action.task_id} />
            ))}
          </div>
        ) : (
          <p className="empty">No upcoming application actions.</p>
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

function ApplicationActionCard({ action }: { action: DashboardApplicationAction }) {
  const actionTime = action.due_at || action.reminder_at;
  return (
    <a className="dashboard-job-card" href={action.href}>
      <span className={`status-pill${action.is_overdue ? " status-rejected" : ""}`}>
        {action.is_overdue ? "Overdue" : action.reminder_due ? "Reminder" : "Upcoming"}
      </span>
      <div>
        <h3>{action.title}</h3>
        <p className="metadata">
          {action.job_title}{action.company ? ` | ${action.company}` : ""}
        </p>
        {actionTime ? <p className="metadata">{new Date(actionTime).toLocaleString()}</p> : null}
      </div>
    </a>
  );
}

function PublicHome() {
  return (
    <section className="panel public-home">
      <section className="public-hero">
        <div>
          <p className="eyebrow">Career Management</p>
          <h1>DaliJob helps organize your job search around your resume.</h1>
          <p className="lede">
            Save jobs, structure resume profiles, compare opportunities, and review match gaps in one private
            workspace.
          </p>
        </div>
        <div className="button-row public-hero-actions">
          <a className="button-link" href="/auth">
            Login / Register
          </a>
        </div>
      </section>

      <section className="public-preview-grid">
        <PublicPreviewCard
          title="Resume Profiles"
          description="Keep structured resume profiles that can be reused for matching and future document generation."
          items={["Backend resume", "Data-focused resume", "Default profile first"]}
        />
        <PublicPreviewCard
          title="Job Search And Import"
          description="Search or import job postings, then save the roles that are worth reviewing."
          items={["Review before saving", "Source URL preserved", "Manual fallback available"]}
        />
        <PublicPreviewCard
          title="Saved Jobs"
          description="Track saved jobs with notes, deadlines when available, and analyzed job details."
          items={["Private saved list", "Job notes", "Analysis status"]}
        />
        <PublicPreviewCard
          title="Resume Matching"
          description="Compare a selected resume profile against saved jobs and get a clear score."
          items={["0-10 score", "Bulk matching", "Resume-specific results"]}
        />
        <PublicPreviewCard
          title="Match Data"
          description="Review why a job matched, what was missing, and what resume updates may help."
          items={["Matched skills", "Missing keywords", "Supported requirements"]}
        />
      </section>

      <section className="profile-card">
        <h2>Private by default</h2>
        <p className="summary">
          Login is required to use AI matching, job scraping, provider-backed search, uploads, saved jobs,
          documents, and profile data.
        </p>
      </section>
    </section>
  );
}

function PublicPreviewCard({
  title,
  description,
  items,
}: {
  title: string;
  description: string;
  items: string[];
}) {
  return (
    <article className="profile-card public-preview-card">
      <h2>{title}</h2>
      <p className="summary">{description}</p>
      <div className="resume-chip-row">
        {items.map((item) => (
          <span className="resume-chip" key={item}>
            {item}
          </span>
        ))}
      </div>
    </article>
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

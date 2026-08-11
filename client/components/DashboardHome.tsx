"use client";

import { useEffect, useState } from "react";
import {
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  ClipboardCheck,
  GraduationCap,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";
import {
  DashboardApplicationAction,
  DashboardBestMatch,
  DashboardRecentJob,
  DashboardResponse,
  getDashboard,
  getAuthToken,
} from "../lib/api";
import {
  AlertBanner,
  Badge,
  EmptyState,
  PageHeader,
  SectionHeader,
  SkeletonRows,
} from "./ui";

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
      <section className="panel dashboard-page">
        <PageHeader eyebrow="Home" title="DaliJob dashboard" description="Loading your career workspace." icon={Sparkles} />
        <SkeletonRows count={4} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="panel">
        <AlertBanner tone="danger">{error}</AlertBanner>
      </section>
    );
  }

  if (!dashboard) {
    return null;
  }

  return (
    <section className="panel dashboard-page">
      <PageHeader
        eyebrow="Home"
        title="DaliJob dashboard"
        description="Review what needs attention and continue your job search."
        icon={Sparkles}
        actions={
          <div className="button-row">
            <a className="button-link secondary-button action-with-icon" href="/tutorial?replay=1">
              <GraduationCap size={17} aria-hidden="true" /> Tutorial
            </a>
          </div>
        }
      />

      <section className="dashboard-next-step">
        <div className="dashboard-next-step-copy">
          <p className="dashboard-next-step-label">Recommended Next Step</p>
          <h2>{dashboard.recommended_next_step.label}</h2>
          <p className="summary">{dashboard.recommended_next_step.reason}</p>
        </div>
        <a className="button-link dashboard-next-step-action" href={dashboard.recommended_next_step.href}>
          Open next step <ArrowRight size={17} aria-hidden="true" />
        </a>
      </section>

      <section className={`dashboard-section dashboard-setup-section${dashboard.setup_alerts.length ? " has-alerts" : ""}`}>
        <div className="dashboard-setup-heading">
          <SectionHeader title="Setup Alerts" description="Complete these items to get the most useful recommendations." />
          {dashboard.setup_alerts.length ? (
            <span className="dashboard-alert-count" aria-label={`${dashboard.setup_alerts.length} setup tasks remaining`}>
              {dashboard.setup_alerts.length}
            </span>
          ) : null}
        </div>
        {dashboard.setup_alerts.length ? (
          <div className="dashboard-alert-list">
            {dashboard.setup_alerts.map((alert) => (
              <a className="dashboard-alert" href={alert.href} key={alert.kind}>
                <span className="dashboard-alert-icon" aria-hidden="true" />
                <span className="dashboard-alert-content">{alert.message}</span>
                <span className="dashboard-alert-action">Resolve</span>
              </a>
            ))}
          </div>
        ) : (
          <EmptyState compact icon={CheckCircle2} title="Setup complete" description="No setup alerts require your attention." />
        )}
      </section>

      <section className="dashboard-section">
        <SectionHeader title="Application Actions" description="Upcoming follow-ups, reminders, and deadlines." />
        {dashboard.application_actions.length ? (
          <div className="dashboard-card-list">
            {dashboard.application_actions.map((action) => (
              <ApplicationActionCard action={action} key={action.task_id} />
            ))}
          </div>
        ) : (
          <EmptyState compact icon={ClipboardCheck} title="Nothing due" description="No upcoming application actions need attention." />
        )}
      </section>

      <section className="dashboard-section">
        <SectionHeader title="Best Matches" description="Your strongest saved-job matches based on the selected resume profile." />
        {dashboard.best_matches.length ? (
          <div className="dashboard-compact-list">
            {dashboard.best_matches.map((job) => (
              <BestMatchCard job={job} key={job.user_saved_job_id} />
            ))}
          </div>
        ) : (
          <EmptyState compact icon={Target} title="No match scores yet" description="Match a resume profile with saved jobs to compare opportunities." />
        )}
      </section>

      <section className="dashboard-section">
        <SectionHeader title="Recently Saved Jobs" description="The latest opportunities added to your workspace." />
        {dashboard.recently_saved_jobs.length ? (
          <div className="dashboard-compact-list">
            {dashboard.recently_saved_jobs.map((job) => (
              <RecentJobCard job={job} key={job.user_saved_job_id} />
            ))}
          </div>
        ) : (
          <EmptyState compact icon={BriefcaseBusiness} title="No saved jobs" description="Search for a role or import a job URL to start building your list." />
        )}
      </section>
    </section>
  );
}

function ApplicationActionCard({ action }: { action: DashboardApplicationAction }) {
  const actionTime = action.due_at || action.reminder_at;
  return (
    <a className="dashboard-job-card" href={action.href}>
      <Badge tone={action.is_overdue ? "danger" : action.reminder_due ? "warning" : "info"}>
        {action.is_overdue ? "Overdue" : action.reminder_due ? "Reminder" : "Upcoming"}
      </Badge>
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
          <h1>DaliJob</h1>
          <p className="lede">
            Organize your job search around your resume. Save opportunities, track applications, compare matches,
            and prepare your next move in one private workspace.
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
          title="Resumes"
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
        <SectionHeader title="Private by default" description="Your career data remains inside your account." />
        <div className="public-privacy-row">
          <ShieldCheck size={22} aria-hidden="true" />
          <p className="summary">Login is required to use AI matching, job scraping, provider-backed search, uploads, saved jobs, documents, and profile data.</p>
        </div>
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
    <a className="dashboard-compact-job" href={job.href}>
      <h3>{job.title}</h3>
      <ArrowRight size={16} aria-hidden="true" />
    </a>
  );
}

function RecentJobCard({ job }: { job: DashboardRecentJob }) {
  return (
    <a className="dashboard-compact-job" href={job.href}>
      <h3>{job.title}</h3>
      <ArrowRight size={16} aria-hidden="true" />
    </a>
  );
}

"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  AnalyticsPerformanceGroup,
  AnalyticsSummary,
  getAnalyticsSummary,
  getAuthToken,
} from "../lib/api";

function labelize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function percentage(value: number | null): string {
  return value === null ? "N/A" : `${value.toFixed(1)}%`;
}

function hours(value: number | null): string {
  if (value === null) return "N/A";
  if (value >= 48) return `${(value / 24).toFixed(1)} days`;
  return `${value.toFixed(1)} hours`;
}

function localDate(daysAgo: number): string {
  const date = new Date();
  date.setDate(date.getDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}

export function AnalyticsDashboard() {
  if (!getAuthToken()) return <AnalyticsPreview />;
  return <AuthenticatedAnalyticsDashboard />;
}

function AuthenticatedAnalyticsDashboard() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadAnalytics(nextStart = startDate, nextEnd = endDate) {
    setLoading(true);
    setError(null);
    try {
      setSummary(await getAnalyticsSummary({ startDate: nextStart || undefined, endDate: nextEnd || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load analytics.");
    } finally {
      setLoading(false);
    }
  }

  // Initial load intentionally uses the default range; later loads are explicit form actions.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void loadAnalytics("", ""); }, []);

  function applyRange(event: FormEvent) {
    event.preventDefault();
    void loadAnalytics();
  }

  function applyPreset(days: number | null) {
    const nextStart = days === null ? "" : localDate(days);
    const nextEnd = days === null ? "" : new Date().toISOString().slice(0, 10);
    setStartDate(nextStart);
    setEndDate(nextEnd);
    void loadAnalytics(nextStart, nextEnd);
  }

  const maxTrendCount = useMemo(
    () => Math.max(1, ...(summary?.application_trend.map((item) => item.count) || [1])),
    [summary],
  );

  if (loading && !summary) return <div className="analytics-dashboard"><p className="empty">Loading analytics.</p></div>;

  return (
    <div className="analytics-dashboard">
      {error ? <p className="error">{error}</p> : null}
      <form className="analytics-filter" onSubmit={applyRange}>
        <div>
          <h2>Date Range</h2>
          <p className="metadata">Dates use your account timezone.</p>
        </div>
        <label>Start<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>End<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <button disabled={loading}>Apply</button>
        <div className="button-row analytics-presets">
          <button type="button" className="secondary" onClick={() => applyPreset(30)}>30 Days</button>
          <button type="button" className="secondary" onClick={() => applyPreset(90)}>90 Days</button>
          <button type="button" className="secondary" onClick={() => applyPreset(null)}>All Time</button>
        </div>
      </form>

      {summary ? (
        <>
          {summary.data_quality.warnings.length ? <section className="analytics-warning-band"><h2>Data Notes</h2><ul>{summary.data_quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></section> : null}

          <section className="analytics-kpis" aria-label="Outcome rates">
            <div><span>Applications</span><strong>{summary.application_count}</strong></div>
            <div><span>Submitted</span><strong>{summary.submitted_application_count}</strong></div>
            {summary.rates.map((rate) => <div key={rate.outcome}><span>{labelize(rate.outcome)} Rate</span><strong>{percentage(rate.percentage)}</strong><small>{rate.numerator} of {rate.denominator}</small></div>)}
          </section>

          <div className="analytics-overview-grid">
            <section className="analytics-section">
              <h2>Current Status</h2>
              <div className="analytics-status-list">{summary.status_counts.map((item) => <div key={item.status}><span>{labelize(item.status)}</span><strong>{item.count}</strong></div>)}</div>
            </section>
            <section className="analytics-section">
              <h2>Application Trend</h2>
              {summary.application_trend.length ? <div className="analytics-trend">{summary.application_trend.map((item) => <div key={item.period}><span>{item.period}</span><div><i style={{ width: `${Math.max(4, item.count * 100 / maxTrendCount)}%` }} /></div><strong>{item.count}</strong></div>)}</div> : <p className="empty">No applications in this range.</p>}
            </section>
            <section className="analytics-section">
              <h2>Response Timing</h2>
              <div className="analytics-timing">{summary.durations.map((item) => <div key={item.metric}><strong>{labelize(item.metric)}</strong><span>Average: {hours(item.average_hours)}</span><span>Median: {hours(item.median_hours)}</span><span>Sample: {item.sample_size}</span></div>)}</div>
            </section>
          </div>

          <PerformanceTable title="Source Performance" groups={summary.source_performance} empty="No submitted applications have source groups in this range." />
          <PerformanceTable title="Resume-Version Performance" groups={summary.resume_version_performance} empty="Attach exact resume versions to submitted applications to see this comparison." />

          <section className="analytics-section">
            <div className="section-heading"><div><h2>Metric Definitions</h2><p className="metadata">Formula version {summary.metric_version} | {summary.timezone}</p></div></div>
            <div className="analytics-definitions">{summary.definitions.map((item) => <article key={item.metric}><strong>{item.metric}</strong><p>{item.definition}</p><p className="metadata">Denominator: {item.denominator}</p></article>)}</div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function PerformanceTable({ title, groups, empty }: { title: string; groups: AnalyticsPerformanceGroup[]; empty: string }) {
  return (
    <section className="analytics-section">
      <h2>{title}</h2>
      {groups.length ? <div className="analytics-table-wrap"><table className="analytics-table"><thead><tr><th>Group</th><th>Sample</th><th>Response</th><th>Interview</th><th>Offer</th><th>Rejected</th><th>Withdrawn</th></tr></thead><tbody>{groups.map((group) => <tr key={group.key}><td><strong>{group.label}</strong>{group.small_sample ? <span className="small-sample">Small sample</span> : null}</td><td>{group.sample_size}</td><td>{percentage(group.response_rate)}</td><td>{percentage(group.interview_rate)}</td><td>{percentage(group.offer_rate)}</td><td>{percentage(group.rejection_rate)}</td><td>{percentage(group.withdrawal_rate)}</td></tr>)}</tbody></table></div> : <p className="empty">{empty}</p>}
    </section>
  );
}

function AnalyticsPreview() {
  return <div className="analytics-dashboard"><section className="analytics-section"><h2>Outcome analytics</h2><p>Log in to review private application status, response timing, job-source outcomes, and exact resume-version comparisons.</p><a className="button-link" href="/auth">Login or Register</a></section></div>;
}

import { AnalyticsDashboard } from "../../components/AnalyticsDashboard";

export default function AnalyticsPage() {
  return (
    <section className="panel analytics-page">
      <div>
        <p className="eyebrow">Outcome Analytics</p>
        <h1>Application Outcomes</h1>
        <p className="lede">Review descriptive application outcomes, response timing, sources, and exact resume versions.</p>
      </div>
      <AnalyticsDashboard />
    </section>
  );
}

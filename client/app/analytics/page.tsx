import { AnalyticsDashboard } from "../../components/AnalyticsDashboard";
import { PageHeader } from "../../components/ui";
import { ChartNoAxesCombined } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <section className="panel analytics-page">
      <PageHeader
        eyebrow="Outcome Analytics"
        title="Application outcomes"
        description="Review application outcomes, response timing, sources, and exact resume versions."
        icon={ChartNoAxesCombined}
      />
      <AnalyticsDashboard />
    </section>
  );
}

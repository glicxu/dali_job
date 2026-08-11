import { JobsManager } from "../../components/JobsManager";
import { BriefcaseBusiness } from "lucide-react";
import { PageHeader } from "../../components/ui";

export default function JobsPage() {
  return (
    <section className="panel jobs-panel">
      <PageHeader
        eyebrow="Saved Jobs"
        title="Jobs"
        description="Review saved opportunities, notes, analysis, and resume match history."
        icon={BriefcaseBusiness}
      />
      <JobsManager />
    </section>
  );
}

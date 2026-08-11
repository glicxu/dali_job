import { JobUrlDebugTool } from "../../components/JobUrlDebugTool";
import { PageHeader } from "../../components/ui";
import { Bug } from "lucide-react";

export default function JobUrlDebugPage() {
  return (
    <section className="panel">
      <PageHeader eyebrow="Diagnostic Tool" title="Job URL scraper preview" description="Inspect the exact text DaliJob extracts from a job posting before analysis or matching." icon={Bug} />
      <JobUrlDebugTool />
    </section>
  );
}

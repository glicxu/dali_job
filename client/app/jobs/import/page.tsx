import { JobListImportManager } from "../../../components/JobListImportManager";
import { ArrowLeft, ListPlus } from "lucide-react";
import { PageHeader } from "../../../components/ui";

export default function JobListImportPage() {
  return (
    <section className="panel jobs-panel job-creation-page">
      <a className="back-link" href="/jobs">
        <ArrowLeft size={18} aria-hidden="true" /> Back to Saved Jobs
      </a>
      <PageHeader
        eyebrow="Job Creation"
        title="Import Jobs From List URL"
        description="Discover individual postings from a search results page, choose the jobs to save, and optionally match them against a resume profile."
        icon={ListPlus}
      />
      <JobListImportManager />
    </section>
  );
}

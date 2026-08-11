import { JobsManager } from "../../../components/JobsManager";
import { ArrowLeft, Link2 } from "lucide-react";
import { PageHeader } from "../../../components/ui";

export default function ImportJobUrlPage() {
  return (
    <section className="panel jobs-panel job-creation-page">
      <a className="back-link" href="/jobs">
        <ArrowLeft size={18} aria-hidden="true" /> Back to Saved Jobs
      </a>
      <PageHeader
        eyebrow="Job Creation"
        title="Import Job URL"
        description="Extract a job posting into a structured profile, review it, and save it to your jobs."
        icon={Link2}
      />
      <JobsManager creationMode="url" />
    </section>
  );
}

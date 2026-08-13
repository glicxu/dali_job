import { JobsManager } from "../../../components/JobsManager";
import { ArrowLeft, FilePenLine } from "lucide-react";
import { PageHeader } from "../../../components/ui";

export default function ManualJobPage() {
  return (
    <section className="panel jobs-panel job-creation-page">
      <a className="back-link" href="/jobs">
        <ArrowLeft size={18} aria-hidden="true" /> Back to Saved Jobs
      </a>
      <PageHeader
        eyebrow="Job Creation"
        title="Create Manual Job"
        description="Enter a title and paste the job description. DaliJob will generate the structured job profile and save it privately to your account."
        icon={FilePenLine}
      />
      <JobsManager creationMode="manual" />
    </section>
  );
}

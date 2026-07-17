import { JobsManager } from "../../../components/JobsManager";

export default function ManualJobPage() {
  return (
    <section className="panel jobs-panel job-creation-page">
      <a className="back-link" href="/jobs">
        <span aria-hidden="true">&larr;</span> Back to Saved Jobs
      </a>
      <div>
        <p className="eyebrow">Job Creation</p>
        <h1>Create Manual Job</h1>
        <p className="lede">Enter a job description and structured details without importing from another website.</p>
      </div>
      <JobsManager creationMode="manual" />
    </section>
  );
}

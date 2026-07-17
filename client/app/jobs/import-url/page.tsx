import { JobsManager } from "../../../components/JobsManager";

export default function ImportJobUrlPage() {
  return (
    <section className="panel jobs-panel job-creation-page">
      <a className="back-link" href="/jobs">
        <span aria-hidden="true">&larr;</span> Back to Saved Jobs
      </a>
      <div>
        <p className="eyebrow">Job Creation</p>
        <h1>Import Job URL</h1>
        <p className="lede">Extract a job posting into a structured profile, review it, and save it to your jobs.</p>
      </div>
      <JobsManager creationMode="url" />
    </section>
  );
}

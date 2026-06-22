import { JobsManager } from "../../components/JobsManager";

export default function JobsPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Job Import</p>
        <h1>Jobs</h1>
        <p className="lede">
          Import, review, edit, and save job descriptions before they become applications.
        </p>
      </div>
      <JobsManager />
    </section>
  );
}

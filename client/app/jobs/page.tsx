import { JobsManager } from "../../components/JobsManager";

export default function JobsPage() {
  return (
    <section className="panel jobs-panel">
      <div>
        <p className="eyebrow">Saved Jobs</p>
        <h1>Jobs</h1>
        <p className="lede">
          Review saved opportunities, notes, analysis, and resume match history.
        </p>
      </div>
      <JobsManager />
    </section>
  );
}

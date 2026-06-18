import { JobUrlDebugTool } from "../../components/JobUrlDebugTool";

export default function JobUrlDebugPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Temporary Debug</p>
        <h1>Job URL scraper preview</h1>
        <p className="lede">
          Paste a job description URL to see the exact text DaliJob extracts before matching.
        </p>
      </div>
      <JobUrlDebugTool />
    </section>
  );
}

import { getApiBaseUrl } from "../../lib/config";

export default function HealthPage() {
  return (
    <section className="panel">
      <p className="eyebrow">Server Boundary</p>
      <h1>API connection</h1>
      <dl className="facts">
        <div>
          <dt>API base URL</dt>
          <dd>{getApiBaseUrl()}</dd>
        </div>
      </dl>
    </section>
  );
}

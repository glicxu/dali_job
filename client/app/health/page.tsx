import { getApiBaseUrl } from "../../lib/config";
import { PageHeader } from "../../components/ui";
import { HeartPulse } from "lucide-react";

export default function HealthPage() {
  return (
    <section className="panel">
      <PageHeader eyebrow="Server Boundary" title="API connection" description="Review the configured server endpoint used by this client." icon={HeartPulse} />
      <dl className="facts">
        <div>
          <dt>API base URL</dt>
          <dd>{getApiBaseUrl()}</dd>
        </div>
      </dl>
    </section>
  );
}

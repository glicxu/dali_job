import { OperationsManager } from "../../components/OperationsManager";
import { PageHeader } from "../../components/ui";
import { Activity } from "lucide-react";

export default function OperationsPage() {
  return (
    <section className="panel operations-page">
      <PageHeader eyebrow="Managed Work" title="Operations" description="Review progress and safely retry searches, imports, parsing, and matching." icon={Activity} />
      <OperationsManager />
    </section>
  );
}

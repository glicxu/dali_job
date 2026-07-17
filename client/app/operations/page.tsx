import { OperationsManager } from "../../components/OperationsManager";

export default function OperationsPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Managed Work</p>
        <h1>Operations</h1>
        <p className="lede">Review progress and safely retry searches, imports, parsing, and matching.</p>
      </div>
      <OperationsManager />
    </section>
  );
}

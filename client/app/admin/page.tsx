import { AdminReports } from "../../components/AdminReports";
import { PageHeader } from "../../components/ui";
import { ShieldCheck } from "lucide-react";

export default function AdminPage() {
  return (
    <main className="panel admin-page">
      <PageHeader eyebrow="Administration" title="Admin workspace" description="Review user reports and access restricted operational diagnostics." icon={ShieldCheck} />
      <AdminReports />
    </main>
  );
}

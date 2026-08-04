import { AdminReports } from "../../components/AdminReports";

export default function AdminPage() {
  return (
    <main className="panel admin-page">
      <div>
        <p className="eyebrow">Administration</p>
        <h1>Admin</h1>
        <p className="lede">Review user reports and access operational diagnostics.</p>
      </div>
      <AdminReports />
    </main>
  );
}

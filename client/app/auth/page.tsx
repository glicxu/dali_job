import { AuthForm } from "../../components/AuthForm";
import { UserReports } from "../../components/UserReports";
import { SearchCriteriaManager } from "../../components/SearchCriteriaManager";
import { PageHeader } from "../../components/ui";
import { UserRound } from "lucide-react";

export default function AuthPage() {
  return (
    <section className="panel account-page">
      <PageHeader eyebrow="Account" title="Account and security" description="Review your session, security options, and submitted support requests." icon={UserRound} />
      <AuthForm />
      <SearchCriteriaManager />
      <UserReports />
    </section>
  );
}

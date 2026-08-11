import { AuthForm } from "../../components/AuthForm";
import { UserReports } from "../../components/UserReports";
import { PageHeader, SectionHeader } from "../../components/ui";
import { Activity, UserRound } from "lucide-react";

export default function AuthPage() {
  return (
    <section className="panel account-page">
      <PageHeader eyebrow="Account" title="Account and security" description="Review your session, security options, and submitted support requests." icon={UserRound} />
      <AuthForm />
      <section className="account-tools" aria-label="Account tools">
        <SectionHeader title="Account tools" description="Review background activity associated with your account." />
        <div className="account-tools-list">
          <article>
            <div className="account-tool-description">
              <Activity size={20} aria-hidden="true" />
              <div>
                <h3>Operations</h3>
                <p>Review background searches, imports, matching, and AI generation activity.</p>
              </div>
            </div>
            <a className="button-link secondary-button" href="/operations">Open Operations</a>
          </article>
        </div>
      </section>
      <UserReports />
    </section>
  );
}

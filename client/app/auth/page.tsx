import { AuthForm } from "../../components/AuthForm";
import { UserReports } from "../../components/UserReports";

export default function AuthPage() {
  return (
    <section className="panel account-page">
      <div>
        <p className="eyebrow">Account</p>
        <h1>Account</h1>
        <p className="lede">Review your session, account options, and submitted support requests.</p>
      </div>
      <AuthForm />
      <section className="account-tools" aria-labelledby="account-tools-heading">
        <div>
          <p className="eyebrow">Activity</p>
          <h2 id="account-tools-heading">Account tools</h2>
        </div>
        <div className="account-tools-list">
          <article>
            <div>
              <h3>Operations</h3>
              <p>Review background searches, imports, matching, and AI generation activity.</p>
            </div>
            <a className="button-link secondary-button" href="/operations">Open Operations</a>
          </article>
        </div>
      </section>
      <UserReports />
    </section>
  );
}

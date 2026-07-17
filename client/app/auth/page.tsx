import { AuthForm } from "../../components/AuthForm";

export default function AuthPage() {
  return (
    <section className="panel account-page">
      <div>
        <p className="eyebrow">Account</p>
        <h1>Account</h1>
        <p className="lede">Review your session and access diagnostic tools when they are needed.</p>
      </div>
      <AuthForm />
      <section className="account-tools" aria-labelledby="account-tools-heading">
        <div>
          <p className="eyebrow">Support</p>
          <h2 id="account-tools-heading">System tools</h2>
        </div>
        <div className="account-tools-list">
          <article>
            <div>
              <h3>Operations</h3>
              <p>Review background searches, imports, matching, and AI generation activity.</p>
            </div>
            <a className="button-link secondary-button" href="/operations">Open Operations</a>
          </article>
          <article>
            <div>
              <h3>System Health</h3>
              <p>Check server availability, configuration, and database migration readiness.</p>
            </div>
            <a className="button-link secondary-button" href="/health">Open Health</a>
          </article>
          <article>
            <div>
              <h3>URL Debug</h3>
              <p>Inspect the raw extraction result returned for an individual job URL.</p>
            </div>
            <a className="button-link secondary-button" href="/job-url-debug">Open URL Debug</a>
          </article>
        </div>
      </section>
    </section>
  );
}

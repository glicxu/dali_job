import { AuthForm } from "../../components/AuthForm";

export default function AuthPage() {
  return (
    <section className="panel">
      <div>
        <p className="eyebrow">Account</p>
        <h1>DaliJob login</h1>
        <p className="lede">Create a DaliJob account or sign in with your existing DaliJob account.</p>
      </div>
      <AuthForm />
    </section>
  );
}

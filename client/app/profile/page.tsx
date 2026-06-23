import { ProfileEditor } from "../../components/ProfileEditor";

export default function ProfilePage() {
  return (
    <section className="panel profile-page">
      <div>
        <p className="eyebrow">Phase 1 Foundation</p>
        <h1>Career profile</h1>
        <p className="lede">
          Maintain multiple structured resume profiles that will later power matching,
          resume tailoring, cover letters, and interview preparation.
        </p>
      </div>
      <ProfileEditor />
    </section>
  );
}

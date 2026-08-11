import { ProfileEditor } from "../../components/ProfileEditor";
import { PageHeader } from "../../components/ui";
import { FileUser } from "lucide-react";

export default function ProfilePage() {
  return (
    <section className="panel profile-page">
      <PageHeader
        title="Resumes"
        description="Maintain structured resume profiles for matching, tailoring, cover letters, and interview preparation."
        icon={FileUser}
      />
      <ProfileEditor />
    </section>
  );
}

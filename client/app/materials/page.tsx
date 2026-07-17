import { ApplicationMaterialsManager } from "../../components/ApplicationMaterialsManager";

export default function MaterialsPage() {
  return (
    <section className="panel materials-page">
      <div>
        <p className="eyebrow">Application Materials</p>
        <h1>Tailored resumes and cover letters</h1>
        <p className="lede">Generate, review, and revise materials from an exact saved job and resume version.</p>
      </div>
      <ApplicationMaterialsManager />
    </section>
  );
}

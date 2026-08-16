import { FlaskConical } from "lucide-react";
import { MatchingEvaluationWorkbench } from "../../components/MatchingEvaluationWorkbench";
import { PageHeader } from "../../components/ui";

export default function MatchingEvaluationPage() {
  return <main className="panel evaluation-page"><PageHeader eyebrow="Internal evaluation" title="Matching evaluation workbench" description="Build a frozen job corpus and inspect every artifact produced by the three-stage matching pipeline." icon={FlaskConical} /><MatchingEvaluationWorkbench /></main>;
}

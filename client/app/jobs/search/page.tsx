import { IndeedJobSearchManager } from "../../../components/IndeedJobSearchManager";
import { Search } from "lucide-react";
import { PageHeader } from "../../../components/ui";

export default function IndeedJobSearchPage() {
  return (
    <section className="panel jobs-panel">
      <PageHeader
        eyebrow="Discover"
        title="Job Search"
        description="Search for jobs, review the results, and import selected postings into DaliJob."
        icon={Search}
      />
      <IndeedJobSearchManager />
    </section>
  );
}

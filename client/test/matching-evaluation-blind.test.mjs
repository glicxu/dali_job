import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const workbench = readFileSync(
  new URL("../components/MatchingEvaluationWorkbench.tsx", import.meta.url),
  "utf8",
);

test("blind QA links open one run without diagnostic expectations or prior reviews", () => {
  assert.match(workbench, /get\("review"\) === "blind"/);
  assert.match(workbench, /get\("run_id"\)/);
  assert.match(workbench, /annotations: \[\]/);
  assert.match(workbench, /review_kind: "independent" as const/);
  assert.match(workbench, /expected_value: null/);
  assert.match(workbench, /Human match review/);
  assert.match(workbench, /Submit human match score/);
  assert.match(workbench, /review_kind: "independent" as const/);

  const blindBranch = workbench.slice(
    workbench.indexOf("if (blindReview)"),
    workbench.indexOf('return <div className="evaluation-workbench">', workbench.indexOf("if (blindReview)") + 1),
  );
  assert.doesNotMatch(blindBranch, /FixtureLibrary|AggregateMetrics|AdjudicationQueue|RunComparison/);
});

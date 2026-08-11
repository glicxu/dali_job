import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const shell = readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const dashboard = readFileSync(new URL("../components/DashboardHome.tsx", import.meta.url), "utf8");
const jobs = readFileSync(new URL("../components/JobsManager.tsx", import.meta.url), "utf8");
const applications = readFileSync(new URL("../components/ApplicationTracker.tsx", import.meta.url), "utf8");
const interviews = readFileSync(new URL("../components/InterviewManager.tsx", import.meta.url), "utf8");
const profiles = readFileSync(new URL("../components/ProfileEditor.tsx", import.meta.url), "utf8");
const matching = readFileSync(new URL("../components/ResumeJobMatchForm.tsx", import.meta.url), "utf8");
const documents = readFileSync(new URL("../components/DocumentLibrary.tsx", import.meta.url), "utf8");
const materials = readFileSync(new URL("../components/ApplicationMaterialsManager.tsx", import.meta.url), "utf8");
const analytics = readFileSync(new URL("../components/AnalyticsDashboard.tsx", import.meta.url), "utf8");
const askScout = readFileSync(new URL("../components/AskScoutPage.tsx", import.meta.url), "utf8");
const auth = readFileSync(new URL("../components/AuthForm.tsx", import.meta.url), "utf8");
const admin = readFileSync(new URL("../components/AdminReports.tsx", import.meta.url), "utf8");
const operations = readFileSync(new URL("../components/OperationsManager.tsx", import.meta.url), "utf8");
const urlDebug = readFileSync(new URL("../components/JobUrlDebugTool.tsx", import.meta.url), "utf8");
const tutorial = readFileSync(new URL("../components/TutorialGuide.tsx", import.meta.url), "utf8");
const tokens = readFileSync(new URL("../app/styles/tokens.css", import.meta.url), "utf8");
const overhaul = readFileSync(new URL("../app/styles/overhaul.css", import.meta.url), "utf8");

function tokenHex(name) {
  const match = tokens.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`, "i"));
  assert.ok(match, `Missing color token --${name}`);
  return match[1];
}

function relativeLuminance(hex) {
  const channels = hex.slice(1).match(/.{2}/g).map((value) => Number.parseInt(value, 16) / 255);
  const linear = channels.map((value) => value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(foreground, background) {
  const values = [relativeLuminance(foreground), relativeLuminance(background)].sort((a, b) => b - a);
  return (values[0] + 0.05) / (values[1] + 0.05);
}

test("blue-led design tokens include semantic states and cool off-white surfaces", () => {
  assert.match(tokens, /--brand-700:\s*#1f5faf/);
  assert.match(tokens, /--surface-page:\s*#f6f8fb/);
  assert.match(tokens, /--success-700/);
  assert.match(tokens, /--warning-700/);
  assert.match(tokens, /--danger-700/);
});

test("applications and interviews use semantic list-detail states", () => {
  assert.match(applications, /applicationStatusTone/);
  assert.match(applications, /Application filters/);
  assert.match(applications, /CollapsibleApplicationSection/);
  assert.match(interviews, /interviewStatusTone/);
  assert.match(interviews, /Interview details/);
});

test("resume profiles separate readable and edit modes while matching preserves guards", () => {
  assert.match(profiles, /ReadableResumeProfile/);
  assert.match(profiles, /setIsEditing\(true\)/);
  assert.match(profiles, /label=\{`Delete \$\{profile\.title\}`\}/);
  assert.match(profiles, /getResumeProfileDependencies\(profile\.id\)/);
  assert.match(profiles, /current\.filter\(\(item\) => item\.id !== profile\.id\)/);
  assert.match(profiles, /className="profile-card manual-resume-card"[\s\S]*className="profile-workspace"/);
  assert.match(profiles, /title="Your Resumes"/);
  const readableProfile = profiles.slice(
    profiles.indexOf("function ReadableResumeProfile"),
    profiles.indexOf("function ProfileEditorPreview"),
  );
  assert.doesNotMatch(readableProfile, /variant="danger"/);
  assert.match(readableProfile, /onClick=\{onClose\}>Close<\/Button>/);
  assert.match(profiles, /icon=\{X\} onClick=\{resetEditor\}>Close<\/Button>/);
  assert.match(matching, /Choose a saved resume profile or paste resume text before matching/);
  assert.match(matching, /Low compatibility/);
  assert.match(matching, /MatchScoreBadge/);
});

test("documents, materials, and analytics expose versions and exact values", () => {
  assert.match(documents, /structured-document-list/);
  assert.match(documents, /document\.versions\.length/);
  assert.match(materials, /material-provenance/);
  assert.match(materials, /source_document_version_number/);
  assert.match(analytics, /aria-label=\{`\$\{item\.count\} applications/);
  assert.match(analytics, /group\.sample_size/);
});

test("navigation exposes active routes and an accessible mobile drawer", () => {
  assert.match(shell, /aria-current=/);
  assert.match(shell, /aria-expanded=\{open\}/);
  assert.match(shell, /Close navigation/);
  assert.match(shell, /event\.key === "Escape"/);
  assert.match(shell, /ChevronDown/);
  assert.match(shell, /user\.tutorial_completed \|\| pathname === "\/tutorial"/);
  assert.match(shell, /<TutorialCoachmark \/>/);
  assert.doesNotMatch(shell, /笆ｼ/);
  assert.match(overhaul, /\.sidebar\.mobile-open/);
  assert.match(overhaul, /\.resume-profile-delete[\s\S]*grid-column: 1/);
  assert.match(overhaul, /\.resume-profile-open[\s\S]*grid-column: 2/);
});

test("first-run tutorial supports cross-page steps, per-step skipping, and replay", () => {
  assert.match(tutorial, /window\.sessionStorage\.setItem\(tutorialSessionKey, "0"\)/);
  assert.match(tutorial, /Skip Step/);
  assert.match(tutorial, /Skip Tutorial/);
  assert.match(tutorial, /completeTutorial\(\)/);
  assert.match(tutorial, /href: "\/profile"/);
  assert.match(tutorial, /href: "\/jobs"/);
  assert.match(tutorial, /href: "\/jobs\/search"/);
  assert.match(tutorial, /href: "\/match"/);
  assert.match(tutorial, /href: "\/applications"/);
  assert.match(dashboard, /href="\/tutorial\?replay=1"/);
});

test("dashboard and jobs use the shared feedback and hierarchy components", () => {
  assert.match(dashboard, /PageHeader/);
  assert.match(dashboard, /SkeletonRows/);
  assert.match(dashboard, /ToastRegion/);
  assert.match(dashboard, /className="dashboard-compact-list"/);
  assert.match(dashboard, /className="dashboard-compact-job"/);
  assert.match(jobs, /Toolbar/);
  assert.match(jobs, /EmptyState/);
  assert.match(jobs, /MatchScoreBadge/);
  assert.match(jobs, /aria-label=\{selectionMode \? `Select \$\{job\.title/);
  assert.match(jobs, /className="job-detail-tabs"/);
  assert.match(jobs, /"Match Analysis" : "Match Resume"/);
  assert.match(jobs, />\s*Analyze All\s*<\/Button>/);
  assert.match(jobs, /for \(const job of unanalyzedJobs\)/);
  assert.match(jobs, /!selectionMode && !job\.job_data \? \(/);
  assert.doesNotMatch(jobs, />\s*View\s*</);
  assert.doesNotMatch(jobs, />\s*Match Data\s*</);
  assert.doesNotMatch(jobs, />\s*Profile\s*</);
  assert.doesNotMatch(jobs, />\s*Description\s*</);
  assert.match(jobs, /className="job-editor-section job-notes-section"/);
  assert.match(jobs, /className="job-editor-section job-profile-section"/);
  assert.match(jobs, /className="job-description-details"/);
  assert.match(jobs, /className="job-description-toggle"/);
  assert.match(jobs, /ReadableJobProfile/);
  assert.match(jobs, /job-notes-readonly/);
  assert.match(jobs, /title="Job profile not analyzed"[\s\S]*action=\{editor\.id && onAnalyze/);
  assert.match(jobs, /loading=\{isAnalyzing\}/);
  assert.match(jobs, /const hasMatch = Boolean\(job\.match_data\)/);
  assert.match(jobs, />\s*Re-match\s*<\/Button>/);
  assert.match(jobs, />Select Jobs<\/Button>/);
  assert.match(jobs, /updateSelectedArchiveState/);
  assert.match(jobs, /toggleSelectAllJobs/);
  assert.doesNotMatch(jobs, />Bulk Match<\/Button>/);
  assert.doesNotMatch(jobs, />Bulk Remove<\/Button>/);
  assert.ok(
    jobs.indexOf('className="job-description-details"') <
      jobs.indexOf('className="job-editor-section job-notes-section"'),
  );
});

test("Ask Scout, authentication, administration, and diagnostics use shared semantic controls", () => {
  assert.match(askScout, /Scout provides navigation guidance only/);
  assert.match(askScout, /Badge tone=\{statusTone/);
  assert.match(auth, /Account security/);
  assert.match(auth, /variant="danger"/);
  assert.match(auth, /aria-pressed=\{mode === "login"\}/);
  assert.match(admin, /admin-diagnostic-link/);
  assert.match(admin, /Badge tone=\{reportStatusTone/);
  assert.match(operations, /Badge tone=\{operationTone/);
  assert.match(urlDebug, /Login is required to scrape and debug job URLs/);
});

test("core text and primary action pairs meet WCAG AA contrast", () => {
  assert.ok(contrastRatio(tokenHex("text-default"), tokenHex("surface-page")) >= 4.5);
  assert.ok(contrastRatio(tokenHex("text-muted"), tokenHex("surface-raised")) >= 4.5);
  assert.ok(contrastRatio(tokenHex("text-on-brand"), tokenHex("brand-700")) >= 4.5);
});

test("focus, reduced-motion, and long-content safeguards remain present", () => {
  assert.match(shell, /className="skip-link"/);
  assert.match(shell, /const focusable =/);
  assert.match(shell, /event\.key !== "Tab"/);
  assert.match(overhaul, /:focus-visible/);
  assert.match(overhaul, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(overhaul, /overflow-wrap: anywhere/);
  assert.match(overhaul, /white-space: pre-wrap/);
});

test("non-command interactive items share the light resume hover treatment", () => {
  assert.match(overhaul, /\.resume-profile-card:not\(\.selected\):hover\s*\{[^}]*var\(--brand-100\)/s);
  assert.match(overhaul, /button\.application-row:not\(\.selected\):hover:not\(:disabled\)\s*\{[^}]*var\(--brand-100\)/s);
  assert.match(overhaul, /button\.material-list-row:not\(\.selected\):hover:not\(:disabled\)\s*\{[^}]*var\(--brand-100\)/s);
  assert.match(overhaul, /button\.job-notes-preview:hover:not\(:disabled\)\s*,[^}]*var\(--brand-100\)/s);
});

test("signed-out protected pages render previews before authenticated implementations", () => {
  const protectedSources = [
    jobs,
    readFileSync(new URL("../components/JobListImportManager.tsx", import.meta.url), "utf8"),
    readFileSync(new URL("../components/IndeedJobSearchManager.tsx", import.meta.url), "utf8"),
    profiles,
    matching,
    documents,
    applications,
    interviews,
    analytics,
    materials,
    operations,
    urlDebug,
    askScout,
  ];

  for (const source of protectedSources) {
    const guard = source.indexOf("if (!getAuthToken())");
    assert.ok(guard >= 0, "Protected page is missing its signed-out guard");
    assert.ok(
      source.slice(guard, guard + 500).includes("return"),
      "Signed-out guard must return preview or login guidance before protected work",
    );
  }
});

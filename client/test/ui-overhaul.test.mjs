import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const shell = readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const homePage = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const introduction = readFileSync(new URL("../components/IntroductionHome.tsx", import.meta.url), "utf8");
const dashboard = readFileSync(new URL("../components/DashboardHome.tsx", import.meta.url), "utf8");
const jobSearch = readFileSync(new URL("../components/IndeedJobSearchManager.tsx", import.meta.url), "utf8");
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
const userReports = readFileSync(new URL("../components/UserReports.tsx", import.meta.url), "utf8");
const accountPage = readFileSync(new URL("../app/auth/page.tsx", import.meta.url), "utf8");
const searchCriteria = readFileSync(new URL("../components/SearchCriteriaManager.tsx", import.meta.url), "utf8");
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
  assert.match(profiles, /title="Upload Resume"/);
  assert.match(profiles, /> Upload File/);
  assert.doesNotMatch(profiles, /Import Resume/);
  assert.match(profiles, /Save Resume Profile/);
  assert.doesNotMatch(profiles, /Apply JSON/);
  assert.match(profiles, /ReadableResumeProfile/);
  assert.match(profiles, /setIsEditing\(true\)/);
  assert.match(profiles, /label=\{`Delete \$\{profile\.title\}`\}/);
  assert.match(profiles, /getResumeProfileDependencies\(profile\.id\)/);
  assert.match(profiles, /current\.filter\(\(item\) => item\.id !== profile\.id\)/);
  assert.match(profiles, /className="manual-resume-option"[\s\S]*Prefer manual entry\?[\s\S]*Create Resume Profile[\s\S]*className="profile-workspace"/);
  assert.doesNotMatch(profiles, /manual-resume-card/);
  const manualCreateFlow = profiles.slice(
    profiles.indexOf("function createBlankResumeProfile"),
    profiles.indexOf("async function setDefaultProfile"),
  );
  assert.match(manualCreateFlow, /setIsCreatingProfile\(true\)/);
  assert.doesNotMatch(manualCreateFlow, /createResumeProfile\(/);
  const resumeEditor = profiles.slice(
    profiles.indexOf('className="profile-card resume-profile-editor"'),
    profiles.indexOf("function ReadableResumeProfile"),
  );
  assert.match(resumeEditor, /selectedProfile \? setEditorFromProfile\(selectedProfile\) : resetEditor\(\)/);
  assert.doesNotMatch(resumeEditor, />Close<\/Button>/);
  assert.match(profiles, /title="Your Resumes"/);
  const readableProfile = profiles.slice(
    profiles.indexOf("function ReadableResumeProfile"),
    profiles.indexOf("function ProfileEditorPreview"),
  );
  assert.doesNotMatch(readableProfile, /variant="danger"/);
  assert.match(readableProfile, /onClick=\{onClose\}>Close<\/Button>/);
  assert.match(matching, /Choose a saved resume profile or paste resume text before matching/);
  assert.match(matching, /Low compatibility/);
  assert.match(matching, /MatchScoreBadge/);
  assert.match(matching, /const \[jobTitle, setJobTitle\] = useState\(""\)/);
  assert.match(matching, /Job title[\s\S]*Job description/);
  assert.match(matching, /location, application deadline, salary, and security clearance when applicable/);
  assert.match(jobs, /location, application deadline, salary, and security clearance when applicable/);
  assert.doesNotMatch(matching, /Paste job URL|Job source/);
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
  assert.match(shell, /currentUser\.tutorial_completed \? "\/dashboard" : "\/"/);
  assert.doesNotMatch(shell, /window\.location\.replace\("\/tutorial"\)/);
  assert.match(shell, /firstRunIncomplete/);
  assert.match(shell, /isTutorialRouteAllowed\(pathname\)/);
  assert.match(shell, /Finish Getting Started once to unlock navigation/);
  assert.match(shell, /<TutorialCoachmark \/>/);
  assert.match(shell, /href: "\/", label: "Home"/);
  assert.match(shell, /href: "\/dashboard", label: "Dashboard"/);
  assert.ok(shell.indexOf('label: "Job Search"') < shell.indexOf('label: "Saved Jobs"'));
  assert.doesNotMatch(shell, /笆ｼ/);
  assert.match(overhaul, /\.sidebar\.mobile-open/);
  assert.match(overhaul, /\.resume-profile-delete[\s\S]*grid-column: 1/);
  assert.match(overhaul, /\.resume-profile-open[\s\S]*grid-column: 2/);
});

test("home introduces resume matching while Job Search owns saved search criteria", () => {
  assert.match(homePage, /IntroductionHome/);
  assert.doesNotMatch(homePage, /DashboardHome/);
  assert.doesNotMatch(homePage, /QuickFindHome/);
  assert.match(introduction, /Find the job that suits you most/);
  assert.match(introduction, /href=\{isAuthenticated \? "\/tutorial\?replay=1" : "\/auth"\}/);
  assert.match(introduction, /> Getting Started/);
  assert.match(jobSearch, /listJobSearchCriteria\(\)/);
  assert.match(jobSearch, /title="Saved Search Criteria"/);
  assert.match(jobSearch, /Make a Search/);
  assert.match(jobSearch, /<\/section>\s*\n\s*<details[\s\S]*className="quick-find-search-editor"/);
  assert.match(jobSearch, /searchWithCriterion\(criterion\)/);
  assert.doesNotMatch(jobSearch, /className="quick-find-active-search"/);
  assert.doesNotMatch(jobSearch, />\s*Search Jobs\s*</);
  assert.match(jobSearch, /Save Search Options/);
  assert.doesNotMatch(jobSearch, /Save as search criteria/);
  assert.match(jobSearch, /else if \(saveAsCriterion\)[\s\S]*createJobSearchCriterion/);
  assert.match(jobSearch, /executeSearch\(trimmedKeyword, trimmedLocation, matchingCriterion, saveAdjustedSearch\)/);
  assert.doesNotMatch(profiles, /createJobSearchCriterion/);
  assert.doesNotMatch(jobSearch, /From resume/);
  assert.doesNotMatch(searchCriteria, /From resume/);
  assert.match(jobSearch, /setSearchEditorOpen\(false\)/);
  assert.match(jobSearch, /setSearchEditorOpen\(true\)/);
  assert.doesNotMatch(jobSearch, /Save this search\?/);
  assert.match(jobSearch, /executeSearch\(criterion\.keyword\.trim\(\), criterionLocation, criterion\)/);
  assert.match(searchCriteria, /updateJobSearchCriterion/);
  assert.match(searchCriteria, /deleteJobSearchCriterion/);
});

test("first-run tutorial requires ordered steps and only completion unlocks the account", () => {
  assert.match(tutorial, /window\.sessionStorage\.setItem\(tutorialSessionKey, "0"\)/);
  assert.doesNotMatch(tutorial, /Skip Step/);
  assert.match(tutorial, /Skip Getting Started/);
  assert.match(tutorial, /function postponeTutorial\(\)[\s\S]*removeItem\(tutorialSessionKey\)[\s\S]*window\.location\.href = "\/"/);
  assert.match(tutorial, /completeTutorial\(\)/);
  assert.match(tutorial, /window\.location\.href = "\/dashboard"/);
  assert.match(tutorial, /href: "\/profile"/);
  assert.match(tutorial, /href: "\/jobs\/search"/);
  assert.match(tutorial, /title: "View Saved Jobs and Match"[\s\S]*href: "\/jobs"/);
  assert.match(tutorial, /allowedPaths: \["\/jobs", "\/match"\]/);
  assert.match(tutorial, /const onTargetPage = isPathAllowedForStep\(pathname, step\)/);
  assert.match(tutorial, /export function tutorialRouteFallback\(\)/);
  assert.match(shell, /window\.location\.replace\(tutorialRouteFallback\(\)\)/);
  assert.doesNotMatch(shell, /if \(firstRunRouteBlocked\) window\.location\.replace\("\/"\)/);
  assert.ok(tutorial.indexOf('href: "/jobs/search"') < tutorial.indexOf('href: "/jobs"'));
  assert.doesNotMatch(tutorial, /title: "Match a job"/);
  assert.doesNotMatch(tutorial, /title: "Track applications"/);
  assert.match(tutorial, /!isLastStep \? \([\s\S]*Skip Getting Started[\s\S]*\) : null/);
  assert.doesNotMatch(dashboard, /href="\/tutorial\?replay=1"/);
  assert.doesNotMatch(dashboard, /> Getting Started/);
  assert.match(overhaul, /\.tutorial-overview-icon,[\s\S]*display: inline-flex;[\s\S]*justify-content: center;/);
  assert.match(overhaul, /\.tutorial-step-overview li > div > span/);
  assert.doesNotMatch(overhaul, /\.tutorial-step-overview span\s*\{/);
  assert.match(jobSearch, /isTutorialActive/);
  assert.match(jobSearch, /const RESULTS_PER_PAGE = 5;/);
  assert.match(jobSearch, /runMatching: !tutorialActive && runMatching/);
  assert.match(jobSearch, /\{!tutorialActive \? \([\s\S]*Run matching after import/);
});

test("job search results open from the row without redundant status or view controls", () => {
  assert.doesNotMatch(jobSearch, /<span>Status<\/span>/);
  assert.doesNotMatch(jobSearch, /<span>Actions<\/span>/);
  assert.doesNotMatch(jobSearch, />View<\/Button>/);
  assert.match(jobSearch, /role="button"[\s\S]*aria-label=\{`View \$\{item\.title/);
  assert.match(jobSearch, /onClick=\{\(\) => setActiveResult\(item\)\}/);
  assert.match(jobSearch, /onClick=\{\(event\) => event\.stopPropagation\(\)\}/);
  assert.match(jobSearch, /icon=\{X\}[\s\S]*onClick=\{onClose\}>Close<\/Button>/);
  assert.match(overhaul, /\.indeed-search-row:not\(\.bulk-import-header\):focus-visible/);
  assert.match(overhaul, /\.job-search-detail-card \.job-description-text \{[\s\S]*?max-height: min\(52vh, 520px\);[\s\S]*?overflow-y: auto;/);
});

test("dashboard and jobs use the shared feedback and hierarchy components", () => {
  assert.match(dashboard, /PageHeader/);
  assert.match(dashboard, /SkeletonRows/);
  assert.match(dashboard, /className="dashboard-compact-list"/);
  assert.match(dashboard, /className="dashboard-compact-job"/);
  assert.match(jobs, /Toolbar/);
  assert.match(jobs, /EmptyState/);
  assert.match(jobs, /MatchScoreBadge/);
  assert.match(jobs, /aria-label=\{selectionMode \? `Select \$\{job\.title/);
  assert.match(jobs, /className="job-detail-tabs"/);
  assert.match(jobs, /"Match Analysis" : "Match Resume"/);
  assert.match(jobs, />\s*Match All\s*<\/Button>/);
  assert.match(jobs, /params\.set\("job_ids", sortedJobs\.map/);
  assert.match(jobs, /!selectionMode && !job\.match_data \? \(/);
  assert.match(jobs, /await draftJobFromText\(description\)/);
  assert.match(jobs, /save_as_user_edit: true/);
  assert.doesNotMatch(jobs, />\s*View\s*</);
  assert.doesNotMatch(jobs, />\s*Match Data\s*</);
  assert.doesNotMatch(jobs, />\s*Profile\s*</);
  assert.doesNotMatch(jobs, />\s*Description\s*</);
  assert.match(jobs, /className="job-editor-section job-notes-section"/);
  assert.match(jobs, /className="job-editor-section job-profile-section"/);
  assert.match(jobs, /className="job-description-details"/);
  assert.match(jobs, /className="job-description-toggle"/);
  assert.match(overhaul, /\.job-description-details \.job-description-text[\s\S]*?max-height: min\(52vh, 520px\);[\s\S]*?overflow-y: auto;/);
  assert.match(jobs, /ReadableJobProfile/);
  assert.match(jobs, /job-notes-readonly/);
  assert.match(jobs, /title="Structured job profile not available"[\s\S]*action=\{editor\.id && onAnalyze/);
  assert.match(jobs, /isSavedJob && editor\.isEditing \? \([\s\S]*Save changes[\s\S]*onClick=\{onCancelEdit\}[\s\S]*Cancel/);
  assert.match(jobs, /const savedJob = jobs\.find\(\(job\) => job\.id === editor\.id\);[\s\S]*setEditor\(editorFromJob\(savedJob\)\)/);
  assert.match(jobs, /analyzeJob\(jobId\)/);
  assert.match(jobs, />\s*Analyze\s*<\/Button>/);
  assert.match(jobs, /const hasMatch = Boolean\(job\.match_data\)/);
  assert.match(jobs, />\s*Re-match\s*<\/Button>/);
  assert.match(jobs, />Select Jobs<\/Button>/);
  assert.match(jobs, /href="\/jobs\/import-url"/);
  assert.match(jobs, /> Use Job URL<\/a>/);
  assert.match(jobs, /> Paste Job Description<\/a>/);
  assert.doesNotMatch(jobs, /href="\/jobs\/import"/);
  assert.doesNotMatch(admin, /href="\/jobs\/import-url"/);
  assert.match(admin, /href="\/jobs\/import"/);
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
  assert.match(shell, /async function signOut\(\)[\s\S]*window\.location\.replace\("\/"\);/);
  assert.match(auth, /async function signOut\(\)[\s\S]*window\.location\.replace\("\/"\);/);
  assert.match(auth, /await deleteAccount\(deletePassword\);[\s\S]*window\.location\.replace\("\/"\);/);
  assert.match(userReports, /Report a problem or share feedback\./);
  assert.match(userReports, /Your report was submitted\./);
  assert.doesNotMatch(userReports, /listUserReports|report-history|track its review status/);
  assert.match(askScout, /Badge tone=\{statusTone/);
  assert.doesNotMatch(auth, /Account security/);
  assert.match(auth, /variant="danger"/);
  assert.match(auth, /aria-pressed=\{mode === "login"\}/);
  assert.match(admin, /admin-diagnostic-link/);
  assert.match(admin, /href="\/operations"/);
  assert.doesNotMatch(accountPage, /href="\/operations"/);
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

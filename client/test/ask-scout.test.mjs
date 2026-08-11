import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appShell = readFileSync(new URL("../components/AppShell.tsx", import.meta.url), "utf8");
const scoutPage = readFileSync(new URL("../components/AskScoutPage.tsx", import.meta.url), "utf8");
const jobsManager = readFileSync(new URL("../components/JobsManager.tsx", import.meta.url), "utf8");
const listImport = readFileSync(new URL("../components/JobListImportManager.tsx", import.meta.url), "utf8");
const jobSearch = readFileSync(new URL("../components/IndeedJobSearchManager.tsx", import.meta.url), "utf8");

test("authenticated shell exposes the persistent Ask Scout sidebar action with page context", () => {
  assert.match(appShell, /className="sidebar-scout-action"/);
  assert.match(appShell, /\/ask-scout\?from=/);
  assert.match(appShell, /aria-label="Open Ask Scout"/);
});

test("signed-out Ask Scout renders login guidance instead of invoking the provider", () => {
  assert.match(scoutPage, /if \(!getAuthToken\(\)\)/);
  assert.match(scoutPage, /Login \/ Register/);
  assert.match(scoutPage, /await askScout/);
});

test("destination adapters only assign query prefills", () => {
  assert.match(jobsManager, /get\("job_url"\)/);
  assert.match(jobsManager, /setJobUrl\(value\)/);
  assert.match(listImport, /get\("list_url"\)/);
  assert.match(listImport, /setListUrl\(value\)/);
  assert.match(jobSearch, /get\("keyword"\)/);
  assert.match(jobSearch, /get\("location"\)/);
  assert.doesNotMatch(jobSearch, /useEffect\(\(\) => \{[^}]*search\(/s);
  assert.doesNotMatch(listImport, /useEffect\(\(\) => \{[^}]*discover\(/s);
});

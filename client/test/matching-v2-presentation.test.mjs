import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("../components/V2MatchInbox.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../lib/api.ts", import.meta.url), "utf8");

test("web match presentation preserves supported and provisional V2 states", () => {
  assert.match(api, /overall_score: number \| null/);
  assert.match(api, /needs_more_information/);
  assert.match(source, /More information needed/);
  assert.match(source, /qualification_coverage/);
  assert.match(source, /Preference conflicts/);
});

test("web presentation keeps legacy results readable and does not link raw evidence IDs", () => {
  assert.match(source, /historical result remains readable/);
  assert.match(source, /Evidence IDs are not links/);
  assert.doesNotMatch(source, /href=.*evidence_refs/);
});

test("provider failures are presented as safe client errors", () => {
  assert.match(source, /Could not load matches/);
  assert.match(source, /AlertBanner tone="danger"/);
});

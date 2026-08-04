import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const configSource = readFileSync(new URL("../lib/config.ts", import.meta.url), "utf8");

test("local API fallback preserves the browser hostname for same-site session cookies", () => {
  assert.match(configSource, /hostname === "localhost" \|\| hostname === "127\.0\.0\.1"/);
  assert.match(configSource, /\$\{window\.location\.protocol\}\/\/\$\{hostname\}:5010\/api\/v1/);
  assert.match(configSource, /parsed\.hostname = browserHostname/);
});

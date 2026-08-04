import assert from "node:assert/strict";
import test from "node:test";

import { buildContentSecurityPolicy, buildSecurityHeaders } from "../security-headers.mjs";

test("production policy contains the required restrictive directives", () => {
  const policy = buildContentSecurityPolicy("production");

  assert.match(policy, /default-src 'self'/);
  assert.match(policy, /object-src 'none'/);
  assert.match(policy, /frame-ancestors 'none'/);
  assert.match(policy, /connect-src 'self'/);
  assert.match(policy, /upgrade-insecure-requests/);
  assert.doesNotMatch(policy, /unsafe-eval/);
  assert.doesNotMatch(policy, /localhost/);
});

test("security header set includes browser privacy and capability policies", () => {
  const headers = new Map(buildSecurityHeaders("production").map((header) => [header.key, header.value]));

  assert.equal(headers.get("Referrer-Policy"), "no-referrer");
  assert.equal(headers.get("X-Frame-Options"), "DENY");
  assert.equal(headers.get("X-Content-Type-Options"), "nosniff");
  assert.match(headers.get("Permissions-Policy") || "", /camera=\(\)/);
  assert.match(headers.get("Permissions-Policy") || "", /microphone=\(\)/);
});

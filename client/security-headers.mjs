function apiOrigin() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!configured) return null;
  try {
    const parsed = new URL(configured);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : null;
  } catch {
    return null;
  }
}

export function buildContentSecurityPolicy(environment = process.env.NODE_ENV) {
  const development = environment !== "production";
  const scriptSources = ["'self'", "'unsafe-inline'"];
  const connectSources = ["'self'"];
  const configuredApiOrigin = apiOrigin();

  if (development) {
    scriptSources.push("'unsafe-eval'");
    connectSources.push("http://localhost:*", "http://127.0.0.1:*", "ws://localhost:*", "ws://127.0.0.1:*");
  }
  if (configuredApiOrigin && !connectSources.includes(configuredApiOrigin)) {
    connectSources.push(configuredApiOrigin);
  }

  const directives = [
    ["default-src", "'self'"],
    ["base-uri", "'self'"],
    ["object-src", "'none'"],
    ["frame-ancestors", "'none'"],
    ["form-action", "'self'"],
    ["script-src", ...scriptSources],
    ["style-src", "'self'", "'unsafe-inline'"],
    ["img-src", "'self'", "data:", "blob:"],
    ["font-src", "'self'", "data:"],
    ["media-src", "'self'", "blob:"],
    ["worker-src", "'self'", "blob:"],
    ["connect-src", ...connectSources],
    ["manifest-src", "'self'"],
  ];
  if (!development) directives.push(["upgrade-insecure-requests"]);
  return directives.map((parts) => parts.join(" ")).join("; ");
}

export function buildSecurityHeaders(environment = process.env.NODE_ENV) {
  return [
    { key: "Content-Security-Policy", value: buildContentSecurityPolicy(environment) },
    { key: "Referrer-Policy", value: "no-referrer" },
    {
      key: "Permissions-Policy",
      value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
    },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-DNS-Prefetch-Control", value: "off" },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  ];
}

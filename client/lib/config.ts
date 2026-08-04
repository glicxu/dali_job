export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured) {
    if (typeof window !== "undefined") {
      try {
        const parsed = new URL(configured);
        const browserHostname = window.location.hostname;
        const configuredIsLocal = parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1";
        const browserIsLocal = browserHostname === "localhost" || browserHostname === "127.0.0.1";
        if (configuredIsLocal && browserIsLocal) {
          parsed.hostname = browserHostname;
          return parsed.toString().replace(/\/$/, "");
        }
      } catch {
        // requestJson will expose an invalid explicit URL as a request failure.
      }
    }
    return configured.replace(/\/$/, "");
  }

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return `${window.location.protocol}//${hostname}:5010/api/v1`;
    }
  }

  return "http://127.0.0.1:5010/api/v1";
}

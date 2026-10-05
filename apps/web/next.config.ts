import type { NextConfig } from "next";

// `/api/*` is the backend (spec 05). In production Caddy routes it (infra/caddy/Caddyfile), so the browser talks to one
// origin and the session cookie is first-party. For `next dev` against a local api, set API_PROXY_URL
// (e.g. http://localhost:8000) and Next forwards `/api/*` the same way. Unset, no rewrite exists: mock mode needs none.
const apiProxy = process.env.API_PROXY_URL?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Self-contained server bundle for the production image (apps/web/Dockerfile, spec 06).
  output: "standalone",
  async rewrites() {
    return apiProxy ? [{ source: "/api/:path*", destination: `${apiProxy}/api/:path*` }] : [];
  },
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the production image (apps/web/Dockerfile, spec 06).
  output: "standalone",
};

export default nextConfig;

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enables a self-contained build output for the production Dockerfile
  // (infra/../apps/web/Dockerfile) — see docs/adr/0001-technology-stack.md.
  output: "standalone",
};

export default nextConfig;

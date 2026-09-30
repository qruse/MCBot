import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: process.env.CLOUDFLARE_BUILD === "1" ? "export" : "standalone",
};

export default nextConfig;

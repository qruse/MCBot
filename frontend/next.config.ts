import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  output: process.env.CLOUDFLARE_BUILD === "1" ? "export" : "standalone",
};

export default nextConfig;

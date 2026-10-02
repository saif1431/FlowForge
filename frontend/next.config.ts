import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.E2E_TEST === "1" ? ".next-e2e" : ".next",
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;

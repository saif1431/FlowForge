import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.E2E_TEST === "1" ? ".next-e2e" : ".next",
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    if (!["localhost", "127.0.0.1", "[::1]"].includes(new URL(api).hostname)) return [];
    return [{ source: "/api/v1/:path*", destination: `${api.replace(/\/$/, "")}/api/v1/:path*` }];
  },
};

export default nextConfig;

import type { NextConfig } from "next";

const backendBase =
  process.env.BACKEND_INTERNAL_URL ||
  (process.env.BACKEND_INTERNAL_HOSTPORT
    ? `http://${process.env.BACKEND_INTERNAL_HOSTPORT}`
    : "http://localhost:8095");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

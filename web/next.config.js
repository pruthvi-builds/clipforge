/** @type {import('next').NextConfig} */
const API = process.env.CLIPFORGE_API_URL || "http://127.0.0.1:8787";

const nextConfig = {
  reactStrictMode: true,
  // Proxy /api/* to the local FastAPI backend so the browser only ever talks
  // to the Next.js origin (no CORS juggling in the common case).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

module.exports = nextConfig;

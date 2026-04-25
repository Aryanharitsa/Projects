/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow inlining the public API base at build time.
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};

export default nextConfig;

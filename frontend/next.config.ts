import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  outputFileTracingIncludes: {
    "/*": ["./public/**/*"],
  },
  experimental: {
    earlyHints: false,
  },
};

export default nextConfig;

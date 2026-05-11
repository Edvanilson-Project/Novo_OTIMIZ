import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL?.replace('/api/v1', '') || 'http://localhost:3001';

const nextConfig: NextConfig = {
  reactStrictMode: false,

  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },

  experimental: {
    optimizePackageImports: ['@mui/material', '@tabler/icons-react'],
  },

  webpack: (config) => {
    config.optimization.moduleIds = 'deterministic';
    return config;
  },
};

export default nextConfig;

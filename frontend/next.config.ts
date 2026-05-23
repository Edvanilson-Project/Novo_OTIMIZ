import path from 'node:path';
import type { NextConfig } from "next";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL?.replace('/api/v1', '') || 'http://localhost:3001';
const SENTRY_DEV_STUB = path.join(process.cwd(), 'src/lib/sentry-dev-stub.ts');

const nextConfig: NextConfig = {
  reactStrictMode: false,

  turbopack: process.env.NODE_ENV !== 'production'
    ? {
        resolveAlias: {
          '@sentry/nextjs': SENTRY_DEV_STUB,
        },
      }
    : undefined,

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

  webpack: (config, { dev }) => {
    if (dev) {
      config.resolve = config.resolve ?? {};
      config.resolve.alias = {
        ...(config.resolve.alias ?? {}),
        '@sentry/nextjs': SENTRY_DEV_STUB,
      };
    }

    config.optimization.moduleIds = 'deterministic';
    return config;
  },
};

export default nextConfig;

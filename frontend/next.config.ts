import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: false,
  
  // Otimiza pacotes pesados para evitar erros de MODULE_NOT_FOUND em chunks numerados
  experimental: {
    optimizePackageImports: ['@mui/material', '@tabler/icons-react'],
  },

  webpack: (config) => {
    // Garante IDs de módulos consistentes entre builds
    config.optimization.moduleIds = 'deterministic';
    return config;
  },
};

export default nextConfig;

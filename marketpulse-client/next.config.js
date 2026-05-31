/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['react-markdown', 'remark-gfm', 'devlop'],
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  // API proxy handled by src/middleware.ts
}

module.exports = nextConfig

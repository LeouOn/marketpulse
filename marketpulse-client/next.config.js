/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
  // Note: /api/llm/chat is handled by src/app/api/llm/chat/route.ts
  // (file-based routes take priority over rewrites in App Router).
  // All other /api/* requests are proxied to the FastAPI backend.
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ]
  },
}

module.exports = nextConfig
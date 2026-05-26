import path from 'node:path'

/** @type {import('next').NextConfig} */
const nextConfig = {
  typedRoutes: false,
  outputFileTracingRoot: path.resolve('.'),
  async redirects() {
    return [
      {
        source: '/index',
        destination: '/',
        permanent: false
      }
    ]
  }
}

export default nextConfig

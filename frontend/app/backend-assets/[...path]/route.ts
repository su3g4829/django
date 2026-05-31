import type { NextRequest } from 'next/server'

const BACKEND_ORIGIN = process.env.DJANGO_API_ORIGIN ?? 'http://127.0.0.1:8080'

async function proxyAsset(request: NextRequest, pathSegments: string[]) {
  const targetPath = pathSegments.join('/')
  const upstreamUrl = `${BACKEND_ORIGIN}/${targetPath}${request.nextUrl.search}`
  const upstream = await fetch(upstreamUrl, {
    method: 'GET',
    redirect: 'follow',
    cache: 'no-store',
  })

  const body = await upstream.arrayBuffer()
  return new Response(body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('content-type') ?? 'application/octet-stream',
      'Cache-Control': upstream.headers.get('cache-control') ?? 'no-store',
    },
  })
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxyAsset(request, path)
}

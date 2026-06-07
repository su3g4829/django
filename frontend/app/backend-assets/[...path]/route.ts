import type { NextRequest } from 'next/server'

/**
 * 後端靜態資產代理。
 *
 * 這支 route 讓前端可以透過 Next.js 同源路徑去拿 Django 提供的圖片或其他檔案，
 * 避免前端直接暴露後端位址，也方便之後統一處理快取與部署環境差異。
 *
 * 來源：
 * - `NextRequest` / route handler 來自 `next/server`
 * - `fetch` / `Response` 來自 Web Fetch API 規範
 */
const BACKEND_ORIGIN = process.env.DJANGO_API_ORIGIN ?? 'http://127.0.0.1:8080'

/**
 * 將 `/backend-assets/...` 轉送到 Django 實際資產路徑。
 *
 * 用法：
 * - 前端頁面只要把 Django 回傳的 `/static/...` 改寫成 `/backend-assets/static/...`
 * - 這支 route 就會代為向後端請求真正資產內容
 *
 * 程式語法：
 * - `async function` 表示這個函式內會使用 `await` 等待非同步工作完成
 * - 這裡的非同步工作就是向 Django 發送 `fetch()` 請求
 */
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

/**
 * 目前只需要支援 GET，因為這條 route 專門用來讀取資產檔案。
 *
 * 程式語法：
 * - Next.js App Router 允許直接匯出 `GET()`，把它當成這條 route 的 HTTP GET handler
 * - `await context.params` 代表先等動態路由參數解析完，再繼續往下執行
 */
export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxyAsset(request, path)
}

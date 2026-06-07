/**
 * 後端 API 代理路由
 *
 * 功能：
 * - 將 Next.js 前端的 `/api/backend/...` 請求代理到 Django DRF `/api/v1/...`
 * - 轉送 cookie 與 CSRF 資訊，讓 session 型登入可在前後端分離架構下正常運作
 * - 統一前端呼叫後端 API 的入口，避免瀏覽器直接跨來源打 Django
 *
 * 來源：
 * - route handler / `NextRequest` 來自 `next/server`
 * - `fetch` / `Headers` / `Response` 來自 Web Fetch API
 * - CSRF 規則對應 Django CSRF middleware
 */

import type { NextRequest } from 'next/server'

/**
 * Django API 主機位址。
 *
 * 預設打本機 Django 開發伺服器；
 * 若前後端分開部署，可改由環境變數 `DJANGO_API_ORIGIN` 指向實際後端。
 */
const BACKEND_ORIGIN = process.env.DJANGO_API_ORIGIN ?? 'http://127.0.0.1:8080'

/**
 * 將 Next.js 收到的 API 請求代理到 Django。
 *
 * request:
 * - Next.js route handler 收到的原始請求物件
 *
 * pathSegments:
 * - 由 `[...path]` 動態路由拆出的路徑陣列
 * - 例如 `/api/backend/products/acme-mug/` 會變成 `['products', 'acme-mug']`
 *
 * 用法：
 * - React page / component 端應統一透過 `frontend/lib/api.ts` 的 `apiFetch()`
 * - 不直接在頁面裡硬寫 Django host，避免跨來源與 cookie 問題
 *
 * 程式語法：
 * - 這是一個 `async function`，因為代理流程包含多個非同步步驟：
 *   1. 讀 request body
 *   2. `fetch()` Django
 *   3. 等待 Django 回傳 response
 */
async function proxy(request: NextRequest, pathSegments: string[]) {
  /** Django API 需要的相對路徑，例如 `products/acme-mug`。 */
  const targetPath = pathSegments.join('/')
  /** 最終要呼叫的 Django DRF 完整網址，會保留原始 query string。 */
  const upstreamUrl = `${BACKEND_ORIGIN}/api/v1/${targetPath}/${request.nextUrl.search}`
  /** 要轉送給 Django 的 request headers 容器。 */
  const headers = new Headers()
  /** 瀏覽器帶來的 cookie，主要用來保留 Django session。 */
  const cookieHeader = request.headers.get('cookie')
  /** 原始請求的 content-type，讓 Django 能正確解析 JSON / form-data。 */
  const contentType = request.headers.get('content-type')
  /** 從瀏覽器 cookie 取出的 CSRF token，供寫入請求使用。 */
  const csrfToken = request.cookies.get('csrftoken')?.value

  // 明確告訴 Django DRF：前端這次預期收到 JSON，不要回傳 HTML。
  headers.set('Accept', 'application/json')
  if (cookieHeader) {
    // 將瀏覽器現有 cookie 原樣轉送給 Django。
    // 這樣 Django 才能辨識登入 session、使用者身份與 csrftoken。
    headers.set('Cookie', cookieHeader)
  }
  if (contentType) {
    // 保留原始內容格式，讓 Django 能正確解析 JSON、表單或 multipart 上傳資料。
    headers.set('Content-Type', contentType)
  }
  if (csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(request.method.toUpperCase())) {
    // 寫入型請求需要附上 CSRF token，否則 Django 預設會拒絕請求。
    headers.set('X-CSRFToken', csrfToken)
  }

  /**
   * 轉送到 Django 的 fetch 設定。
   *
   * - method: 沿用原始 HTTP 方法
   * - headers: 帶上 cookie / content-type / csrf
   * - redirect: 不讓 fetch 自動追轉址，交由前端自行處理
   * - cache: 關閉快取，避免管理或購物流程拿到舊資料
   */
  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: 'manual',
    cache: 'no-store',
  }

  /** GET/HEAD 以外的方法通常有 request body，這裡把原始 body 原封不動轉送。 */
  if (!['GET', 'HEAD'].includes(request.method.toUpperCase())) {
    init.body = await request.arrayBuffer()
  }

  /** Django 回傳的原始 response。 */
  let upstream: Response
  try {
    upstream = await fetch(upstreamUrl, init)
  } catch (error) {
    const detail =
      error instanceof Error
        ? `Django backend unavailable: ${BACKEND_ORIGIN}`
        : `Django backend unavailable: ${BACKEND_ORIGIN}`
    return new Response(JSON.stringify({ detail }), {
      status: 503,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }
  /** 先以文字讀出 response body，再原樣包裝回前端 response。 */
  const body = await upstream.text()
  /** 回傳給前端頁面或元件的 Next.js Response。 */
  const response = new Response(body, {
    status: upstream.status,
    headers: {
      'Content-Type': upstream.headers.get('content-type') ?? 'application/json',
    },
  })

  /**
   * Django 可能透過 `Set-Cookie` 更新 session / csrftoken。
   * 這裡把所有 cookie 收集起來，再附加回 Next.js response。
   */
  const setCookieList =
    typeof (upstream.headers as Headers & { getSetCookie?: () => string[] }).getSetCookie === 'function'
      ? (upstream.headers as Headers & { getSetCookie: () => string[] }).getSetCookie()
      : upstream.headers.get('set-cookie')
        ? [upstream.headers.get('set-cookie') as string]
        : []

  for (const cookie of setCookieList) {
    response.headers.append('set-cookie', cookie)
  }

  return response
}

/** 代理 GET 請求到 Django。 */
export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxy(request, path)
}

/** 代理 POST 請求到 Django。 */
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxy(request, path)
}

/** 代理 PUT 請求到 Django。 */
export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxy(request, path)
}

/** 代理 PATCH 請求到 Django。 */
export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxy(request, path)
}

/** 代理 DELETE 請求到 Django。 */
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  return proxy(request, path)
}


'use client'

/**
 * Shared frontend API helpers.
 *
 * This module standardizes how Next.js pages call the Django DRF backend
 * through the local `/api/backend/...` proxy route.
 *
 * Sources:
 * - browser `fetch` API
 * - Next.js route proxy at `app/api/backend/[...path]/route.ts`
 * - Django session + CSRF flow on the backend
 * - TypeScript generic / Promise 語法
 */

/**
 * HTTP methods that do not require CSRF protection.
 */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * Global event name used to notify UI shells that app bootstrap counters
 * such as cart / compare / favorites should refresh.
 */
export const APP_BOOTSTRAP_REFRESH_EVENT = 'store:bootstrap-refresh'

/**
 * Partial bootstrap counters that can be refreshed after client-side actions.
 */
export type BootstrapRefreshDetail = {
  cart_count?: number
  compare_count?: number
  favorite_count?: number
}

/**
 * Dispatch a browser event so shared UI such as the site header can refresh
 * app-wide counters without a full page reload.
 *
 * `CustomEvent` 來自瀏覽器 DOM Event API。
 * 這種做法適合做跨元件輕量通知，不必引入更重的全域 state manager。
 */
export function dispatchAppBootstrapRefresh(detail: BootstrapRefreshDetail = {}) {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent(APP_BOOTSTRAP_REFRESH_EVENT, { detail }))
}

/**
 * Ensure Django has issued a fresh CSRF cookie before any write request.
 *
 * Source:
 * - Django CSRF middleware expects a valid `csrftoken` cookie on unsafe methods.
 *
 * 程式語法：
 * - `async` 代表函式會回傳 `Promise`
 * - 呼叫端可以用 `await ensureCsrfCookie()`，先等 cookie 準備好再送出寫入請求
 * - 這支函式本身不回傳 payload，只負責準備 CSRF cookie
 */
export async function ensureCsrfCookie() {
  await fetch('/api/backend/auth/csrf/', {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
  })
}

/**
 * Call the Django backend through the local Next.js proxy route.
 *
 * Notes:
 * - Non-FormData request bodies default to `application/json`.
 * - Write requests automatically bootstrap a CSRF cookie first.
 * - Non-2xx responses are normalized into thrown `Error` messages.
 *
 * Usage:
 * - All page / component API calls should prefer this helper instead of raw `fetch`
 * - This keeps cookie, CSRF, error parsing, and proxy paths consistent
 *
 * 程式語法：
 * - `<T>` 是 TypeScript generic，表示呼叫端可指定這次預期的回傳型別
 * - `Promise<T>` 表示函式最終會非同步回傳一個 `T`
 * - 因此頁面常會寫成 `await apiFetch<CartPayload>(...)`
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  const normalizedPath = (() => {
    const trimmed = path.trim()
    if (!trimmed) {
      return ''
    }
    if (trimmed === '/') {
      return ''
    }
    return trimmed.replace(/\/+$/, '')
  })()

  if (!SAFE_METHODS.has(method)) {
    await ensureCsrfCookie()
  }

  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData
  if (!isFormData && init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`/api/backend${normalizedPath}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
    cache: 'no-store',
  })

  /**
   * 統一在這裡判斷 Django 回傳的是 JSON 還是純文字。
   *
   * 這樣上層頁面只需要處理型別 `T`，不必每頁都重寫 content-type 判斷。
   */
  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    let detail = 'Request failed.'

    if (typeof payload === 'object' && payload) {
      if ('detail' in payload && (payload as { detail?: unknown }).detail) {
        detail = String((payload as { detail: unknown }).detail)
      } else {
        // 將 Django serializer / validation 的欄位錯誤攤平成單一字串，方便頁面直接顯示。
        const fieldMessages = Object.entries(payload as Record<string, unknown>)
          .flatMap(([field, value]) => {
            if (Array.isArray(value)) {
              return value.map((item) => `${field}: ${String(item)}`)
            }
            if (typeof value === 'string') {
              return [`${field}: ${value}`]
            }
            return []
          })
          .filter(Boolean)

        if (fieldMessages.length) {
          detail = fieldMessages.join(' | ')
        }
      }
    }

    throw new Error(detail)
  }

  return payload as T
}

/**
 * Convert a simple key-value object into a query string, skipping empty values.
 *
 * `URLSearchParams` 來自 Web 平台標準 API，
 * 用它組 query string 比手動字串拼接更安全，也會自動處理 encoding。
 */
export function toQueryString(values: Record<string, string | number | undefined | null>) {
  const params = new URLSearchParams()

  Object.entries(values).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return
    }
    params.set(key, String(value))
  })

  const query = params.toString()
  return query ? `?${query}` : ''
}

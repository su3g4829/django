'use client'

/**
 * 前端 API 輔助工具
 *
 * 功能：
 * - 統一包裝 `fetch`
 * - 在寫入型請求前先確保 Django 已發出 `csrftoken`
 * - 一律透過 Next.js proxy `/api/backend/...` 呼叫 Django DRF
 * - 將後端錯誤整理成可直接顯示的 `Error` 訊息
 */

/**
 * SAFE_METHODS:
 * - 不會改動資料狀態的 HTTP 方法集合
 * - 這些方法通常不需要額外附帶 CSRF token
 */
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

/**
 * 先向 Django 要求一個 CSRF cookie。
 *
 * 作用：
 * - 讓後續的 POST / PUT / PATCH / DELETE 可帶上 `csrftoken`
 * - 避免 Django 因 CSRF 驗證失敗而拒絕請求
 */
async function ensureCsrfCookie() {
  await fetch('/api/backend/auth/csrf/', {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
  })
}

/**
 * 統一呼叫 Django DRF API。
 *
 * T:
 * - 預期的回傳型別
 *
 * path:
 * - DRF API 的相對路徑
 * - 例如 `/products/acme-mug/`、`/me/profile/`
 *
 * init:
 * - 原生 fetch 設定
 * - 可帶 `method`、`body`、`headers` 等參數
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  /** method: 這次請求的 HTTP 方法，預設為 GET。 */
  const method = (init.method ?? 'GET').toUpperCase()

  /** headers: 將呼叫端傳入的 header 轉成可修改的 Headers 物件。 */
  const headers = new Headers(init.headers)

  /**
   * 若是寫入型請求，先確保已拿到 Django 的 CSRF cookie。
   * 這樣 proxy route 才能把 `csrftoken` 轉送給後端。
   */
  if (!SAFE_METHODS.has(method)) {
    await ensureCsrfCookie()
  }

  /**
   * 判斷這次 body 是否為 FormData。
   *
   * 原因：
   * - FormData 上傳時，瀏覽器會自動補 multipart boundary
   * - 若手動覆蓋 `Content-Type`，上傳格式可能會失敗
   */
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData

  /**
   * 一般 JSON 請求若尚未指定 `Content-Type`，預設補成 `application/json`。
   */
  if (!isFormData && init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  /**
   * 實際送出的請求會先打到 Next.js proxy route。
   *
   * 好處：
   * - 統一前端呼叫後端 API 的入口
   * - 讓 cookie / CSRF / session 轉送邏輯集中管理
   */
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
    cache: 'no-store',
  })

  /** contentType: 後端回傳內容格式，用來判斷要用 JSON 還是文字解析。 */
  const contentType = response.headers.get('content-type') ?? ''

  /**
   * payload:
   * - 若後端回傳 JSON，就解析成物件
   * - 否則保留為純文字
   */
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  /**
   * 若 HTTP 狀態不是 2xx，統一拋出 Error。
   *
   * 優先使用 Django DRF 常見的 `detail` 欄位；
   * 若沒有 detail，則回退成固定英文訊息。
   */
  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : 'Request failed.'
    throw new Error(detail)
  }

  return payload as T
}

/**
 * 將一般物件轉成 query string。
 *
 * values:
 * - 鍵值對物件
 * - 值若為 `undefined`、`null` 或空字串，會自動略過
 *
 * 回傳：
 * - 例如 `?page=2&brand=ACME`
 * - 若沒有有效參數，回傳空字串
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

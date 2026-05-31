'use client'

/**
 * Shared frontend API helpers.
 *
 * This module standardizes how Next.js pages call the Django DRF backend
 * through the local `/api/backend/...` proxy route.
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
 */
export function dispatchAppBootstrapRefresh(detail: BootstrapRefreshDetail = {}) {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent(APP_BOOTSTRAP_REFRESH_EVENT, { detail }))
}

/**
 * Ensure Django has issued a fresh CSRF cookie before any write request.
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
 */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)

  if (!SAFE_METHODS.has(method)) {
    await ensureCsrfCookie()
  }

  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData
  if (!isFormData && init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`/api/backend${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
    cache: 'no-store',
  })

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    let detail = 'Request failed.'

    if (typeof payload === 'object' && payload) {
      if ('detail' in payload && (payload as { detail?: unknown }).detail) {
        detail = String((payload as { detail: unknown }).detail)
      } else {
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

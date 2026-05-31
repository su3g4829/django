/**
 * 後端靜態資產網址工具。
 *
 * 功能：
 * - 將 Django 回傳的 `/static/...` 路徑轉成可由 Next.js 前端讀取的代理網址
 * - 已是完整 http/https 網址時原樣回傳
 */

export function toBackendAssetUrl(path?: string | null) {
  if (!path) {
    return ''
  }

  if (/^https?:\/\//i.test(path)) {
    return path
  }

  const normalized = path.startsWith('/') ? path.slice(1) : path
  return `/backend-assets/${normalized}`
}

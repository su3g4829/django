/**
 * 後端靜態資產路徑轉換 helper。
 *
 * 這支模組不依賴 React，只是一般 TypeScript 函式模組，所以可以同時被：
 * - Next.js route handler
 * - Client Component
 * - 其他 `lib/*` helper
 * 共用。
 *
 * 這裡處理的核心問題是：
 * Django 端常回傳 `/static/...` 或相對路徑，但前端為了避開跨來源與權限細節，
 * 會統一經過 Next.js 的 `/backend-assets/*` proxy route 取檔。
 */

/**
 * 把 Django/後端資產路徑轉成前端可直接使用的 proxy URL。
 *
 * 型別 `path?: string | null` 的意思：
 * - `?` 來自 TypeScript，可讓呼叫端不傳參數。
 * - `string | null` 是 union type，代表這個值可能是字串，也可能是 `null`。
 *
 * 這個函式故意不宣告回傳型別，讓 TypeScript 透過 `return` 自動推導成 `string`。
 */
export function toBackendAssetUrl(path?: string | null) {
  if (!path) {
    return ''
  }

  /**
   * `RegExp.test(...)` 來自 JavaScript 正規表示式 API。
   * 這裡用來判斷呼叫端是否已經給了完整的 `http://` 或 `https://` URL。
   * 如果是完整網址，就直接回傳，不再多包一層 proxy。
   */
  if (/^https?:\/\//i.test(path)) {
    return path
  }

  /**
   * `startsWith` 來自 JavaScript `String` API。
   * 這裡把前導 `/` 拿掉，是因為後面要手動組成 `/backend-assets/${normalized}`，
   * 避免路徑變成雙斜線。
   */
  const normalized = path.startsWith('/') ? path.slice(1) : path
  return `/backend-assets/${normalized}`
}

'use client'

/**
 * 補充：
 * 這支模組本質上是「跨頁但不跨裝置」的草稿儲存層。
 * 只要同一個瀏覽器分頁工作階段還在，就能保留暫存內容。
 */

/**
 * session draft helper。
 *
 * 用來暫存「尚未正式送出，但跨頁面還需要保留」的表單狀態，
 * 例如 checkout 配送方式、會員編輯中的暫存欄位等。
 *
 * 來源：
 * - 底層依賴瀏覽器 `window.sessionStorage`
 * - 和 React state 不同，重新整理同一個分頁後仍可保留
 * - `function foo<T>(...)` 裡的 `<T>` 是 TypeScript generic，代表同一支函式可重用在不同資料型別
 */
const DRAFT_PREFIX = 'store:draft:'

// 所有草稿都加同一個 prefix，方便一次清理，也避免撞到其他 sessionStorage key。
function toDraftKey(key: string) {
  return `${DRAFT_PREFIX}${key}`
}

/**
 * 讀取單一草稿，若 JSON 解析失敗則直接視為不存在。
 *
 * `T | null` 的意思：
 * - 成功時回傳指定型別 `T`
 * - 沒有資料或解析失敗時回傳 `null`
 */
export function getSessionDraft<T>(key: string): T | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(toDraftKey(key))
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

/**
 * 寫入單一草稿。
 *
 * `JSON.stringify(value)` 的原因：
 * - `sessionStorage` 只能存字串
 * - 所以物件、陣列或巢狀結構都要先序列化
 */
export function setSessionDraft<T>(key: string, value: T) {
  if (typeof window === 'undefined') return
  window.sessionStorage.setItem(toDraftKey(key), JSON.stringify(value))
}

/**
 * 刪除單一草稿。
 */
export function clearSessionDraft(key: string) {
  if (typeof window === 'undefined') return
  window.sessionStorage.removeItem(toDraftKey(key))
}

/**
 * 刪除專案所有 session 草稿。
 *
 * 常用於登入成功、送單完成或登出後清除舊暫存。
 *
 * 用法：
 * - 只清除 prefix 為 `store:draft:` 的 key
 * - 不會動到其他非本專案的 sessionStorage 資料
 * - 適合在登入成功、送單完成或登出後做全域清理
 */
export function clearAllSessionDrafts() {
  if (typeof window === 'undefined') return
  const keys = Object.keys(window.sessionStorage)
  for (const key of keys) {
    if (key.startsWith(DRAFT_PREFIX)) {
      window.sessionStorage.removeItem(key)
    }
  }
}

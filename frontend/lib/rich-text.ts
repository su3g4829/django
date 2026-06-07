'use client'

/**
 * 富文字 HTML 整理工具。
 *
 * 這支模組負責：
 * - 清洗富文字 HTML，避免危險標記直接渲染
 * - 轉換 Django `/static/...` 路徑成前端可顯示的 proxy 路徑
 * - 儲存前與顯示前做一致的 rich-text 正規化
 *
 * 來源：
 * - `DOMPurify` 來自 `dompurify` 套件
 * - 資產路徑規則對應本專案的 `/backend-assets/...` Next.js proxy route
 * - JavaScript RegExp 與 Web DOM API
 *
 * 語法補充：
 * - `/.../i` 是 JavaScript RegExp 語法，`i` 代表 ignore case
 * - `mode: 'to-display' | 'to-storage'` 是 TypeScript union literal type
 */
import DOMPurify from 'dompurify'

const HTML_TAG_PATTERN = /<\/?[a-z][\s\S]*>/i
const RAW_STATIC_PREFIX = '/static/'
const PROXY_STATIC_PREFIX = '/backend-assets/static/'

/**
 * 將純文字 escape 成安全 HTML。
 *
 * 用在使用者輸入其實不是 HTML、只是一般文字內容時，
 * 避免 `<script>` 這類字串被當成真標籤渲染。
 */
function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * 使用 DOMPurify 清洗輸入 HTML。
 *
 * 只保留目前專案 rich-text 會用到的安全標籤與屬性。
 *
 * 規範來源：
 * - 這裡遵循常見 HTML sanitization 實務，主動禁止 `script` / `iframe` / `embed`
 *
 * `DOMPurify.sanitize()` 的用途：
 * - 移除危險標籤與屬性
 * - 再搭配 allow-list，將 rich-text 限縮在本專案需要的安全範圍
 */
export function sanitizeRichTextHtml(rawHtml: string) {
  return DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'span', 'a', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3', 'img'],
    ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title', 'style'],
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed'],
  })
}

/**
 * 在「儲存格式」與「顯示格式」之間切換資產路徑。
 *
 * - to-display: `/static/...` -> `/backend-assets/static/...`
 * - to-storage: `/backend-assets/static/...` -> `/static/...`
 *
 * 為什麼分兩種模式：
 * - 前端顯示時，要走 Next.js proxy 路由
 * - 真正存回 Django 時，要保留後端認得的 `/static/...`
 */
function rewriteAssetUrls(html: string, mode: 'to-display' | 'to-storage') {
  if (typeof document === 'undefined' || !html) {
    if (mode === 'to-display') {
      return html.replaceAll(RAW_STATIC_PREFIX, PROXY_STATIC_PREFIX)
    }
    return html.replaceAll(PROXY_STATIC_PREFIX, RAW_STATIC_PREFIX)
  }

  const container = document.createElement('div')
  container.innerHTML = html
  container.querySelectorAll('img').forEach((image) => {
    const src = image.getAttribute('src') ?? ''
    if (mode === 'to-display' && src.startsWith(RAW_STATIC_PREFIX)) {
      image.setAttribute('src', src.replace(RAW_STATIC_PREFIX, PROXY_STATIC_PREFIX))
    }
    if (mode === 'to-storage' && src.startsWith(PROXY_STATIC_PREFIX)) {
      image.setAttribute('src', src.replace(PROXY_STATIC_PREFIX, RAW_STATIC_PREFIX))
    }
  })
  return container.innerHTML
}

/**
 * 把資料庫中的 rich-text 值整理成前端可直接渲染的內容。
 *
 * 會自動分辨：
 * - 原本就是 HTML
 * - 只是一般純文字
 *
 * `HTML_TAG_PATTERN.test(trimmed)` 的用途：
 * - 粗略判斷輸入是否包含 HTML 標籤
 * - 用來分流「真 HTML」與「單純文字」
 */
export function normalizeStoredRichText(rawValue: string) {
  const trimmed = rawValue.trim()
  if (!trimmed) {
    return ''
  }

  if (HTML_TAG_PATTERN.test(trimmed)) {
    return rewriteAssetUrls(sanitizeRichTextHtml(trimmed), 'to-display')
  }

  return rewriteAssetUrls(sanitizeRichTextHtml(escapeHtml(trimmed).replace(/\r?\n/g, '<br />')), 'to-display')
}

/**
 * 表單送回後端前的整理版本。
 *
 * 與顯示不同的地方是，會把 proxy 路徑轉回 Django 原始 `/static/...`。
 *
 * 用法：
 * - rich-text editor 送出前統一呼叫
 * - 避免每個頁面自行處理圖片路徑與 HTML 清洗
 */
export function prepareRichTextForStorage(rawValue: string) {
  const normalized = normalizeStoredRichText(rawValue)
  if (!normalized) {
    return ''
  }
  return rewriteAssetUrls(normalized, 'to-storage')
}

/**
 * 判斷 rich-text 是否真的有內容。
 *
 * 用來避免只有空白、空標籤或單純排版痕跡時也被當成有效文字。
 *
 * 這在表單驗證很常見：
 * - 視覺上看起來像有內容
 * - 實際上卻只剩 `<br>`、空白或 `&nbsp;`
 */
export function hasMeaningfulRichText(rawValue: string) {
  const normalized = normalizeStoredRichText(rawValue)
  if (!normalized) {
    return false
  }

  const textOnly = normalized
    .replace(/<img\b[^>]*>/gi, ' image ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()

  return textOnly.length > 0
}

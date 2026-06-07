'use client'

/**
 * 社群 rich-text 編輯器圖片上傳 helper。
 *
 * `use client` 來自 Next.js App Router 規範：
 * 這行不是一般 JavaScript 字串，而是 Next.js 的 Client Component 標記。
 * 因為這支 helper 會碰到：
 * - `FormData`
 * - `XMLHttpRequest`
 * - upload progress
 * - 瀏覽器 cookie / CSRF
 * 所以只能跑在瀏覽器端。
 */
import { ensureCsrfCookie } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'

type CommunityImageUploadPayload = {
  path: string
  detail?: string
}

/**
 * 上傳社群編輯器中的圖片。
 *
 * 這裡刻意不用 `fetch`，而改用 `XMLHttpRequest`，原因是：
 * Web Fetch API 雖然更現代，但瀏覽器原生 `fetch` 沒有穩定的 upload progress 事件，
 * rich-text 編輯器需要即時顯示「上傳到幾 %」，所以這裡保留 XHR 比較合理。
 *
 * `onProgress?: (percent: number) => void`：
 * - `?` 表示這個 callback 可傳可不傳
 * - `(percent: number) => void` 是 TypeScript 函式型別，代表呼叫端可收到數字百分比
 */
export async function uploadCommunityEditorImage(file: File, onProgress?: (percent: number) => void) {
  /**
   * 先確保 Django 端已經發下 CSRF cookie。
   * 這對 Django 的 CSRF middleware 是必要前置步驟，否則後續 POST 可能被擋掉。
   */
  await ensureCsrfCookie()

  return await new Promise<string>((resolve, reject) => {
    const payload = new FormData()
    payload.append('image', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/backend/community/uploads/images/')
    xhr.withCredentials = true

    /**
     * `xhr.upload.onprogress` 來自 XMLHttpRequest upload API。
     * 只有在瀏覽器知道總大小 `event.total` 時，才有辦法計算百分比。
     */
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) {
        return
      }
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }

    xhr.onload = () => {
      const raw = xhr.responseText || '{}'
      const data = JSON.parse(raw) as Partial<CommunityImageUploadPayload>

      if (xhr.status >= 200 && xhr.status < 300 && data.path) {
        onProgress?.(100)
        /**
         * Django 回傳的是後端資產路徑，前端統一轉成 `/backend-assets/*` proxy URL，
         * 避免 rich-text 內容直接暴露後端靜態路徑。
         */
        resolve(toBackendAssetUrl(data.path))
        return
      }

      reject(new Error(data.detail || '圖片上傳失敗'))
    }

    xhr.onerror = () => reject(new Error('圖片上傳失敗'))
    xhr.send(payload)
  })
}

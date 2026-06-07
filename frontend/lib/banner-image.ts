/**
 * Banner 圖片檢查 helper。
 *
 * 這支模組不直接上傳圖片，只負責：
 * 1. 檢查副檔名
 * 2. 檢查檔案大小
 * 3. 檢查圖片實際寬高
 * 4. 告訴呼叫端是否接近建議比例
 *
 * 呼叫位置通常是：
 * - 會員送出 Banner 申請頁
 * - 管理端審核或建立 Banner 的表單
 */
const MAX_BANNER_FILE_SIZE = 5 * 1024 * 1024
const ALLOWED_BANNER_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
const MAX_BANNER_WIDTH = 2240
const MAX_BANNER_HEIGHT = 840
const RECOMMENDED_BANNER_RATIO = MAX_BANNER_WIDTH / MAX_BANNER_HEIGHT
const RATIO_TOLERANCE = 0.015

/**
 * `type` 來自 TypeScript 型別系統。
 * 與 `interface` 類似，這裡用來描述 helper 回傳的結構。
 */
export type BannerImageInspection = {
  width: number
  height: number
  isRecommendedRatio: boolean
}

/**
 * 讀取圖片的實際像素尺寸。
 *
 * `Promise<{ width: number; height: number }>` 的意思：
 * - `Promise` 來自 JavaScript 非同步規範。
 * - `<...>` 是 TypeScript generic，表示這個 Promise 最後 resolve 的值長什麼樣。
 *
 * 這裡使用瀏覽器原生 `Image` 物件與 `URL.createObjectURL(...)`：
 * - `Image` 讓前端在不先上傳的情況下讀到圖片 metadata
 * - `createObjectURL` 讓本機檔案暫時變成可被 `<img>` 載入的 blob URL
 */
function readImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    const objectUrl = URL.createObjectURL(file)

    image.onload = () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight })
      URL.revokeObjectURL(objectUrl)
    }

    image.onerror = () => {
      reject(new Error('無法讀取圖片尺寸'))
      URL.revokeObjectURL(objectUrl)
    }

    image.src = objectUrl
  })
}

/**
 * 單純檢查圖片尺寸與比例，不做副檔名/大小驗證。
 *
 * `async function` 來自 JavaScript 非同步語法糖。
 * `await` 會等待 `readImageDimensions(...)` 的 Promise resolve 後再往下執行，
 * 讓這段看起來像同步流程，比直接 `.then(...)` 更容易讀。
 */
export async function inspectBannerImageFile(file: File): Promise<BannerImageInspection> {
  const { width, height } = await readImageDimensions(file)
  const ratio = width / height

  return {
    width,
    height,
    isRecommendedRatio: Math.abs(ratio - RECOMMENDED_BANNER_RATIO) <= RATIO_TOLERANCE,
  }
}

/**
 * 完整驗證 banner 圖片。
 *
 * 呼叫端通常在送出表單前先跑這支 helper：
 * - 驗證沒過：直接在前端顯示錯誤，避免無效檔案送到後端
 * - 驗證通過：再把檔案包進 `FormData` 上傳
 */
export async function validateBannerImageFile(file: File): Promise<BannerImageInspection> {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_BANNER_EXTENSIONS.includes(extension)) {
    throw new Error('Banner 圖片只接受 jpg、jpeg、png、webp')
  }
  if (file.size > MAX_BANNER_FILE_SIZE) {
    throw new Error('Banner 圖片大小不可超過 5 MB')
  }

  const inspection = await inspectBannerImageFile(file)
  if (inspection.width > MAX_BANNER_WIDTH || inspection.height > MAX_BANNER_HEIGHT) {
    throw new Error(`Banner 圖片尺寸不可超過 ${MAX_BANNER_WIDTH} x ${MAX_BANNER_HEIGHT} px`)
  }

  return inspection
}

/**
 * 純規則物件，方便 UI 直接顯示上傳限制，不必重複把常數寫死在頁面裡。
 */
export const bannerImageRules = {
  maxFileSizeMb: 5,
  width: MAX_BANNER_WIDTH,
  height: MAX_BANNER_HEIGHT,
  allowedExtensions: ALLOWED_BANNER_EXTENSIONS,
}

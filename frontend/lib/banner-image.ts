const MAX_BANNER_FILE_SIZE = 5 * 1024 * 1024
const ALLOWED_BANNER_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp']
const MAX_BANNER_WIDTH = 2240
const MAX_BANNER_HEIGHT = 840
const RECOMMENDED_BANNER_RATIO = MAX_BANNER_WIDTH / MAX_BANNER_HEIGHT
const RATIO_TOLERANCE = 0.015

export type BannerImageInspection = {
  width: number
  height: number
  isRecommendedRatio: boolean
}

function readImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    const objectUrl = URL.createObjectURL(file)

    image.onload = () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight })
      URL.revokeObjectURL(objectUrl)
    }

    image.onerror = () => {
      reject(new Error('無法讀取圖片尺寸。'))
      URL.revokeObjectURL(objectUrl)
    }

    image.src = objectUrl
  })
}

export async function inspectBannerImageFile(file: File): Promise<BannerImageInspection> {
  const { width, height } = await readImageDimensions(file)
  const ratio = width / height

  return {
    width,
    height,
    isRecommendedRatio: Math.abs(ratio - RECOMMENDED_BANNER_RATIO) <= RATIO_TOLERANCE,
  }
}

export async function validateBannerImageFile(file: File): Promise<BannerImageInspection> {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  if (!ALLOWED_BANNER_EXTENSIONS.includes(extension)) {
    throw new Error('Banner 圖片格式只接受 jpg、jpeg、png、webp。')
  }
  if (file.size > MAX_BANNER_FILE_SIZE) {
    throw new Error('Banner 圖片大小不得超過 5 MB。')
  }

  const inspection = await inspectBannerImageFile(file)
  if (inspection.width > MAX_BANNER_WIDTH || inspection.height > MAX_BANNER_HEIGHT) {
    throw new Error(`Banner 圖片尺寸不得超過 ${MAX_BANNER_WIDTH} x ${MAX_BANNER_HEIGHT} px。`)
  }

  return inspection
}

export const bannerImageRules = {
  maxFileSizeMb: 5,
  width: MAX_BANNER_WIDTH,
  height: MAX_BANNER_HEIGHT,
  allowedExtensions: ALLOWED_BANNER_EXTENSIONS,
}

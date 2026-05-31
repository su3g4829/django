'use client'

import { ensureCsrfCookie } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'

type CommunityImageUploadPayload = {
  path: string
  detail?: string
}

export async function uploadCommunityEditorImage(file: File, onProgress?: (percent: number) => void) {
  await ensureCsrfCookie()

  return await new Promise<string>((resolve, reject) => {
    const payload = new FormData()
    payload.append('image', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/backend/community/uploads/images/')
    xhr.withCredentials = true

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
        resolve(toBackendAssetUrl(data.path))
        return
      }

      reject(new Error(data.detail || '圖片上傳失敗。'))
    }

    xhr.onerror = () => reject(new Error('圖片上傳失敗。'))
    xhr.send(payload)
  })
}

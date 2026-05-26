'use client'

/**
 * `/index` 只是相容舊入口的轉址頁。
 * 這裡改用 client-side redirect，避免 Next.js 15 在 prerender
 * 純 redirect page 時觸發 clientReferenceManifest 錯誤。
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** 將舊的 `/index` 路徑導回真正首頁 `/`。 */
export default function IndexPage() {
  const router = useRouter()

  /**
   * 元件掛載後立即用 client router 轉址。
   * 這樣不依賴 server prerender redirect。
   */
  useEffect(() => {
    router.replace('/')
  }, [router])

  /** 轉址期間僅顯示簡單提示，避免白畫面。 */
  return <p className="text-muted">Redirecting to home...</p>
}

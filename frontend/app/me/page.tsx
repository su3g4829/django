'use client'

/**
 * `/me` 是會員中心入口轉址頁。
 * 改成 client-side redirect，避免 Next.js 15 prerender 純 redirect page 的問題。
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** 將 `/me` 導向真正的會員儀表板 `/me/dashboard`。 */
export default function MeRootPage() {
  const router = useRouter()

  /** 掛載後立即導向會員儀表板。 */
  useEffect(() => {
    router.replace('/me/dashboard')
  }, [router])

  /** 轉址期間顯示簡單提示。 */
  return <p className="text-muted">Redirecting to member dashboard...</p>
}

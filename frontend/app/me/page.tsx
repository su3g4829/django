'use client'

/**
 * `/me` 是會員中心入口轉址頁。
 * 改成 client-side redirect，避免 Next.js 15 prerender 純 redirect page 的問題。
 *
 * 來源：
 * - `useEffect` 來自 React
 * - `useRouter` 來自 `next/navigation`
 * - redirect 行為依賴 Next.js client navigation
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/** 將 `/me` 導向真正的會員儀表板 `/me/dashboard`。 */
export default function MeRootPage() {
  const router = useRouter()

  /**
   * 掛載後立即導向會員儀表板。
   *
   * 程式語法：
   * - `useEffect` 用來執行 render 之外的副作用
   * - `router.replace()` 會取代目前網址，不額外留下 `/me` 歷史紀錄
   */
  useEffect(() => {
    router.replace('/me/dashboard')
  }, [router])

  /** 轉址期間顯示簡單提示。 */
  return <p className="text-muted">Redirecting to member dashboard...</p>
}

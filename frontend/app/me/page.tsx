/**
 * 會員入口頁
 *
 * 功能：
 * - 將 `/me` 轉址到會員中心首頁 `/me/dashboard`
 */

import { redirect } from 'next/navigation'

/** 會員中心根路徑轉址頁。 */
export default function MeRootPage() {
  /** 純轉址頁，將 `/me` 統一導向會員中心首頁。 */
  redirect('/me/dashboard')
}

/**
 * `/index` 相容轉址頁
 *
 * 功能：
 * - 保留舊入口路徑
 * - 將 `/index` 重新導向真正的 Next.js 首頁 `/`
 */

import { redirect } from 'next/navigation'

/**
 * 舊首頁轉址元件。
 *
 * 早期曾使用 `/index` 作為首頁網址，目前統一改成 `/`，
 * 因此此頁面只負責相容性轉址。
 */
export default function IndexPage() {
  /** 純轉址頁，沒有實際畫面區塊。 */
  redirect('/')
}

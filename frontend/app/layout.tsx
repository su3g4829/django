/**
 * 全站共用 Layout
 *
 * 功能：
 * - 定義前端站台的 metadata
 * - 載入全站樣式
 * - 套用共用 Header
 * - 包住所有 `frontend/app/**/page.tsx` 頁面
 */

import type { Metadata } from 'next'

import { SiteHeader } from '@/components/site-header'

import './globals.css'

export const metadata: Metadata = {
  title: 'Store Frontend',
  description: 'Next.js frontend for the Django JSON-backed store',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  /** children 是目前路由頁面的實際內容。 */
  return (
    <html lang="zh-Hant">
      <body>
        <SiteHeader />
        <main className="page">
          <div className="container">{children}</div>
        </main>
      </body>
    </html>
  )
}

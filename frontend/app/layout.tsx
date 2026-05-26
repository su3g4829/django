/**
 * Next.js 全站根 Layout。
 *
 * 功能：
 * - 設定全站 metadata
 * - 載入共用樣式
 * - 掛上全站 Header
 * - 包住各頁面的主要內容區
 */

import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SiteHeader } from '@/components/site-header'

import './globals.css'

export const metadata: Metadata = {
  title: 'Store Frontend',
  description: 'Next.js frontend for the Django JSON-backed store',
}

export default function RootLayout({ children }: { children: ReactNode }) {
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

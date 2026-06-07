/**
 * Next.js 全站根 Layout。
 *
 * 功能：
 * - 設定全站 metadata
 * - 載入共用樣式
 * - 掛上全站 Header
 * - 包住各頁面的主要內容區
 *
 * 來源：
 * - `Metadata` 型別來自 `next`
 * - `ReactNode` 來自 React
 * - 這是 Next.js App Router 規範中的根 layout 檔案
 */

import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { SiteHeader } from '@/components/site-header'

import './globals.css'

export const metadata: Metadata = {
  title: 'Store Frontend',
  description: 'Next.js frontend for the Django JSON-backed store',
}

/**
 * RootLayout 會包住整個 frontend 所有頁面。
 *
 * 程式語法：
 * - `children` 是 layout 慣例參數，用來承接子頁面 JSX
 * - `<html>` / `<body>` 必須由根 layout 輸出
 */
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

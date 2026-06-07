'use client'

/**
 * rich-text 顯示元件。
 *
 * 這個元件的責任很單純：
 * - 接收後端或草稿儲存下來的 HTML 字串
 * - 先經過 `normalizeStoredRichText(...)` 清洗與路徑轉換
 * - 再用 `dangerouslySetInnerHTML` 輸出
 *
 * `dangerouslySetInnerHTML` 來自 React 規範，
 * 用來告訴 React「這裡不是一般 JSX 子節點，而是要直接塞原始 HTML」。
 * 因為這個 API 有 XSS 風險，所以前面一定要先做 sanitize。
 */
import { useMemo } from 'react'

import { normalizeStoredRichText } from '@/lib/rich-text'

type RichTextContentProps = {
  html: string
  className?: string
}

export function RichTextContent({ html, className = '' }: RichTextContentProps) {
  /**
   * `useMemo` 來自 React。
   * 用途不是「一定比較快」，而是避免每次 render 都重跑一遍 rich-text 正規化流程。
   *
   * 當依賴陣列 `[html]` 沒變時，React 會沿用上次計算好的結果。
   */
  const safeHtml = useMemo(() => normalizeStoredRichText(html), [html])

  if (!safeHtml) {
    return null
  }

  return <div className={className} dangerouslySetInnerHTML={{ __html: safeHtml }} />
}

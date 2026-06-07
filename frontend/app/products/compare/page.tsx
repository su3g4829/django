'use client'

/**
 * 商品比較頁。
 *
 * 功能：
 * - 讀取目前加入比較清單的商品
 * - 顯示品牌、分類、價格、顏色、尺寸等欄位
 * - 支援把單一商品從比較清單移除
 *
 * 來源：
 * - `useEffect` / `useState` 來自 React
 * - API 呼叫透過 `@/lib/api` 的 `apiFetch`
 * - 型別 `CompareListPayload` 來自 `@/lib/types`
 *
 * 主要 API：
 * - GET `/api/v1/products/compare/`
 * - POST `/api/v1/products/:slug/compare/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CompareListPayload } from '@/lib/types'

export default function ProductComparePage() {
  /** 比較清單主資料，直接對應後端 compare payload。 */
  const [data, setData] = useState<CompareListPayload | null>(null)
  /** 首次載入比較清單時顯示 skeleton / loading 文案。 */
  const [loading, setLoading] = useState(true)
  /** 任何 API 失敗都統一落在這個錯誤訊息欄位。 */
  const [error, setError] = useState('')
  /** 移除比較商品時避免重複點擊。 */
  const [submitting, setSubmitting] = useState(false)

  /**
   * 載入目前比較清單。
   *
   * 程式語法：
   * - `async` 讓函式內可使用 `await apiFetch(...)`
   * - `try / catch / finally` 分別處理成功、失敗與收尾 loading 狀態
   */
  async function loadCompare() {
    setLoading(true)
    try {
      const payload = await apiFetch<CompareListPayload>('/products/compare/')
      setData(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入商品比較資料失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  /**
   * `useEffect` 是 React 的副作用 hook。
   *
   * 這裡代表頁面第一次 mount 後再向後端抓比較資料，
   * 而不是在 render 階段直接發請求。
   */
  useEffect(() => {
    void loadCompare()
  }, [])

  /**
   * 將單一商品從比較清單移除。
   *
   * 用法：
   * - compare API 目前使用 POST 作為 toggle 行為
   * - 移除後再重新抓一次比較清單，保持表格內容同步
   */
  async function removeFromCompare(slug: string) {
    try {
      setSubmitting(true)
      await apiFetch(`/products/${slug}/compare/`, { method: 'POST' })
      await loadCompare()
    } catch (err) {
      setError(err instanceof Error ? err.message : '移除比較商品失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入商品比較資料中...</section>
  }

  return (
    <div className="stack">
      {/* 頁首說明本頁用途，讓使用者知道這裡在比較哪些欄位。 */}
      <section className="hero">
        <h1>商品比較</h1>
        <p className="muted">這一頁會整理你加入比較清單的商品，並列出主要規格與價格差異。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data?.items.length ? (
        <section className="card muted">目前沒有加入任何比較商品。</section>
      ) : (
        <section className="card stack">
          {/* 表格欄位固定，方便直接橫向比對商品資訊。 */}
          <table className="table">
            <thead>
              <tr>
                <th>商品</th>
                <th>品牌</th>
                <th>分類</th>
                <th>價格</th>
                <th>顏色</th>
                <th>尺寸</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.slug}>
                  <td>
                    <a href={`/products/${item.slug}`}>{item.name}</a>
                  </td>
                  <td>{item.brand}</td>
                  <td>{item.category}</td>
                  <td>{item.price_range_label ?? `$${item.price.toFixed(2)}`}</td>
                  <td>{item.color_options?.join(', ') || '-'}</td>
                  <td>{item.size_options?.join(', ') || '-'}</td>
                  <td>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => removeFromCompare(item.slug)} type="button">
                      移除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}

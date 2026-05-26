'use client'

/**
 * 商品比較頁
 *
 * 功能：
 * - 顯示目前加入比較清單的商品
 * - 提供移除比較項目的操作
 *
 * 主要 API：
 * - GET `/api/v1/products/compare/`
 * - POST `/api/v1/products/:slug/compare/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CompareListPayload } from '@/lib/types'

export default function ProductComparePage() {
  /** 比較清單資料。 */
  const [data, setData] = useState<CompareListPayload | null>(null)
  /** 首次載入比較清單時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 畫面上的錯誤訊息。 */
  const [error, setError] = useState('')
  /** 移除比較項目時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)

  /** 載入目前比較清單。 */
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

  useEffect(() => {
    loadCompare()
  }, [])

  /**
   * 從比較清單移除商品。
   *
   * slug:
   * - 商品 slug，用來指定要移除哪一個比較項目。
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
    return <section className="card">載入商品比較資料中…</section>
  }

  return (
    <div className="stack">
      {/* 頁首說明：交代這裡是商品比較頁。 */}
      <section className="hero">
        <h1>商品比較</h1>
        <p className="muted">這裡會顯示目前加入比較清單的商品，資料由 Django DRF compare API 提供。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data?.items.length ? (
        <section className="card muted">目前沒有加入任何比較商品。</section>
      ) : (
        <section className="card stack">
          {/* 比較表格：橫向對照品牌、分類、價格、顏色與尺寸。 */}
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
              {/* 每列是一個加入比較清單的商品。 */}
              {data.items.map((item) => (
                <tr key={item.slug}>
                  <td>
                    <a href={`/products/${item.slug}`}>{item.name}</a>
                  </td>
                  <td>{item.brand}</td>
                  <td>{item.category}</td>
                  <td>{item.price_range_label ?? `$${item.price.toFixed(2)}`}</td>
                  <td>{item.color_options?.join(', ') || '無'}</td>
                  <td>{item.size_options?.join(', ') || '無'}</td>
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

'use client'

/**
 * 賣家銷售報表頁
 *
 * 功能：
 * - 顯示銷售統計
 * - 支援日期篩選
 *
 * 主要 API：
 * - GET `/api/v1/me/sales/report/`
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { SalesReport } from '@/lib/types'

export default function SellerReportPage() {
  /** 賣家銷售報表資料。 */
  const [report, setReport] = useState<SalesReport | null>(null)
  /** 日期篩選條件。 */
  const [filters, setFilters] = useState({ date_from: '', date_to: '' })
  /** 初次載入報表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 載入銷售報表。
   *
   * nextFilters:
   * - 要送給後端的日期篩選條件；未傳入時會沿用目前 `filters` state。
   */
  async function loadReport(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<SalesReport>(`/me/sales/report/${toQueryString(nextFilters)}`)
      setReport(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入銷售報表失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadReport()
  }, [])

  return (
    <div className="stack">
      {/* 報表篩選區：依日期區間重新載入報表。 */}
      <section className="card stack">
        <h1>銷售報表</h1>
        <div className="grid grid-2">
          <label className="field">
            <span>開始日期</span>
            <input type="date" value={filters.date_from} onChange={(event) => setFilters((prev) => ({ ...prev, date_from: event.target.value }))} />
          </label>
          <label className="field">
            <span>結束日期</span>
            <input type="date" value={filters.date_to} onChange={(event) => setFilters((prev) => ({ ...prev, date_to: event.target.value }))} />
          </label>
        </div>
        <div className="row">
          {/* 重新查詢報表資料。 */}
          <button className="btn btn-secondary" onClick={() => loadReport(filters)} type="button">
            套用篩選
          </button>
        </div>
      </section>

      {error ? <div className="notice">{error}</div> : null}
      {loading ? (
        <section className="card">載入銷售報表中…</section>
      ) : !report ? null : (
        <>
          {/* 核心統計卡：訂單數、售出件數、營收。 */}
          <section className="grid grid-3">
            <div className="card stack">
              <span className="muted">訂單數</span>
              <strong>{report.order_count}</strong>
            </div>
            <div className="card stack">
              <span className="muted">售出件數</span>
              <strong>{report.units_sold}</strong>
            </div>
            <div className="card stack">
              <span className="muted">營收</span>
              <strong>${report.revenue}</strong>
            </div>
          </section>

          {/* 狀態統計：依履約狀態彙總訂單。 */}
          <section className="card stack">
            <h2>狀態統計</h2>
            <div className="row">
              <span className="badge">待處理 {report.status_counts.pending}</span>
              <span className="badge">已出貨 {report.status_counts.shipped}</span>
              <span className="badge">已完成 {report.status_counts.completed}</span>
            </div>
          </section>

          {/* 熱門商品排行：依售出件數與營收顯示前幾名商品。 */}
          <section className="card stack">
            <h2>熱門商品</h2>
            {!report.top_products.length ? (
              <div className="muted">目前沒有足夠資料產生熱門商品排行。</div>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>商品名稱</th>
                    <th>售出件數</th>
                    <th>營收</th>
                  </tr>
                </thead>
                <tbody>
                  {report.top_products.map((item) => (
                    <tr key={item.slug}>
                      <td>{item.name}</td>
                      <td>{item.qty}</td>
                      <td>${item.revenue}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  )
}

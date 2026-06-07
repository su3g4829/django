'use client'

/**
 * 賣家銷售報表頁。
 *
 * 功能：
 * - 顯示訂單數、銷售數量、營收
 * - 依日期區間過濾
 * - 顯示狀態統計與熱賣商品
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { SalesReport } from '@/lib/types'

export default function SellerReportPage() {
  const [report, setReport] = useState<SalesReport | null>(null)
  const [filters, setFilters] = useState({ date_from: '', date_to: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadReport(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<SalesReport>(`/me/sales/report/${toQueryString(nextFilters)}`)
      setReport(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入銷售報表失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadReport()
  }, [])

  return (
    <div className="stack">
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
          <button className="btn btn-secondary" onClick={() => void loadReport(filters)} type="button">
            套用篩選
          </button>
        </div>
      </section>

      {error ? <div className="notice">{error}</div> : null}
      {loading ? (
        <section className="card">載入銷售報表中...</section>
      ) : !report ? null : (
        <>
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

          <section className="card stack">
            <h2>狀態分佈</h2>
            <div className="row">
              <span className="badge">待出貨：{report.status_counts.pending}</span>
              <span className="badge">已出貨：{report.status_counts.shipped}</span>
              <span className="badge">已完成：{report.status_counts.completed}</span>
            </div>
          </section>

          <section className="card stack">
            <h2>熱門商品</h2>
            {!report.top_products.length ? (
              <div className="muted">目前沒有符合條件的熱門商品資料。</div>
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

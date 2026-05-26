'use client'

/**
 * 管理者訂單列表頁
 *
 * 功能：
 * - 顯示全站訂單
 * - 提供查詢與篩選
 *
 * 主要 API：
 * - GET `/api/v1/staff/orders/`
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

export default function AdminOrdersPage() {
  /** 管理端可見的訂單列表。 */
  const [items, setItems] = useState<Order[]>([])
  /** 訂單搜尋與篩選條件。 */
  const [filters, setFilters] = useState({
    q: '',
    date_from: '',
    date_to: '',
    status: '',
    service_status: '',
  })
  /** 初次載入列表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 載入管理端訂單列表。
   *
   * nextFilters:
   * - 要送給後端的查詢條件；未傳入時會沿用目前 `filters` state。
   */
  async function loadOrders(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<OrderListPayload>(`/staff/orders/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入管理端訂單失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  return (
    <section className="card stack">
      {/* 查詢與篩選列：關鍵字、日期、訂單狀態與售後狀態。 */}
      <h1>管理者訂單列表</h1>
      <div className="grid grid-3">
        <label className="field">
          <span>關鍵字</span>
          <input value={filters.q} onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))} />
        </label>
        <label className="field">
          <span>開始日期</span>
          <input type="date" value={filters.date_from} onChange={(event) => setFilters((prev) => ({ ...prev, date_from: event.target.value }))} />
        </label>
        <label className="field">
          <span>結束日期</span>
          <input type="date" value={filters.date_to} onChange={(event) => setFilters((prev) => ({ ...prev, date_to: event.target.value }))} />
        </label>
        <label className="field">
          <span>訂單狀態</span>
          <input value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))} />
        </label>
        <label className="field">
          <span>售後狀態</span>
          <input value={filters.service_status} onChange={(event) => setFilters((prev) => ({ ...prev, service_status: event.target.value }))} />
        </label>
      </div>
      <div className="row">
        {/* 套用篩選條件並重新查詢。 */}
        <button className="btn btn-secondary" onClick={() => loadOrders(filters)} type="button">
          套用篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">載入管理端訂單中…</div>
      ) : !items.length ? (
        <div className="muted">目前沒有符合條件的訂單。</div>
      ) : (
        <table className="table">
          {/* 表頭：訂單摘要與售後狀態。 */}
          <thead>
            <tr>
              <th>訂單編號</th>
              <th>買家</th>
              <th>建立時間</th>
              <th>訂單狀態</th>
              <th>售後狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {/* 每列可進一步查看管理端詳情頁。 */}
            {items.map((item) => (
              <tr key={item.id}>
                <td>#{item.id}</td>
                <td>{item.display_name}</td>
                <td>{item.created_at_display}</td>
                <td>{item.status_label ?? item.status}</td>
                <td>{item.service_request?.status_label ?? item.service_request?.status ?? '-'}</td>
                <td>
                  <a href={`/staff/orders/${item.id}`}>查看詳情</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

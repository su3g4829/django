'use client'

/**
 * 賣家訂單列表頁
 *
 * 功能：
 * - 顯示賣家可見訂單
 * - 支援日期篩選
 *
 * 主要 API：
 * - GET `/api/v1/me/sales/`
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

export default function SellerOrdersPage() {
  /** 賣家可見的訂單列表。 */
  const [items, setItems] = useState<Order[]>([])
  /** 日期篩選條件。 */
  const [filters, setFilters] = useState({ date_from: '', date_to: '' })
  /** 初次載入時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 載入賣家訂單列表。
   *
   * nextFilters:
   * - 要送給後端的篩選條件；未傳入時會沿用目前 `filters` state。
   */
  async function loadOrders(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<OrderListPayload>(`/me/sales/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入賣家訂單失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  return (
    <section className="card stack">
      {/* 日期篩選區：控制賣家訂單列表查詢範圍。 */}
      <h1>賣家訂單</h1>
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
        {/* 主動重新查詢訂單。 */}
        <button className="btn btn-secondary" onClick={() => loadOrders(filters)} type="button">
          套用篩選
        </button>
      </div>
      {error ? <div className="notice">{error}</div> : null}
      {loading ? (
        <div className="muted">載入賣家訂單中…</div>
      ) : !items.length ? (
        <div className="muted">目前沒有賣家訂單。</div>
      ) : (
        <table className="table">
          {/* 表頭：訂單摘要與賣家金額。 */}
          <thead>
            <tr>
              <th>訂單編號</th>
              <th>買家</th>
              <th>建立時間</th>
              <th>賣家狀態</th>
              <th>賣家金額</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {/* 每列都可進入單張賣家訂單詳情。 */}
            {items.map((item) => (
              <tr key={item.id}>
                <td>#{item.id}</td>
                <td>{item.display_name}</td>
                <td>{item.created_at_display}</td>
                <td>{item.seller_status_label ?? item.seller_status}</td>
                <td>${item.seller_totals?.subtotal ?? '0.00'}</td>
                <td>
                  <a href={`/me/sales/${item.id}`}>查看詳情</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

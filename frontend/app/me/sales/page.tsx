'use client'

/**
 * 賣家訂單列表頁。
 *
 * 功能：
 * - 顯示賣家自己的訂單
 * - 透過日期區間查詢
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

export default function SellerOrdersPage() {
  const [items, setItems] = useState<Order[]>([])
  const [filters, setFilters] = useState({ date_from: '', date_to: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  /**
   * `nextFilters = filters` 是 JavaScript 預設參數語法。
   *
   * 用法：
   * - 呼叫端若沒傳參數，就用目前 state 中的 `filters`
   * - 如果按下「套用篩選」前先組好一份臨時條件，也可以明確傳入
   */
  async function loadOrders(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<OrderListPayload>(`/me/sales/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入賣家訂單失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadOrders()
  }, [])

  return (
    <section className="card stack">
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
        <button className="btn btn-secondary" onClick={() => void loadOrders(filters)} type="button">
          套用篩選
        </button>
      </div>
      {error ? <div className="notice">{error}</div> : null}
      {loading ? (
        <div className="muted">載入賣家訂單中...</div>
      ) : !items.length ? (
        <div className="muted">目前沒有賣家訂單。</div>
      ) : (
        <table className="table">
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
            {items.map((item) => (
              <tr key={item.id}>
                <td>#{item.id}</td>
                <td>{item.display_name}</td>
                <td>{item.created_at_display}</td>
                <td>{item.seller_status_label ?? item.seller_status ?? '-'}</td>
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

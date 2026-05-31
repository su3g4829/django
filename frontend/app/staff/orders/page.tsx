'use client'

import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

type OrderSortKey = 'created_desc' | 'created_asc' | 'id_desc' | 'id_asc'

export default function AdminOrdersPage() {
  const [items, setItems] = useState<Order[]>([])
  const [filters, setFilters] = useState({
    q: '',
    date_from: '',
    date_to: '',
    status: '',
    service_status: '',
  })
  const [sortBy, setSortBy] = useState<OrderSortKey>('created_desc')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadOrders(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<OrderListPayload>(`/staff/orders/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取平台訂單失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadOrders()
  }, [])

  const sortedItems = useMemo(() => {
    const next = [...items]
    switch (sortBy) {
      case 'created_asc':
        next.sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')))
        break
      case 'id_asc':
        next.sort((a, b) => a.id - b.id)
        break
      case 'id_desc':
        next.sort((a, b) => b.id - a.id)
        break
      case 'created_desc':
      default:
        next.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
        break
    }
    return next
  }, [items, sortBy])

  return (
    <section className="card stack">
      <h1>平台訂單</h1>

      <div className="grid grid-3">
        <label className="field">
          <span>搜尋關鍵字</span>
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
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as OrderSortKey)}>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="id_desc">訂單編號：大到小</option>
            <option value="id_asc">訂單編號：小到大</option>
          </select>
        </label>
      </div>

      <div className="row">
        <button className="btn btn-secondary" onClick={() => void loadOrders(filters)} type="button">
          套用篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">正在讀取平台訂單...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的訂單。</div>
      ) : (
        <table className="table">
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
            {sortedItems.map((item) => (
              <tr key={item.id}>
                <td>#{item.id}</td>
                <td>{item.display_name}</td>
                <td>{item.created_at_display}</td>
                <td>{item.status_label ?? item.status}</td>
                <td>{item.service_request?.status_label ?? item.service_request?.status ?? '-'}</td>
                <td>
                  <a href={`/staff/orders/${item.id}`}>查看訂單</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 管理查詢條件 state
 * - 管理前端排序 state
 * - 根據操作重新抓訂單列表
 */

/**
 * 管理端訂單列表頁。
 *
 * 主要用途：
 * - 查看全站訂單
 * - 依關鍵字、日期、狀態與售後狀態篩選
 * - 進入單筆訂單詳情與售後審核頁
 *
 * 來源：
 * - `useEffect` / `useMemo` / `useState` 來自 React
 * - `toQueryString` 來自專案 API helper
 */

import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

type OrderSortKey = 'created_desc' | 'created_asc' | 'id_desc' | 'id_asc'

/**
 * staff 訂單列表頁。
 *
 * 這頁偏向營運查詢用途：
 * - 輸入多條件搜尋
 * - 切換不同排序視角
 * - 前往單筆訂單詳情頁
 *
 * 設計方式：
 * - 後端負責過濾
 * - 前端負責切換顯示排序
 */
export default function AdminOrdersPage() {
  // 管理端訂單頁同時持有篩選條件與排序條件，列表重抓後再做前端排序。
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

  /**
   * staff 訂單查詢主入口。
   *
   * `nextFilters = filters`
   * - 是 JavaScript 預設參數語法
   * - 若呼叫時沒傳入下一組篩選條件，就自動使用目前 state
   */
  async function loadOrders(nextFilters = filters) {
    // 列表查詢由後端過濾，前端只做補充排序與展示。
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

  /**
   * 後端先回傳符合篩選條件的結果，排序由前端調整視角。
   *
   * `useMemo`
   * - 讓排序結果成為衍生值
   * - 只有 `items` 或 `sortBy` 改變時才重算
   */
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

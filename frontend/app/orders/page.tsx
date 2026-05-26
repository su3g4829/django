'use client'

/**
 * 買家訂單列表頁
 *
 * 功能：
 * - 顯示目前登入者的訂單列表
 * - 提供進入訂單詳情頁的入口
 *
 * 主要 API：
 * - GET `/api/v1/me/orders/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { Order } from '@/lib/types'

type OrderListPayload = {
  items: Order[]
}

export default function OrdersPage() {
  /** 目前登入者的訂單列表。 */
  const [orders, setOrders] = useState<Order[]>([])
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')
  /** 初次載入訂單列表時的狀態。 */
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    /** 進頁後即載入訂單列表。 */
    setLoading(true)
    apiFetch<OrderListPayload>('/me/orders/')
      .then((payload) => {
        setOrders(payload.items)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <section className="card">載入訂單列表中…</section>
  }

  return (
    <section className="card stack">
      {/* 訂單列表主表格：摘要顯示每張訂單的編號、時間、狀態與總額。 */}
      <h1>我的訂單</h1>
      {error ? <div className="notice">{error}</div> : null}
      {!orders.length ? (
        <div className="muted">目前沒有任何訂單。</div>
      ) : (
        <table className="table">
          {/* 表頭：定義訂單摘要欄位。 */}
          <thead>
            <tr>
              <th>訂單編號</th>
              <th>建立時間</th>
              <th>狀態</th>
              <th>總額</th>
            </tr>
          </thead>
          <tbody>
            {/* 每列都可點進單張訂單詳情頁。 */}
            {orders.map((order) => (
              <tr key={order.id}>
                <td>
                  <a href={`/orders/${order.id}`}>#{order.id}</a>
                </td>
                <td>{order.created_at_display}</td>
                <td>{order.status_label ?? order.status}</td>
                <td>${order.totals?.total ?? '0.00'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

'use client'

/**
 * 買家訂單詳情頁
 *
 * 功能：
 * - 顯示單筆訂單內容
 * - 顯示物流、履約、售後資訊
 *
 * 主要 API：
 * - GET `/api/v1/me/orders/:id/`
 */

import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { Order } from '@/lib/types'

export default function OrderDetailPage({ params }: { params: { id: string } }) {
  /** 從動態路由解析出的訂單編號。 */
  const orderId = useMemo(() => params.id, [params.id])
  /** 單筆訂單詳情資料。 */
  const [order, setOrder] = useState<Order | null>(null)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')
  /** 初次載入詳情時的狀態。 */
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    /** 依訂單編號載入訂單詳情。 */
    setLoading(true)
    apiFetch<Order>(`/me/orders/${orderId}/`)
      .then((payload) => {
        setOrder(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [orderId])

  if (loading) {
    return <section className="card">載入訂單詳情中…</section>
  }

  return (
    <div className="stack">
      {/* 訂單基本資訊。 */}
      <section className="card stack">
        <h1>訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            {order.created_at_display} ｜ {order.status_label ?? order.status}
          </div>
        )}
      </section>

      {/* 訂單商品明細。 */}
      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這筆訂單沒有任何商品。</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>商品</th>
                <th>數量</th>
                <th>小計</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={`${item.id}-${item.slug}`}>
                  <td>{item.display_name ?? item.name}</td>
                  <td>{item.qty}</td>
                  <td>${item.line_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* 物流與履約資訊。 */}
      <section className="card stack">
        <h2>物流與履約</h2>
        {!order?.shipment_groups?.length ? (
          <div className="muted">目前沒有物流資訊。</div>
        ) : (
          order.shipment_groups.map((group) => (
            <div className="card" key={group.seller_username}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{group.seller_display_name}</strong>
                <span className="badge">{group.seller_status_label}</span>
              </div>
              <div className="muted">物流編號：{group.tracking_number || '尚未提供'}</div>
              <div className="muted">出貨備註：{group.shipping_note || '無'}</div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

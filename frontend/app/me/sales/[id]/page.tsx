'use client'

/**
 * 賣家訂單詳情頁
 *
 * 功能：
 * - 顯示單筆賣家訂單
 * - 查看物流與履約資訊
 *
 * 主要 API：
 * - GET `/api/v1/me/sales/:id/`
 */

import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { Order } from '@/lib/types'

export default function SellerOrderDetailPage({ params }: { params: { id: string } }) {
  /** 從動態路由解析出的訂單編號。 */
  const orderId = useMemo(() => params.id, [params.id])
  /** 單筆賣家訂單詳情資料。 */
  const [order, setOrder] = useState<Order | null>(null)
  /** 初次載入詳情時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    /** 依訂單編號載入賣家可見的訂單詳情。 */
    setLoading(true)
    apiFetch<Order>(`/me/sales/${orderId}/`)
      .then((payload) => {
        setOrder(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [orderId])

  if (loading) {
    return <section className="card">載入賣家訂單詳情中…</section>
  }

  return (
    <div className="stack">
      {/* 訂單基本資訊：訂單編號、建立時間與賣家履約狀態。 */}
      <section className="card stack">
        <h1>賣家訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            {order.created_at_display} ｜ {order.seller_status_label ?? order.seller_status}
          </div>
        )}
      </section>

      {/* 賣家可見的商品明細：僅顯示此賣家能處理的商品列。 */}
      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這筆訂單沒有任何商品。</div>
        ) : (
          <table className="table">
            {/* 表頭：商品、數量、狀態、物流與小計。 */}
            <thead>
              <tr>
                <th>商品</th>
                <th>數量</th>
                <th>狀態</th>
                <th>物流編號</th>
                <th>小計</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={`${item.id}-${item.slug}`}>
                  <td>{item.display_name ?? item.name}</td>
                  <td>{item.qty}</td>
                  <td>{item.seller_status_label ?? item.seller_status ?? '-'}</td>
                  <td>{item.tracking_number || '-'}</td>
                  <td>${item.line_total}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

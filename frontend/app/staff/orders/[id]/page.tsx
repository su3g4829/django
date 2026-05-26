'use client'

/**
 * 管理者訂單詳情頁
 *
 * 功能：
 * - 顯示單筆訂單內容
 * - 處理售後審核
 *
 * 主要 API：
 * - GET `/api/v1/staff/orders/:id/`
 * - POST `/api/v1/staff/orders/:id/service-review/`
 */

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { Order } from '@/lib/types'

export default function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>()
  /** 從動態路由解析出的訂單編號。 */
  const orderId = useMemo(() => params.id, [params.id])
  /** 訂單詳情資料。 */
  const [order, setOrder] = useState<Order | null>(null)
  /** 初次載入詳情時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 售後審核送出時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /** 載入單筆訂單詳情。 */
  async function loadDetail() {
    setLoading(true)
    try {
      const payload = await apiFetch<Order>(`/staff/orders/${orderId}/`)
      setOrder(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入訂單詳情失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDetail()
  }, [orderId])

  /**
   * 審核售後申請。
   *
   * approved:
   * - `true` 代表核准，`false` 代表駁回。
   */
  async function reviewServiceRequest(approved: boolean) {
    try {
      setSubmitting(true)
      const payload = await apiFetch<Order>(`/staff/orders/${orderId}/service-review/`, {
        method: 'POST',
        body: JSON.stringify({
          approved,
          note: approved ? 'Approved in Next.js admin page.' : 'Rejected in Next.js admin page.',
        }),
      })
      setOrder(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '審核售後申請失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入管理端訂單詳情中…</section>
  }

  return (
    <div className="stack">
      {/* 訂單基本資訊：顯示訂單編號、建立時間與整體狀態。 */}
      <section className="card stack">
        <h1>管理端訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            {order.created_at_display} ｜ {order.status_label ?? order.status}
          </div>
        )}
      </section>

      {/* 商品明細：列出此訂單所有購買項目。 */}
      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這筆訂單沒有任何商品。</div>
        ) : (
          <table className="table">
            {/* 表頭：商品名稱、數量與金額。 */}
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

      {/* 售後申請審核區：管理者可查看並處理退款/取消等申請。 */}
      <section className="card stack">
        <h2>售後申請</h2>
        {!order?.service_request ? (
          <div className="muted">目前沒有售後申請。</div>
        ) : (
          <>
            {/* 申請摘要：類型、狀態與備註。 */}
            <div className="muted">類型：{order.service_request.type_label ?? order.service_request.type ?? '-'}</div>
            <div className="muted">狀態：{order.service_request.status_label ?? order.service_request.status ?? '-'}</div>
            <div className="muted">備註：{order.service_request.note || '無'}</div>
            {order.service_request.is_pending ? (
              /* 待審時才顯示核准 / 駁回按鈕。 */
              <div className="row">
                <button className="btn" disabled={submitting} onClick={() => reviewServiceRequest(true)} type="button">
                  核准
                </button>
                <button className="btn btn-secondary" disabled={submitting} onClick={() => reviewServiceRequest(false)} type="button">
                  駁回
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 讀 route param
 * - client-side 抓 API
 * - 審核售後申請
 *
 * 所以必須在瀏覽器端執行。
 */

/**
 * 管理端訂單詳情頁。
 *
 * 這頁同時顯示：
 * - 訂單基本資料
 * - 金流 debug
 * - 售後申請審核操作
 *
 * 來源：
 * - `useParams` 來自 `next/navigation`
 * - `Promise.all` 來自 JavaScript Promise API
 */

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { NewebpayPaymentDebug, Order } from '@/lib/types'

export default function AdminOrderDetailPage() {
  const params = useParams<{ id: string }>()
  /**
   * `useMemo`
   * 來源：React。
   *
   * 用途：
   * - 把動態路由 id 收斂成穩定值
   * - 讓後續 effect 明確依賴 `orderId`
   */
  const orderId = useMemo(() => params.id, [params.id])

  const [order, setOrder] = useState<Order | null>(null)
  const [paymentDebug, setPaymentDebug] = useState<NewebpayPaymentDebug | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadDetail() {
    /**
     * 訂單詳情與 payment debug 併行抓取。
     *
     * `Promise.all([...])`
     * - 來源：JavaScript Promise API
     * - 用來同時等待多個非同步請求完成
     * - 比先抓訂單再抓 payment debug 更快
     */
    setLoading(true)
    try {
      const [orderPayload, debugPayload] = await Promise.all([
        apiFetch<Order>(`/staff/orders/${orderId}/`),
        apiFetch<NewebpayPaymentDebug>(`/staff/orders/${orderId}/payment-debug/`),
      ])
      setOrder(orderPayload)
      setPaymentDebug(debugPayload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入訂單資料失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDetail()
  }, [orderId])

  async function reviewServiceRequest(approved: boolean) {
    /**
     * 管理端可直接核准 / 拒絕售後申請。
     *
     * `approved: boolean`
     * - `boolean` 是 TypeScript 基本型別
     * - 用來明確表達這個 action 只有「通過」或「拒絕」兩種分支
     */
    try {
      setSubmitting(true)
      const payload = await apiFetch<Order>(`/staff/orders/${orderId}/service-review/`, {
        method: 'POST',
        body: JSON.stringify({
          approved,
          note: approved ? 'Approved in admin page.' : 'Rejected in admin page.',
        }),
      })
      setOrder(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '審核售後申請失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入後台訂單中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>後台訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <>
            <div className="muted">建立時間：{order.created_at_display ?? order.created_at}</div>
            <div className="muted">訂單狀態：{order.status_label ?? order.status}</div>
            <div className="muted">付款狀態：{order.payment_status_label ?? order.payment_status ?? '-'}</div>
            <div className="muted">配送方式：{order.shipping_method_label ?? order.shipping_method ?? '-'}</div>
          </>
        )}
      </section>

      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這張訂單沒有商品。</div>
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

      <section className="card stack">
        <h2>NewebPay Payment Debug</h2>
        {!paymentDebug ? (
          <div className="muted">目前沒有可顯示的付款 debug 資料。</div>
        ) : (
          <>
            <div className="muted">Gateway：{paymentDebug.runtime.gateway_url}</div>
            <div className="muted">Merchant ID：{paymentDebug.runtime.merchant_id || '-'}</div>
            <div className="muted">Notify URL：{paymentDebug.runtime.notify_url || '-'}</div>
            <div className="muted">Return URL：{paymentDebug.runtime.return_url || '-'}</div>
            <div className="muted">ClientBack URL：{paymentDebug.runtime.client_back_url || '-'}</div>

            {!paymentDebug.records.length ? (
              <div className="muted">這筆訂單尚未建立任何藍新付款資料。</div>
            ) : (
              paymentDebug.records.map((record) => (
                <div className="card stack" key={`${record.merchant_order_no}-${record.updated_at}`}>
                  <div>
                    <strong>{record.merchant_order_no}</strong>
                  </div>
                  <div className="muted">
                    狀態：{record.status_label} / 交易序號：{record.trade_no || '-'}
                  </div>
                  <div className="muted">
                    金額：{record.amount} {record.currency} / callback 次數：{record.callback_count}
                  </div>
                  <div className="muted">建立時間：{record.created_at}</div>
                  <div className="muted">最後更新：{record.updated_at}</div>
                  <details>
                    <summary>送出與接收原始資料</summary>
                    <pre>{JSON.stringify(record.raw_payload ?? {}, null, 2)}</pre>
                  </details>
                </div>
              ))
            )}
          </>
        )}
      </section>

      <section className="card stack">
        <h2>售後申請</h2>
        {!order?.service_request ? (
          <div className="muted">目前沒有售後申請。</div>
        ) : (
          <>
            <div className="muted">類型：{order.service_request.type_label ?? order.service_request.type ?? '-'}</div>
            <div className="muted">狀態：{order.service_request.status_label ?? order.service_request.status ?? '-'}</div>
            <div className="muted">備註：{order.service_request.note || '-'}</div>
            {order.service_request.is_pending ? (
              <div className="row">
                <button className="btn" disabled={submitting} onClick={() => reviewServiceRequest(true)} type="button">
                  通過
                </button>
                <button className="btn btn-secondary" disabled={submitting} onClick={() => reviewServiceRequest(false)} type="button">
                  拒絕
                </button>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { NewebpayPaymentRecord, NewebpaySandboxPaymentPrepared, Order } from '@/lib/types'

function submitExternalForm(actionUrl: string, method: string, fields: Record<string, string | number>) {
  const form = document.createElement('form')
  form.action = actionUrl
  form.method = method
  form.style.display = 'none'

  Object.entries(fields).forEach(([key, value]) => {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = key
    input.value = String(value)
    form.appendChild(input)
  })

  document.body.appendChild(form)
  form.submit()
}

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const orderId = useMemo(() => params.id, [params.id])

  const [order, setOrder] = useState<Order | null>(null)
  const [paymentRecord, setPaymentRecord] = useState<NewebpayPaymentRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [paymentSubmitting, setPaymentSubmitting] = useState(false)
  const [paymentError, setPaymentError] = useState('')
  const [completeSubmitting, setCompleteSubmitting] = useState(false)
  const [completeMessage, setCompleteMessage] = useState('')
  const [completeMessageType, setCompleteMessageType] = useState<'success' | 'error'>('success')

  async function loadOrder() {
    setLoading(true)
    try {
      const payload = await apiFetch<Order>(`/me/orders/${orderId}/`)
      setOrder(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入訂單失敗。')
    } finally {
      setLoading(false)
    }
  }

  async function loadPaymentRecord() {
    try {
      const payload = await apiFetch<NewebpayPaymentRecord>(`/me/orders/${orderId}/newebpay-payment/`)
      setPaymentRecord(payload)
    } catch {
      setPaymentRecord(null)
    }
  }

  useEffect(() => {
    void loadOrder()
    void loadPaymentRecord()
  }, [orderId])

  async function handlePreparePayment() {
    try {
      setPaymentSubmitting(true)
      setPaymentError('')
      const payload = await apiFetch<NewebpaySandboxPaymentPrepared>(`/me/orders/${orderId}/newebpay-payment/sandbox/`, {
        method: 'POST',
        body: JSON.stringify({}),
      })
      submitExternalForm(payload.gateway_url, payload.form_method, payload.form_fields)
    } catch (err) {
      setPaymentError(err instanceof Error ? err.message : '建立付款資料失敗。')
    } finally {
      setPaymentSubmitting(false)
    }
  }

  async function handleCompleteOrder() {
    setCompleteSubmitting(true)
    setCompleteMessage('')
    try {
      const payload = await apiFetch<Order>(`/me/orders/${orderId}/complete/`, { method: 'POST' })
      setOrder(payload)
      setCompleteMessageType('success')
      setCompleteMessage('訂單已完成。')
    } catch (err) {
      setCompleteMessageType('error')
      setCompleteMessage(err instanceof Error ? err.message : '完成訂單失敗。')
    } finally {
      setCompleteSubmitting(false)
    }
  }

  const paymentCallbackStatus = searchParams.get('payment_callback')
  const paymentTradeStatus = searchParams.get('trade_status')
  const paymentMerchantOrderNo = searchParams.get('merchant_order_no')

  const canStartPayment = useMemo(() => {
    if (!order) {
      return false
    }
    if (order.status === 'cancelled' || order.status === 'refunded') {
      return false
    }
    if (paymentRecord?.status === 'paid') {
      return false
    }
    if (order.items?.length && order.items.every((item) => item.seller_status === 'completed')) {
      return false
    }
    return true
  }, [order, paymentRecord])

  if (loading) {
    return <section className="card">載入訂單中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <>
            <div className="muted">建立時間：{order.created_at_display ?? order.created_at} / 訂單狀態：{order.status_label ?? order.status}</div>
            <div className="muted">
              配送方式：{order.shipping_method_label ?? order.shipping_method ?? '-'} / 付款方式：{order.payment_method_label ?? order.payment_method ?? '-'}
            </div>
          </>
        )}
      </section>

      {paymentCallbackStatus ? (
        <section className="card stack">
          <h2>付款回傳結果</h2>
          <div className={paymentCallbackStatus === 'success' ? 'notice success' : 'notice'}>
            payment_callback={paymentCallbackStatus}
            {paymentTradeStatus ? ` / trade_status=${paymentTradeStatus}` : ''}
            {paymentMerchantOrderNo ? ` / merchant_order_no=${paymentMerchantOrderNo}` : ''}
          </div>
        </section>
      ) : null}

      <div className="grid grid-2">
        <section className="card stack">
          <h2>{order?.is_convenience_store_shipping ? '取貨資訊' : '收件資訊'}</h2>
          {order?.is_convenience_store_shipping ? (
            order.pickup_store_name ? (
              <>
                <div>
                  {order.pickup_store_brand_label ?? order.pickup_store_brand} / {order.pickup_store_name}
                </div>
                <div className="muted">門市代碼：{order.pickup_store_code || '-'}</div>
                <div className="muted">門市地址：{order.pickup_store_address || '-'}</div>
              </>
            ) : (
              <div className="muted">尚未收到藍新回傳的超商門市資料。</div>
            )
          ) : order?.shipping_address ? (
            <>
              <div>收件人：{order.shipping_address.recipient}</div>
              <div className="muted">電話：{order.shipping_address.phone}</div>
              <div className="muted">
                {order.shipping_address.postal_code ? `${order.shipping_address.postal_code} ` : ''}
                {order.shipping_address.city}
                {order.shipping_address.district}
                {order.shipping_address.address_line}
              </div>
            </>
          ) : (
            <div className="muted">沒有可顯示的配送資料。</div>
          )}

          {order?.buyer_note ? (
            <div className="card stack">
              <strong>訂單備註</strong>
              <div className="muted">{order.buyer_note}</div>
            </div>
          ) : null}
        </section>

        <section className="card stack">
          <h2>付款資訊</h2>
          <div className="muted">付款狀態：{paymentRecord?.status_label ?? order?.payment_status_label ?? '尚未建立付款單'}</div>
          <div className="muted">付款方式：{paymentRecord ? order?.payment_method_label ?? order?.payment_method ?? '-' : '藍新支付'}</div>
          <div className="muted">商店訂單編號：{paymentRecord?.merchant_order_no || '-'}</div>
          <div className="muted">藍新交易序號：{paymentRecord?.trade_no || order?.payment_trade_no || '-'}</div>
          {paymentRecord?.updated_at ? <div className="muted">最後更新：{paymentRecord.updated_at}</div> : null}
          {paymentError ? <div className="notice">{paymentError}</div> : null}
          <button className="btn-primary" disabled={!canStartPayment || paymentSubmitting} onClick={handlePreparePayment} type="button">
            {paymentSubmitting ? '前往付款中...' : paymentRecord ? '重新前往付款' : '前往藍新付款'}
          </button>
          {!canStartPayment ? <div className="muted">這筆訂單目前不可再建立新的付款單。</div> : null}
        </section>
      </div>

      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這張訂單沒有商品資料。</div>
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
        <h2>出貨分組</h2>
        {!order?.shipment_groups?.length ? (
          <div className="muted">目前沒有出貨分組資料。</div>
        ) : (
          order.shipment_groups.map((group) => (
            <div className="card stack" key={group.seller_username}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{group.seller_display_name}</strong>
                <span className="badge">{group.seller_status_label}</span>
              </div>
              <div className="muted">物流單號：{group.tracking_number || '尚未建立'}</div>
              <div className="muted">出貨備註：{group.shipping_note || '無'}</div>
            </div>
          ))
        )}
      </section>

      {order?.can_confirm_completion ? (
        <section className="card stack">
          <h2>完成訂單</h2>
          <div className="muted">賣家已經標記出貨後，你可以在這裡完成訂單。</div>
          {completeMessage ? <div className={completeMessageType === 'success' ? 'notice success' : 'notice'}>{completeMessage}</div> : null}
          <button className="btn-primary" disabled={completeSubmitting} onClick={handleCompleteOrder} type="button">
            {completeSubmitting ? '處理中...' : '完成訂單'}
          </button>
        </section>
      ) : null}
    </div>
  )
}

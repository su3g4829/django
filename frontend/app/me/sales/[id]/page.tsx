'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { Order } from '@/lib/types'

type SellerFulfillmentFormState = {
  seller_status: string
  tracking_number: string
  shipping_note: string
}

const INITIAL_FULFILLMENT_FORM: SellerFulfillmentFormState = {
  seller_status: 'shipped',
  tracking_number: '',
  shipping_note: '',
}

export default function SellerOrderDetailPage() {
  const params = useParams<{ id: string }>()
  const orderId = useMemo(() => params.id, [params.id])

  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [fulfillmentForm, setFulfillmentForm] = useState<SellerFulfillmentFormState>(INITIAL_FULFILLMENT_FORM)
  const [fulfillmentSubmitting, setFulfillmentSubmitting] = useState(false)
  const [fulfillmentMessage, setFulfillmentMessage] = useState('')
  const [fulfillmentMessageType, setFulfillmentMessageType] = useState<'success' | 'error'>('success')

  useEffect(() => {
    setLoading(true)
    apiFetch<Order>(`/me/sales/${orderId}/`)
      .then((payload) => {
        setOrder(payload)
        setFulfillmentForm({
          seller_status: payload.seller_status ?? 'shipped',
          tracking_number: payload.tracking_number ?? '',
          shipping_note: payload.shipping_note ?? '',
        })
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [orderId])

  function updateFulfillmentForm<K extends keyof SellerFulfillmentFormState>(field: K, value: SellerFulfillmentFormState[K]) {
    setFulfillmentForm((current) => ({ ...current, [field]: value }))
  }

  async function handleUpdateFulfillment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFulfillmentSubmitting(true)
    setFulfillmentMessage('')
    try {
      const payload = await apiFetch<Order>(`/me/sales/${orderId}/update/`, {
        method: 'POST',
        body: JSON.stringify(fulfillmentForm),
      })
      setOrder(payload)
      setFulfillmentForm({
        seller_status: payload.seller_status ?? fulfillmentForm.seller_status,
        tracking_number: payload.tracking_number ?? '',
        shipping_note: payload.shipping_note ?? '',
      })
      setFulfillmentMessageType('success')
      if ((payload.seller_status ?? fulfillmentForm.seller_status) === 'completed') {
        setFulfillmentMessage('已直接結案。')
      } else if ((payload.seller_status ?? fulfillmentForm.seller_status) === 'pending_shipment') {
        setFulfillmentMessage('已更新為待出貨。')
      } else {
        setFulfillmentMessage('已標記為已出貨，買家現在可在訂單頁完成訂單。')
      }
    } catch (err) {
      setFulfillmentMessageType('error')
      setFulfillmentMessage(err instanceof Error ? err.message : '更新出貨狀態失敗。')
    } finally {
      setFulfillmentSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入賣家訂單中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>賣家訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            建立時間：{order.created_at_display ?? order.created_at} / 目前狀態：
            {order.seller_status_label ?? order.seller_status ?? order.status_label ?? order.status}
          </div>
        )}
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>超商取貨資訊</h2>
          {order?.pickup_store_name ? (
            <div className="card stack">
              <strong>門市資料</strong>
              <div>
                {order.pickup_store_brand_label ?? order.pickup_store_brand} / {order.pickup_store_name}
              </div>
              <div className="muted">門市代碼：{order.pickup_store_code || '-'}</div>
              <div className="muted">門市地址：{order.pickup_store_address || '-'}</div>
            </div>
          ) : (
            <div className="muted">這張訂單沒有超商門市資訊。</div>
          )}
        </section>

        <section className="card stack">
          <h2>收件資訊</h2>
          {order?.shipping_address ? (
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
            <div className="muted">這張訂單沒有宅配地址。</div>
          )}
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
                <th>賣家狀態</th>
                <th>物流單號</th>
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

      <section className="card stack">
        <h2>出貨操作</h2>
        <div className="muted">
          這裡可以先標記已出貨，買家端就會出現「完成訂單」按鈕。
          如果只是 sandbox 測試，也可以直接把賣家狀態改成已完成。
        </div>
        {fulfillmentMessage ? (
          <div className={fulfillmentMessageType === 'success' ? 'notice success' : 'notice'}>{fulfillmentMessage}</div>
        ) : null}
        <form className="stack" onSubmit={handleUpdateFulfillment}>
          <label className="stack">
            <span>賣家履約狀態</span>
            <select
              value={fulfillmentForm.seller_status}
              onChange={(event) => updateFulfillmentForm('seller_status', event.target.value)}
            >
              <option value="pending_shipment">待出貨</option>
              <option value="shipped">已出貨</option>
              <option value="completed">已完成（測試用）</option>
            </select>
          </label>
          <label className="stack">
            <span>物流單號</span>
            <input
              placeholder="TW123456789"
              value={fulfillmentForm.tracking_number}
              onChange={(event) => updateFulfillmentForm('tracking_number', event.target.value)}
            />
          </label>
          <label className="stack">
            <span>出貨備註</span>
            <textarea
              placeholder="例如：已包裝完成，今晚交寄。"
              rows={3}
              value={fulfillmentForm.shipping_note}
              onChange={(event) => updateFulfillmentForm('shipping_note', event.target.value)}
            />
          </label>
          <button className="btn-primary" disabled={fulfillmentSubmitting} type="submit">
            {fulfillmentSubmitting ? '儲存中...' : '儲存出貨狀態'}
          </button>
        </form>
        {order?.shipped_at_display ? <div className="muted">出貨時間：{order.shipped_at_display}</div> : null}
        {order?.completed_at_display ? <div className="muted">完成時間：{order.completed_at_display}</div> : null}
      </section>
    </div>
  )
}

'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { NewebpayPaymentRecord, NewebpaySandboxPaymentPrepared, NewebpaySandboxPaymentSummary, Order } from '@/lib/types'

type SandboxPaymentFormState = {
  item_desc_override: string
  email: string
  notify_url: string
  return_url: string
  client_back_url: string
}

const INITIAL_PAYMENT_FORM: SandboxPaymentFormState = {
  item_desc_override: '',
  email: '',
  notify_url: '',
  return_url: '',
  client_back_url: '',
}

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const orderId = useMemo(() => params.id, [params.id])

  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [paymentSummary, setPaymentSummary] = useState<NewebpaySandboxPaymentSummary | null>(null)
  const [paymentSummaryLoading, setPaymentSummaryLoading] = useState(true)
  const [paymentPrepared, setPaymentPrepared] = useState<NewebpaySandboxPaymentPrepared | null>(null)
  const [paymentRecord, setPaymentRecord] = useState<NewebpayPaymentRecord | null>(null)
  const [paymentForm, setPaymentForm] = useState<SandboxPaymentFormState>(INITIAL_PAYMENT_FORM)
  const [paymentSubmitting, setPaymentSubmitting] = useState(false)
  const [paymentError, setPaymentError] = useState('')

  useEffect(() => {
    setLoading(true)
    apiFetch<Order>(`/me/orders/${orderId}/`)
      .then((payload) => {
        setOrder(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [orderId])

  useEffect(() => {
    setPaymentSummaryLoading(true)
    apiFetch<NewebpaySandboxPaymentSummary>(`/me/orders/${orderId}/newebpay-payment/sandbox/`)
      .then((payload) => {
        setPaymentSummary(payload)
        setPaymentForm((current) => ({
          ...current,
          notify_url: current.notify_url || payload.notify_url || '',
          return_url: current.return_url || payload.return_url || '',
          client_back_url: current.client_back_url || payload.client_back_url || '',
        }))
        setPaymentError('')
      })
      .catch((err: Error) => setPaymentError(err.message))
      .finally(() => setPaymentSummaryLoading(false))
  }, [orderId])

  useEffect(() => {
    apiFetch<NewebpayPaymentRecord>(`/me/orders/${orderId}/newebpay-payment/`)
      .then((payload) => setPaymentRecord(payload))
      .catch(() => setPaymentRecord(null))
  }, [orderId])

  function updatePaymentForm<K extends keyof SandboxPaymentFormState>(field: K, value: SandboxPaymentFormState[K]) {
    setPaymentForm((current) => ({ ...current, [field]: value }))
  }

  async function handlePreparePayment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPaymentSubmitting(true)
    setPaymentError('')

    try {
      const payload = await apiFetch<NewebpaySandboxPaymentPrepared>(`/me/orders/${orderId}/newebpay-payment/sandbox/`, {
        method: 'POST',
        body: JSON.stringify(paymentForm),
      })
      setPaymentPrepared(payload)
      setPaymentRecord(null)
    } catch (err) {
      setPaymentPrepared(null)
      setPaymentError(err instanceof Error ? err.message : '建立 NewebPay sandbox payload 失敗。')
    } finally {
      setPaymentSubmitting(false)
    }
  }

  const paymentCallbackStatus = searchParams.get('payment_callback')
  const paymentTradeStatus = searchParams.get('trade_status')
  const paymentMerchantOrderNo = searchParams.get('merchant_order_no')

  if (loading) {
    return <section className="card">讀取訂單中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <>
            <div className="muted">建立時間：{order.created_at_display ?? order.created_at} / 狀態：{order.status_label ?? order.status}</div>
            <div className="muted">
              配送方式：{order.shipping_method_label ?? order.shipping_method ?? '-'} / 付款方式：
              {order.payment_method_label ?? order.payment_method ?? '-'}
            </div>
          </>
        )}
      </section>

      {paymentCallbackStatus ? (
        <section className="card stack">
          <h2>支付回傳結果</h2>
          <div className={paymentCallbackStatus === 'success' ? 'notice success' : 'notice'}>
            payment_callback={paymentCallbackStatus}
            {paymentTradeStatus ? ` / trade_status=${paymentTradeStatus}` : ''}
            {paymentMerchantOrderNo ? ` / merchant_order_no=${paymentMerchantOrderNo}` : ''}
          </div>
        </section>
      ) : null}

      <div className="grid grid-2">
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
            <div className="muted">沒有收件地址資料。</div>
          )}

          {order?.pickup_store_name ? (
            <div className="card stack">
              <strong>超商取貨門市</strong>
              <div>
                {order.pickup_store_brand_label ?? order.pickup_store_brand} / {order.pickup_store_name}
              </div>
              <div className="muted">門市代碼：{order.pickup_store_code || '-'}</div>
              <div className="muted">門市地址：{order.pickup_store_address || '-'}</div>
            </div>
          ) : null}

          {order?.buyer_note ? (
            <div className="card stack">
              <strong>買家備註</strong>
              <div className="muted">{order.buyer_note}</div>
            </div>
          ) : null}
        </section>

        <section className="card stack">
          <h2>金額資訊</h2>
          <div className="muted">小計：{order?.totals?.subtotal ?? '0.00'}</div>
          <div className="muted">運費：{order?.totals?.shipping ?? '0.00'}</div>
          <div className="muted">折扣：{order?.totals?.discount ?? '0.00'}</div>
          <div>
            <strong>總計：{order?.totals?.total ?? '0.00'}</strong>
          </div>
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
                <th>金額</th>
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

      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>NewebPay Sandbox 支付</h2>
          <span className="badge">Buyer Test</span>
        </div>
        <div className="muted">這裡會建立藍新支付 MPG sandbox form payload，方便測試支付流程。</div>

        {paymentError ? <div className="notice">{paymentError}</div> : null}
        {paymentSummaryLoading ? (
          <div className="muted">讀取支付設定中...</div>
        ) : !paymentSummary ? (
          <div className="muted">目前沒有可用的支付設定。</div>
        ) : (
          <>
            <div className="stack">
              <div>
                <strong>設定狀態：</strong>
                {paymentSummary.configured ? '已完成' : '未完成'}
              </div>
              <div>
                <strong>Gateway：</strong>
                {paymentSummary.gateway_url}
              </div>
              <div>
                <strong>Merchant ID：</strong>
                {paymentSummary.merchant_id || '未設定'}
              </div>
              <div>
                <strong>加密套件：</strong>
                {paymentSummary.has_crypto_dependency ? '可用' : '缺少 pycryptodome'}
              </div>
              {paymentSummary.notify_url ? <div className="muted">Notify URL：{paymentSummary.notify_url}</div> : null}
              {paymentSummary.return_url ? <div className="muted">Return URL：{paymentSummary.return_url}</div> : null}
              {paymentSummary.client_back_url ? <div className="muted">ClientBack URL：{paymentSummary.client_back_url}</div> : null}
              {paymentSummary.missing_settings?.length ? (
                <div className="notice">缺少設定：{paymentSummary.missing_settings.join(', ')}</div>
              ) : null}
            </div>

            <form className="stack" onSubmit={handlePreparePayment}>
              <label className="stack">
                <span>商品描述覆寫</span>
                <input
                  placeholder="可選填，用來覆蓋訂單商品描述"
                  value={paymentForm.item_desc_override}
                  onChange={(event) => updatePaymentForm('item_desc_override', event.target.value)}
                />
              </label>
              <label className="stack">
                <span>Email</span>
                <input
                  placeholder="buyer@example.com"
                  type="email"
                  value={paymentForm.email}
                  onChange={(event) => updatePaymentForm('email', event.target.value)}
                />
              </label>
              <label className="stack">
                <span>Notify URL 覆寫</span>
                <input
                  placeholder="可選填，用來覆蓋後端回調網址"
                  value={paymentForm.notify_url}
                  onChange={(event) => updatePaymentForm('notify_url', event.target.value)}
                />
              </label>
              <label className="stack">
                <span>Return URL 覆寫</span>
                <input
                  placeholder="可選填，用來覆蓋付款完成返回網址"
                  value={paymentForm.return_url}
                  onChange={(event) => updatePaymentForm('return_url', event.target.value)}
                />
              </label>
              <label className="stack">
                <span>ClientBack URL 覆寫</span>
                <input
                  placeholder="可選填，用來覆蓋使用者返回網址"
                  value={paymentForm.client_back_url}
                  onChange={(event) => updatePaymentForm('client_back_url', event.target.value)}
                />
              </label>
              <button className="btn-primary" disabled={paymentSubmitting} type="submit">
                {paymentSubmitting ? '建立中...' : '建立 Sandbox Payload'}
              </button>
            </form>

            {paymentPrepared ? (
              <div className="stack">
                <div>
                  <strong>商店訂單編號：</strong>
                  {paymentPrepared.merchant_order_no}
                </div>
                <div>
                  <strong>Gateway URL：</strong>
                  {paymentPrepared.gateway_url}
                </div>
                <div className="stack">
                  <strong>Form Fields</strong>
                  <pre>{JSON.stringify(paymentPrepared.form_fields, null, 2)}</pre>
                </div>
                <div className="stack">
                  <strong>TradeInfo Params</strong>
                  <pre>{JSON.stringify(paymentPrepared.trade_info_params, null, 2)}</pre>
                </div>
                <form action={paymentPrepared.gateway_url} className="stack" method={paymentPrepared.form_method} target="_blank">
                  {Object.entries(paymentPrepared.form_fields).map(([key, value]) => (
                    <input key={key} name={key} type="hidden" value={String(value)} />
                  ))}
                  <button className="btn-primary" type="submit">
                    開啟 Sandbox 付款頁
                  </button>
                </form>
              </div>
            ) : null}

            {paymentRecord ? (
              <div className="card stack">
                <strong>最新支付紀錄</strong>
                <div>模式：{paymentRecord.mode}</div>
                <div>狀態：{paymentRecord.status_label}</div>
                <div>商店訂單編號：{paymentRecord.merchant_order_no || '-'}</div>
                <div>交易編號：{paymentRecord.trade_no || '-'}</div>
                <div>金額：{paymentRecord.amount} {paymentRecord.currency}</div>
                <div>回調次數：{paymentRecord.callback_count}</div>
                <div className="muted">建立時間：{paymentRecord.created_at}</div>
                <div className="muted">更新時間：{paymentRecord.updated_at}</div>
                {paymentRecord.paid_at ? <div className="muted">付款時間：{paymentRecord.paid_at}</div> : null}
                {paymentRecord.raw_payload ? (
                  <details>
                    <summary>查看原始回傳</summary>
                    <pre>{JSON.stringify(paymentRecord.raw_payload, null, 2)}</pre>
                  </details>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

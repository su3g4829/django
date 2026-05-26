'use client'

/**
 * 買家訂單明細頁。
 *
 * 功能：
 * - 顯示買家可見的訂單資訊、商品明細、出貨分組
 * - 提供藍新支付 sandbox 測試區，確認後端設定與 form payload
 *
 * 對應 API：
 * - GET `/api/v1/me/orders/:id/`
 * - GET `/api/v1/me/orders/:id/newebpay-payment/sandbox/`
 * - POST `/api/v1/me/orders/:id/newebpay-payment/sandbox/`
 */

import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type {
  NewebpaySandboxPaymentPrepared,
  NewebpaySandboxPaymentSummary,
  Order,
} from '@/lib/types'

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

export default function OrderDetailPage({ params }: { params: { id: string } }) {
  /** 目前瀏覽中的訂單 ID。 */
  const orderId = useMemo(() => params.id, [params.id])
  /** 訂單明細資料。 */
  const [order, setOrder] = useState<Order | null>(null)
  /** 主訂單區的錯誤訊息。 */
  const [error, setError] = useState('')
  /** 主訂單區載入狀態。 */
  const [loading, setLoading] = useState(true)

  /** 藍新支付 sandbox 設定摘要。 */
  const [paymentSummary, setPaymentSummary] = useState<NewebpaySandboxPaymentSummary | null>(null)
  /** 藍新支付 sandbox form payload。 */
  const [paymentPrepared, setPaymentPrepared] = useState<NewebpaySandboxPaymentPrepared | null>(null)
  /** 藍新支付測試表單欄位。 */
  const [paymentForm, setPaymentForm] = useState<SandboxPaymentFormState>(INITIAL_PAYMENT_FORM)
  /** 支付 sandbox 區塊錯誤訊息。 */
  const [paymentError, setPaymentError] = useState('')
  /** 支付 sandbox 設定摘要載入狀態。 */
  const [paymentSummaryLoading, setPaymentSummaryLoading] = useState(true)
  /** 支付 sandbox 建立 payload 送出中狀態。 */
  const [paymentSubmitting, setPaymentSubmitting] = useState(false)

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
        setPaymentError('')
      })
      .catch((err: Error) => setPaymentError(err.message))
      .finally(() => setPaymentSummaryLoading(false))
  }, [orderId])

  /**
   * 更新支付 sandbox 表單欄位。
   *
   * field:
   * - 要更新的欄位名稱
   *
   * value:
   * - 使用者輸入的新值
   */
  function updatePaymentForm(field: keyof SandboxPaymentFormState, value: string) {
    setPaymentForm((current) => ({ ...current, [field]: value }))
  }

  /**
   * 呼叫後端建立藍新支付 sandbox form payload。
   *
   * event:
   * - 原生表單送出事件，用於阻止瀏覽器直接重整頁面
   */
  async function handlePreparePayment(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPaymentSubmitting(true)
    setPaymentError('')

    try {
      const payload = await apiFetch<NewebpaySandboxPaymentPrepared>(
        `/me/orders/${orderId}/newebpay-payment/sandbox/`,
        {
          method: 'POST',
          body: JSON.stringify(paymentForm),
        },
      )
      setPaymentPrepared(payload)
    } catch (err) {
      setPaymentError(err instanceof Error ? err.message : '建立藍新支付測試資料失敗。')
      setPaymentPrepared(null)
    } finally {
      setPaymentSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入訂單明細中…</section>
  }

  return (
    <div className="stack">
      {/* 訂單標題與基本狀態。 */}
      <section className="card stack">
        <h1>訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            {order.created_at_display} ・ {order.status_label ?? order.status}
          </div>
        )}
      </section>

      {/* 訂單商品明細表。 */}
      <section className="card stack">
        <h2>商品明細</h2>
        {!order?.items?.length ? (
          <div className="muted">這筆訂單目前沒有商品資料。</div>
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

      {/* 賣家出貨與追蹤資訊分組。 */}
      <section className="card stack">
        <h2>出貨資訊</h2>
        {!order?.shipment_groups?.length ? (
          <div className="muted">目前尚無出貨分組資料。</div>
        ) : (
          order.shipment_groups.map((group) => (
            <div className="card" key={group.seller_username}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{group.seller_display_name}</strong>
                <span className="badge">{group.seller_status_label}</span>
              </div>
              <div className="muted">物流單號：{group.tracking_number || '尚未提供'}</div>
              <div className="muted">出貨備註：{group.shipping_note || '無'}</div>
            </div>
          ))
        )}
      </section>

      {/* 藍新支付 sandbox 設定摘要與測試表單。 */}
      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>藍新支付 Sandbox 測試</h2>
          <span className="badge">Buyer Test</span>
        </div>
        <div className="muted">
          這一段只用來測試後端 sandbox form payload 是否正確建立，不會直接在前端送出到藍新。
        </div>
        {paymentError ? <div className="notice">{paymentError}</div> : null}
        {paymentSummaryLoading ? (
          <div className="muted">載入藍新支付設定中…</div>
        ) : !paymentSummary ? (
          <div className="muted">目前無法取得藍新支付設定摘要。</div>
        ) : (
          <>
            <div className="stack">
              <div>
                <strong>設定狀態：</strong>
                {paymentSummary.configured ? '已設定' : '未完成'}
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
                <strong>Crypto 依賴：</strong>
                {paymentSummary.has_crypto_dependency ? '已安裝' : '缺少 pycryptodome'}
              </div>
              {paymentSummary.missing_settings?.length ? (
                <div className="notice">
                  缺少設定：{paymentSummary.missing_settings.join(', ')}
                </div>
              ) : null}
            </div>

            {/* 建立支付 sandbox payload 的表單。 */}
            <form className="stack" onSubmit={handlePreparePayment}>
              <label className="stack">
                <span>商品描述覆寫</span>
                <input
                  value={paymentForm.item_desc_override}
                  onChange={(event) => updatePaymentForm('item_desc_override', event.target.value)}
                  placeholder="留空則由訂單商品名稱自動組合"
                />
              </label>
              <label className="stack">
                <span>Email</span>
                <input
                  value={paymentForm.email}
                  onChange={(event) => updatePaymentForm('email', event.target.value)}
                  placeholder="buyer@example.com"
                  type="email"
                />
              </label>
              <label className="stack">
                <span>Notify URL 覆寫</span>
                <input
                  value={paymentForm.notify_url}
                  onChange={(event) => updatePaymentForm('notify_url', event.target.value)}
                  placeholder="留空則使用後端環境變數"
                />
              </label>
              <label className="stack">
                <span>Return URL 覆寫</span>
                <input
                  value={paymentForm.return_url}
                  onChange={(event) => updatePaymentForm('return_url', event.target.value)}
                  placeholder="留空則使用後端環境變數"
                />
              </label>
              <label className="stack">
                <span>ClientBack URL 覆寫</span>
                <input
                  value={paymentForm.client_back_url}
                  onChange={(event) => updatePaymentForm('client_back_url', event.target.value)}
                  placeholder="留空則使用後端環境變數"
                />
              </label>
              <button className="btn-primary" disabled={paymentSubmitting} type="submit">
                {paymentSubmitting ? '建立中…' : '建立藍新支付 Sandbox Payload'}
              </button>
            </form>

            {/* 顯示後端回傳的 sandbox form 欄位，方便人工核對。 */}
            {paymentPrepared ? (
              <div className="stack">
                <div>
                  <strong>商店訂單編號：</strong>
                  {paymentPrepared.merchant_order_no}
                </div>
                <div>
                  <strong>送單網址：</strong>
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
                <form
                  action={paymentPrepared.gateway_url}
                  method={paymentPrepared.form_method}
                  target="_blank"
                  className="stack"
                >
                  {Object.entries(paymentPrepared.form_fields).map(([key, value]) => (
                    <input key={key} name={key} type="hidden" value={String(value)} />
                  ))}
                  <button className="btn-primary" type="submit">
                    用新分頁送往藍新 Sandbox
                  </button>
                </form>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

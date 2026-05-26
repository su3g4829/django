'use client'

/**
 * 賣家訂單明細頁。
 *
 * 功能：
 * - 顯示賣家可見的訂單內容、商品履約狀態、物流單號
 * - 提供藍新物流 sandbox scaffold 測試區，確認後端物流設定與建議 payload
 *
 * 對應 API：
 * - GET `/api/v1/me/sales/:id/`
 * - GET `/api/v1/me/sales/:id/newebpay-logistics/sandbox/`
 * - POST `/api/v1/me/sales/:id/newebpay-logistics/sandbox/`
 */

import { useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type {
  NewebpaySandboxLogisticsPrepared,
  NewebpaySandboxLogisticsSummary,
  Order,
} from '@/lib/types'

type SandboxLogisticsFormState = {
  logistics_type: string
  shipment_note: string
}

const INITIAL_LOGISTICS_FORM: SandboxLogisticsFormState = {
  logistics_type: 'UNIMARTC2C',
  shipment_note: '',
}

export default function SellerOrderDetailPage({ params }: { params: { id: string } }) {
  /** 目前瀏覽中的賣家訂單 ID。 */
  const orderId = useMemo(() => params.id, [params.id])
  /** 賣家可見的訂單明細。 */
  const [order, setOrder] = useState<Order | null>(null)
  /** 主畫面載入狀態。 */
  const [loading, setLoading] = useState(true)
  /** 主畫面錯誤訊息。 */
  const [error, setError] = useState('')

  /** 藍新物流 sandbox 設定摘要。 */
  const [logisticsSummary, setLogisticsSummary] = useState<NewebpaySandboxLogisticsSummary | null>(null)
  /** 藍新物流 sandbox 建議 payload。 */
  const [logisticsPrepared, setLogisticsPrepared] = useState<NewebpaySandboxLogisticsPrepared | null>(null)
  /** 物流 sandbox 表單欄位。 */
  const [logisticsForm, setLogisticsForm] = useState<SandboxLogisticsFormState>(INITIAL_LOGISTICS_FORM)
  /** 物流 sandbox 區塊錯誤訊息。 */
  const [logisticsError, setLogisticsError] = useState('')
  /** 物流 sandbox 設定摘要載入狀態。 */
  const [logisticsSummaryLoading, setLogisticsSummaryLoading] = useState(true)
  /** 物流 sandbox 建立 payload 送出中狀態。 */
  const [logisticsSubmitting, setLogisticsSubmitting] = useState(false)

  useEffect(() => {
    setLoading(true)
    apiFetch<Order>(`/me/sales/${orderId}/`)
      .then((payload) => {
        setOrder(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [orderId])

  useEffect(() => {
    setLogisticsSummaryLoading(true)
    apiFetch<NewebpaySandboxLogisticsSummary>(`/me/sales/${orderId}/newebpay-logistics/sandbox/`)
      .then((payload) => {
        setLogisticsSummary(payload)
        setLogisticsError('')
      })
      .catch((err: Error) => setLogisticsError(err.message))
      .finally(() => setLogisticsSummaryLoading(false))
  }, [orderId])

  /**
   * 更新物流 sandbox 表單欄位。
   *
   * field:
   * - 要更新的欄位名稱
   *
   * value:
   * - 使用者輸入的新值
   */
  function updateLogisticsForm(field: keyof SandboxLogisticsFormState, value: string) {
    setLogisticsForm((current) => ({ ...current, [field]: value }))
  }

  /**
   * 建立藍新物流 sandbox scaffold payload。
   *
   * event:
   * - 原生表單送出事件，用於阻止頁面重整
   */
  async function handlePrepareLogistics(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLogisticsSubmitting(true)
    setLogisticsError('')

    try {
      const payload = await apiFetch<NewebpaySandboxLogisticsPrepared>(
        `/me/sales/${orderId}/newebpay-logistics/sandbox/`,
        {
          method: 'POST',
          body: JSON.stringify(logisticsForm),
        },
      )
      setLogisticsPrepared(payload)
    } catch (err) {
      setLogisticsError(err instanceof Error ? err.message : '建立藍新物流測試資料失敗。')
      setLogisticsPrepared(null)
    } finally {
      setLogisticsSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入賣家訂單明細中…</section>
  }

  return (
    <div className="stack">
      {/* 訂單標題與賣家履約狀態。 */}
      <section className="card stack">
        <h1>賣家訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            {order.created_at_display} ・ {order.seller_status_label ?? order.seller_status ?? order.status_label ?? order.status}
          </div>
        )}
      </section>

      {/* 賣家視角的商品與履約資料表。 */}
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
                <th>履約狀態</th>
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

      {/* 藍新物流 sandbox scaffold 設定摘要與測試表單。 */}
      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>藍新物流 Sandbox 測試</h2>
          <span className="badge">Seller Test</span>
        </div>
        <div className="muted">
          這一段先用來檢查物流 merchant 設定，以及把賣家訂單整理成建議送件 payload。
        </div>
        {logisticsError ? <div className="notice">{logisticsError}</div> : null}
        {logisticsSummaryLoading ? (
          <div className="muted">載入藍新物流設定中…</div>
        ) : !logisticsSummary ? (
          <div className="muted">目前無法取得藍新物流設定摘要。</div>
        ) : (
          <>
            <div className="stack">
              <div>
                <strong>設定狀態：</strong>
                {logisticsSummary.configured ? '已設定' : '未完成'}
              </div>
              <div>
                <strong>Merchant ID：</strong>
                {logisticsSummary.merchant_id || '未設定'}
              </div>
              <div>
                <strong>Callback URL：</strong>
                {logisticsSummary.callback_url || '未設定'}
              </div>
              <div>
                <strong>Create URL：</strong>
                {logisticsSummary.create_url || '未設定'}
              </div>
              <div>
                <strong>Status URL：</strong>
                {logisticsSummary.status_url || '未設定'}
              </div>
              {logisticsSummary.missing_settings?.length ? (
                <div className="notice">
                  缺少設定：{logisticsSummary.missing_settings.join(', ')}
                </div>
              ) : null}
            </div>

            {/* 建立物流 sandbox scaffold payload 的表單。 */}
            <form className="stack" onSubmit={handlePrepareLogistics}>
              <label className="stack">
                <span>物流類型</span>
                <select
                  value={logisticsForm.logistics_type}
                  onChange={(event) => updateLogisticsForm('logistics_type', event.target.value)}
                >
                  <option value="UNIMARTC2C">UNIMARTC2C</option>
                  <option value="FAMIC2C">FAMIC2C</option>
                  <option value="TCAT">TCAT</option>
                </select>
              </label>
              <label className="stack">
                <span>出貨備註</span>
                <textarea
                  rows={3}
                  value={logisticsForm.shipment_note}
                  onChange={(event) => updateLogisticsForm('shipment_note', event.target.value)}
                  placeholder="例如：超商交貨便測試訂單"
                />
              </label>
              <button className="btn-primary" disabled={logisticsSubmitting} type="submit">
                {logisticsSubmitting ? '建立中…' : '建立藍新物流 Sandbox Payload'}
              </button>
            </form>

            {/* 顯示後端整理後的建議送件資料。 */}
            {logisticsPrepared ? (
              <div className="stack">
                <div>
                  <strong>物流類型：</strong>
                  {logisticsPrepared.logistics_type}
                </div>
                <div>
                  <strong>送件 URL：</strong>
                  {logisticsPrepared.create_url || '未設定'}
                </div>
                <div className="stack">
                  <strong>Suggested Payload</strong>
                  <pre>{JSON.stringify(logisticsPrepared.suggested_payload, null, 2)}</pre>
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>
    </div>
  )
}

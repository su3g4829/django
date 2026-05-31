'use client'

import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'
import type { NewebpayLogisticsRecord, NewebpaySandboxLogisticsPrepared, NewebpaySandboxLogisticsSummary, Order } from '@/lib/types'

type SandboxLogisticsFormState = {
  logistics_type: string
  shipment_note: string
}

const INITIAL_LOGISTICS_FORM: SandboxLogisticsFormState = {
  logistics_type: 'UNIMARTC2C',
  shipment_note: '',
}

export default function SellerOrderDetailPage() {
  const params = useParams<{ id: string }>()
  const orderId = useMemo(() => params.id, [params.id])

  const [order, setOrder] = useState<Order | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [logisticsSummary, setLogisticsSummary] = useState<NewebpaySandboxLogisticsSummary | null>(null)
  const [logisticsSummaryLoading, setLogisticsSummaryLoading] = useState(true)
  const [logisticsPrepared, setLogisticsPrepared] = useState<NewebpaySandboxLogisticsPrepared | null>(null)
  const [logisticsRecord, setLogisticsRecord] = useState<NewebpayLogisticsRecord | null>(null)
  const [logisticsForm, setLogisticsForm] = useState<SandboxLogisticsFormState>(INITIAL_LOGISTICS_FORM)
  const [logisticsSubmitting, setLogisticsSubmitting] = useState(false)
  const [logisticsError, setLogisticsError] = useState('')

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

  useEffect(() => {
    apiFetch<NewebpayLogisticsRecord>(`/me/sales/${orderId}/newebpay-logistics/`)
      .then((payload) => setLogisticsRecord(payload))
      .catch(() => setLogisticsRecord(null))
  }, [orderId])

  function updateLogisticsForm<K extends keyof SandboxLogisticsFormState>(field: K, value: SandboxLogisticsFormState[K]) {
    setLogisticsForm((current) => ({ ...current, [field]: value }))
  }

  async function handlePrepareLogistics(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLogisticsSubmitting(true)
    setLogisticsError('')

    try {
      const payload = await apiFetch<NewebpaySandboxLogisticsPrepared>(`/me/sales/${orderId}/newebpay-logistics/sandbox/`, {
        method: 'POST',
        body: JSON.stringify(logisticsForm),
      })
      setLogisticsPrepared(payload)
      setLogisticsRecord(null)
    } catch (err) {
      setLogisticsPrepared(null)
      setLogisticsError(err instanceof Error ? err.message : '建立 NewebPay 物流 sandbox payload 失敗。')
    } finally {
      setLogisticsSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">讀取賣家訂單中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>賣家訂單 #{order?.id ?? orderId}</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!order ? null : (
          <div className="muted">
            建立時間：{order.created_at_display ?? order.created_at} / 履約狀態：
            {order.seller_status_label ?? order.seller_status ?? order.status_label ?? order.status}
          </div>
        )}
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>取貨門市</h2>
          {order?.pickup_store_name ? (
            <div className="card stack">
              <strong>超商門市</strong>
              <div>
                {order.pickup_store_brand_label ?? order.pickup_store_brand} / {order.pickup_store_name}
              </div>
              <div className="muted">門市代碼：{order.pickup_store_code || '-'}</div>
              <div className="muted">門市地址：{order.pickup_store_address || '-'}</div>
            </div>
          ) : (
            <div className="muted">這張訂單沒有超商取貨門市資料。</div>
          )}
        </section>

        <section className="card stack">
          <h2>收件資料</h2>
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
            <div className="muted">這張訂單沒有收件資料。</div>
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
                <th>履約狀態</th>
                <th>物流單號</th>
                <th>金額</th>
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
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2>NewebPay Sandbox 物流</h2>
          <span className="badge">Seller Test</span>
        </div>
        <div className="muted">這裡會依買家結帳資料建立物流 sandbox payload，方便測試物流建立與 callback 流程。</div>

        {logisticsError ? <div className="notice">{logisticsError}</div> : null}
        {logisticsSummaryLoading ? (
          <div className="muted">讀取物流設定中...</div>
        ) : !logisticsSummary ? (
          <div className="muted">目前沒有可用的物流設定。</div>
        ) : (
          <>
            <div className="stack">
              <div>
                <strong>設定狀態：</strong>
                {logisticsSummary.configured ? '已完成' : '未完成'}
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
                <div className="notice">缺少設定：{logisticsSummary.missing_settings.join(', ')}</div>
              ) : null}
            </div>

            <form className="stack" onSubmit={handlePrepareLogistics}>
              <label className="stack">
                <span>物流類型</span>
                <select value={logisticsForm.logistics_type} onChange={(event) => updateLogisticsForm('logistics_type', event.target.value)}>
                  <option value="UNIMARTC2C">UNIMARTC2C</option>
                  <option value="FAMIC2C">FAMIC2C</option>
                  <option value="TCAT">TCAT</option>
                </select>
              </label>
              <label className="stack">
                <span>出貨備註</span>
                <textarea
                  placeholder="可選填，用來補充本次出貨說明"
                  rows={3}
                  value={logisticsForm.shipment_note}
                  onChange={(event) => updateLogisticsForm('shipment_note', event.target.value)}
                />
              </label>
              <button className="btn-primary" disabled={logisticsSubmitting} type="submit">
                {logisticsSubmitting ? '建立中...' : '建立 Sandbox Payload'}
              </button>
            </form>

            {logisticsPrepared ? (
              <div className="stack">
                {logisticsPrepared.buyer_shipping_summary ? (
                  <div className="card stack">
                    <strong>買家結帳資料摘要</strong>
                    <div>
                      配送方式：
                      {logisticsPrepared.buyer_shipping_summary.shipping_method_label ??
                        logisticsPrepared.buyer_shipping_summary.shipping_method}
                    </div>
                    <div>
                      付款方式：
                      {logisticsPrepared.buyer_shipping_summary.payment_method_label ??
                        logisticsPrepared.buyer_shipping_summary.payment_method}
                    </div>
                    {logisticsPrepared.buyer_shipping_summary.is_convenience_store ? (
                      <>
                        <div>
                          取貨門市品牌：
                          {logisticsPrepared.buyer_shipping_summary.pickup_store_brand_label ??
                            logisticsPrepared.buyer_shipping_summary.pickup_store_brand ??
                            '-'}
                        </div>
                        <div>門市代碼：{logisticsPrepared.buyer_shipping_summary.pickup_store_code || '-'}</div>
                        <div>門市名稱：{logisticsPrepared.buyer_shipping_summary.pickup_store_name || '-'}</div>
                        <div>門市地址：{logisticsPrepared.buyer_shipping_summary.pickup_store_address || '-'}</div>
                      </>
                    ) : null}
                  </div>
                ) : null}
                <div>
                  <strong>物流類型：</strong>
                  {logisticsPrepared.logistics_type}
                </div>
                <div>
                  <strong>建立 URL：</strong>
                  {logisticsPrepared.create_url || '未提供'}
                </div>
                <div className="stack">
                  <strong>Suggested Payload</strong>
                  <pre>{JSON.stringify(logisticsPrepared.suggested_payload, null, 2)}</pre>
                </div>
              </div>
            ) : null}

            {logisticsRecord ? (
              <div className="card stack">
                <strong>最新物流紀錄</strong>
                <div>模式：{logisticsRecord.mode}</div>
                <div>狀態：{logisticsRecord.status_label}</div>
                <div>商店訂單編號：{logisticsRecord.merchant_order_no || '-'}</div>
                <div>物流單號：{logisticsRecord.logistics_no || '-'}</div>
                <div>物流類型：{logisticsRecord.store_type || '-'}</div>
                <div>回調次數：{logisticsRecord.callback_count}</div>
                <div className="muted">建立時間：{logisticsRecord.created_at}</div>
                <div className="muted">更新時間：{logisticsRecord.updated_at}</div>
                {logisticsRecord.raw_payload ? (
                  <details>
                    <summary>查看原始回傳</summary>
                    <pre>{JSON.stringify(logisticsRecord.raw_payload, null, 2)}</pre>
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

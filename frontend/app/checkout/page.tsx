'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { apiFetch, dispatchAppBootstrapRefresh, toQueryString } from '@/lib/api'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { CheckoutPreviewPayload, Order } from '@/lib/types'

type CheckoutFormState = {
  address_id: number
  shipping_method: string
  pickup_store_brand: string
  pickup_store_code: string
  pickup_store_name: string
  pickup_store_address: string
  payment_method: string
  buyer_note: string
}

type StoreMapPreparedPayload = {
  action_url: string
  form_method: string
  form_fields: Record<string, string>
}

type StoreSelectionPayload = {
  selection_token: string
  status: string
  is_ready: boolean
  pickup_store_brand?: string
  pickup_store_brand_label?: string
  pickup_store_code?: string
  pickup_store_name?: string
  pickup_store_address?: string
}

const INITIAL_FORM: CheckoutFormState = {
  address_id: 0,
  shipping_method: 'home_delivery',
  pickup_store_brand: '',
  pickup_store_code: '',
  pickup_store_name: '',
  pickup_store_address: '',
  payment_method: 'newebpay_credit',
  buyer_note: '',
}

const CHECKOUT_DRAFT_KEY = 'checkout-form'

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function submitExternalForm(actionUrl: string, method: string, fields: Record<string, string>) {
  const form = document.createElement('form')
  form.action = actionUrl
  form.method = method
  form.style.display = 'none'

  Object.entries(fields).forEach(([key, value]) => {
    const input = document.createElement('input')
    input.type = 'hidden'
    input.name = key
    input.value = value
    form.appendChild(input)
  })

  document.body.appendChild(form)
  form.submit()
}

export default function CheckoutPage() {
  const router = useRouter()
  const [preview, setPreview] = useState<CheckoutPreviewPayload | null>(null)
  const [form, setForm] = useState<CheckoutFormState>(() => getSessionDraft<CheckoutFormState>(CHECKOUT_DRAFT_KEY) ?? INITIAL_FORM)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [previewReady, setPreviewReady] = useState(false)
  const [storeMapBusy, setStoreMapBusy] = useState(false)
  const [storeMapMessage, setStoreMapMessage] = useState('')
  const [processedStoreMapToken, setProcessedStoreMapToken] = useState('')

  useEffect(() => {
    setSessionDraft(CHECKOUT_DRAFT_KEY, form)
  }, [form])

  async function loadPreview(preferredShippingMethod?: string) {
    setLoading(true)
    try {
      const payload = await apiFetch<CheckoutPreviewPayload>(
        `/checkout/preview/${toQueryString({
          shipping_method: preferredShippingMethod || form.shipping_method || 'home_delivery',
        })}`,
      )
      setPreview(payload)
      const baseForm: CheckoutFormState = {
        address_id: payload.selected_address_id ?? payload.addresses[0]?.id ?? 0,
        shipping_method: payload.selected_shipping_method ?? preferredShippingMethod ?? 'home_delivery',
        pickup_store_brand: '',
        pickup_store_code: '',
        pickup_store_name: '',
        pickup_store_address: '',
        payment_method: payload.selected_payment_method ?? 'newebpay_credit',
        buyer_note: '',
      }
      const draft = getSessionDraft<Partial<CheckoutFormState>>(CHECKOUT_DRAFT_KEY)
      const nextForm = draft ? { ...baseForm, ...draft } : baseForm
      nextForm.shipping_method = payload.selected_shipping_method ?? nextForm.shipping_method
      if (!payload.addresses.some((address) => address.id === nextForm.address_id)) {
        nextForm.address_id = baseForm.address_id
      }
      setForm(nextForm)
      setError(payload.detail ?? '')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入結帳預覽失敗。')
    } finally {
      setPreviewReady(true)
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadPreview(form.shipping_method)
  }, [])

  useEffect(() => {
    if (!previewReady || !preview) {
      return
    }
    if (form.shipping_method === preview.selected_shipping_method) {
      return
    }
    void loadPreview(form.shipping_method)
  }, [form.shipping_method, preview, previewReady])

  function updateForm<K extends keyof CheckoutFormState>(field: K, value: CheckoutFormState[K]) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function updatePickupStoreBrand(value: string) {
    setForm((current) => {
      if (current.pickup_store_brand === value) {
        return { ...current, pickup_store_brand: value }
      }
      return {
        ...current,
        pickup_store_brand: value,
        pickup_store_code: '',
        pickup_store_name: '',
        pickup_store_address: '',
      }
    })
    setStoreMapMessage('')
  }

  function applyStoreSelection(selection: StoreSelectionPayload) {
    setForm((current) => ({
      ...current,
      pickup_store_brand: selection.pickup_store_brand || current.pickup_store_brand,
      pickup_store_code: selection.pickup_store_code || '',
      pickup_store_name: selection.pickup_store_name || '',
      pickup_store_address: selection.pickup_store_address || '',
    }))
    setStoreMapMessage(
      selection.pickup_store_name
        ? `已回填 ${selection.pickup_store_brand_label || selection.pickup_store_brand || '超商'}門市：${selection.pickup_store_name}`
        : '',
    )
  }

  async function hydrateStoreSelectionFromToken(selectionToken: string) {
    setStoreMapBusy(true)
    let readySelection: StoreSelectionPayload | null = null

    for (let attempt = 0; attempt < 8; attempt += 1) {
      try {
        const selection = await apiFetch<StoreSelectionPayload>(
          `/checkout/logistics/store-selection/${toQueryString({ token: selectionToken })}`,
        )
        if (selection.is_ready) {
          readySelection = selection
          break
        }
      } catch {
        // The callback may not have reached our backend yet; retry briefly.
      }
      await sleep(700)
    }

    if (readySelection) {
      applyStoreSelection(readySelection)
      router.replace('/checkout')
    } else {
      setStoreMapMessage('藍新門市資料尚未回填完成，請稍後重新整理，或再次點選門市地圖。')
      router.replace('/checkout')
    }

    setStoreMapBusy(false)
  }

  useEffect(() => {
    if (!previewReady || typeof window === 'undefined') {
      return
    }
    const token = new URLSearchParams(window.location.search).get('store_map_token') ?? ''
    if (!token || token === processedStoreMapToken) {
      return
    }
    setProcessedStoreMapToken(token)
    void hydrateStoreSelectionFromToken(token)
  }, [previewReady, processedStoreMapToken])

  const selectedAddress = useMemo(
    () => preview?.addresses.find((address) => address.id === form.address_id) ?? null,
    [form.address_id, preview?.addresses],
  )

  const selectedShippingMethod = useMemo(
    () => preview?.shipping_methods.find((item) => item.value === form.shipping_method) ?? null,
    [form.shipping_method, preview?.shipping_methods],
  )

  const selectedPaymentMethod = useMemo(
    () => preview?.payment_methods.find((item) => item.value === form.payment_method) ?? null,
    [form.payment_method, preview?.payment_methods],
  )

  const selectedStoreBrand = useMemo(
    () => preview?.convenience_store_brands.find((item) => item.value === form.pickup_store_brand) ?? null,
    [form.pickup_store_brand, preview?.convenience_store_brands],
  )

  const requiresConvenienceStoreFields = form.shipping_method === 'convenience_store'
  const convenienceStoreFieldsComplete =
    !requiresConvenienceStoreFields ||
    Boolean(form.pickup_store_brand && form.pickup_store_code && form.pickup_store_name)

  async function openStoreMap() {
    if (!form.pickup_store_brand) {
      setError('請先選擇超商品牌。')
      return
    }
    try {
      setStoreMapBusy(true)
      setError('')
      setStoreMapMessage('即將開啟藍新超商門市地圖...')
      const payload = await apiFetch<StoreMapPreparedPayload>('/checkout/logistics/store-map/prepare/', {
        method: 'POST',
        body: JSON.stringify({
          pickup_store_brand: form.pickup_store_brand,
          payment_method: form.payment_method,
          return_url: `${window.location.origin}/checkout`,
        }),
      })
      submitExternalForm(payload.action_url, payload.form_method || 'POST', payload.form_fields)
    } catch (err) {
      setStoreMapBusy(false)
      setStoreMapMessage('')
      setError(err instanceof Error ? err.message : '開啟藍新門市地圖失敗。')
    }
  }

  async function confirmCheckout() {
    try {
      setSubmitting(true)
      setError('')
      const order = await apiFetch<Order>('/checkout/confirm/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      clearSessionDraft(CHECKOUT_DRAFT_KEY)
      dispatchAppBootstrapRefresh({ cart_count: 0 })
      router.push(`/orders/${order.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : '建立訂單失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入結帳預覽中...</section>
  }

  if (!preview) {
    return <section className="card">目前無法讀取結帳資料。</section>
  }

  const canSubmit =
    !preview.requires_login &&
    preview.item_count > 0 &&
    Boolean(form.address_id) &&
    convenienceStoreFieldsComplete &&
    !error &&
    !submitting &&
    !storeMapBusy

  return (
    <div className="stack">
      <section className="card stack">
        <h1>結帳</h1>
        <div className="muted">
          請確認收件地址、配送方式與付款方式後送出訂單。若選擇超商取貨，請先透過藍新門市地圖完成選店。
        </div>
        {preview.requires_login ? <div className="notice">請先登入會員後再進行結帳。</div> : null}
        {error ? <div className="notice">{error}</div> : null}
        {storeMapMessage ? <div className="notice">{storeMapMessage}</div> : null}
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>商品明細</h2>
          {!preview.items.length ? (
            <div className="muted">購物車目前沒有商品。</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>商品</th>
                  <th>規格</th>
                  <th>數量</th>
                  <th>小計</th>
                </tr>
              </thead>
              <tbody>
                {preview.items.map((item) => (
                  <tr key={item.key}>
                    <td>{item.display_name ?? item.name}</td>
                    <td>{item.variant_name || '-'}</td>
                    <td>{item.qty}</td>
                    <td>${item.line_total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card stack">
          <h2>金額摘要</h2>
          <div className="muted">商品數量：{preview.item_count}</div>
          <div className="muted">商品小計：${preview.totals.subtotal}</div>
          <div className="muted">運費：${preview.totals.shipping}</div>
          <div className="muted">折扣：${preview.totals.discount}</div>
          <div>
            <strong>總計：${preview.totals.total}</strong>
          </div>
          {preview.seller_shipping_groups?.length ? (
            <div className="stack" style={{ gap: '0.5rem' }}>
              <strong>分賣家運費摘要</strong>
              {preview.seller_shipping_groups.map((group) => (
                <div className="card stack" key={group.seller_username} style={{ gap: '0.35rem' }}>
                  <div>
                    <strong>{group.seller_display_name}</strong>
                  </div>
                  <div className="muted">商品小計 ${group.subtotal}</div>
                  <div className="muted">{group.selected_shipping_method_label}運費 ${group.shipping_fee}</div>
                  <div className="muted">
                    {group.free_shipping_applied
                      ? `已達免運門檻 $${group.free_shipping_threshold}`
                      : `免運門檻 $${group.free_shipping_threshold}`}
                  </div>
                  {!group.selected_shipping_method_supported ? (
                    <div className="notice">目前選擇的配送方式不適用於這位賣家的所有商品，請改用其他配送方式。</div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          <div className="muted">
            配送方式：{selectedShippingMethod?.label ?? '未選擇'} / 付款方式：{selectedPaymentMethod?.label ?? '未選擇'}
          </div>
          <button className="btn-primary" disabled={!canSubmit} onClick={confirmCheckout} type="button">
            {submitting ? '建立訂單中...' : '前往付款'}
          </button>
        </section>
      </div>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>收件地址</h2>
          {!preview.addresses.length ? (
            <div className="stack">
              <div className="muted">你尚未建立收件地址，請先到會員中心新增地址。</div>
              <button className="btn" onClick={() => router.push('/me/addresses')} type="button">
                前往地址管理
              </button>
            </div>
          ) : (
            preview.addresses.map((address) => (
              <label className="card stack" key={address.id}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <input
                      checked={form.address_id === address.id}
                      name="address_id"
                      onChange={() => updateForm('address_id', address.id)}
                      type="radio"
                    />{' '}
                    <strong>{address.label}</strong>
                  </div>
                  {address.is_default ? <span className="badge">預設</span> : null}
                </div>
                <div>{address.recipient}</div>
                <div className="muted">{address.phone}</div>
                <div className="muted">
                  {address.postal_code ? `${address.postal_code} ` : ''}
                  {address.city}
                  {address.district}
                  {address.address_line}
                </div>
              </label>
            ))
          )}
          {selectedAddress ? <div className="muted">目前配送地址：{selectedAddress.label}</div> : null}
        </section>

        <section className="card stack">
          <h2>發票設定</h2>
          {!preview.invoice_profile?.invoice_type ? (
            <div className="muted">尚未設定發票資料，若需要載具或統編，請先到會員中心設定。</div>
          ) : (
            <div className="stack">
              <div>發票類型：{preview.invoice_profile.invoice_type}</div>
              {preview.invoice_profile.company_name ? <div>公司名稱：{preview.invoice_profile.company_name}</div> : null}
              {preview.invoice_profile.tax_id ? <div>統一編號：{preview.invoice_profile.tax_id}</div> : null}
              {preview.invoice_profile.carrier_code ? <div>載具號碼：{preview.invoice_profile.carrier_code}</div> : null}
            </div>
          )}
          <button className="btn" onClick={() => router.push('/me/invoice')} type="button">
            前往發票設定
          </button>
        </section>
      </div>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>配送方式</h2>
          {preview.shipping_methods.map((method) => (
            <label key={method.value}>
              <input
                checked={form.shipping_method === method.value}
                name="shipping_method"
                onChange={() => updateForm('shipping_method', method.value)}
                type="radio"
              />{' '}
              {method.label}
            </label>
          ))}

          {requiresConvenienceStoreFields ? (
            <div className="card stack">
              <strong>超商取貨門市</strong>
              <div className="muted">先選擇超商品牌，再使用藍新門市地圖完成選店。回到結帳頁後會自動帶入門市名稱與代碼。</div>
              <label className="field">
                <span>超商品牌</span>
                <select value={form.pickup_store_brand} onChange={(event) => updatePickupStoreBrand(event.target.value)}>
                  <option value="">請選擇品牌</option>
                  {preview.convenience_store_brands.map((brand) => (
                    <option key={brand.value} value={brand.value}>
                      {brand.label}
                    </option>
                  ))}
                </select>
              </label>
              <div className="row" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
                <button className="btn" disabled={!form.pickup_store_brand || storeMapBusy} onClick={openStoreMap} type="button">
                  {storeMapBusy ? '門市地圖準備中...' : form.pickup_store_code ? '重新選擇門市' : '使用藍新門市地圖'}
                </button>
                {form.pickup_store_code ? (
                  <button
                    className="btn"
                    onClick={() => {
                      setStoreMapMessage('')
                      setForm((current) => ({
                        ...current,
                        pickup_store_code: '',
                        pickup_store_name: '',
                        pickup_store_address: '',
                      }))
                    }}
                    type="button"
                  >
                    清除門市
                  </button>
                ) : null}
              </div>
              {selectedStoreBrand ? <div className="muted">目前品牌：{selectedStoreBrand.label}</div> : null}
              <div className="stack" style={{ gap: '0.35rem' }}>
                <div>門市代碼：{form.pickup_store_code || '尚未選擇'}</div>
                <div>門市名稱：{form.pickup_store_name || '尚未選擇'}</div>
                <div className="muted">門市地址：{form.pickup_store_address || '尚未選擇'}</div>
              </div>
            </div>
          ) : null}
        </section>

        <section className="card stack">
          <h2>付款方式與備註</h2>
          {preview.payment_methods.map((method) => (
            <label key={method.value}>
              <input
                checked={form.payment_method === method.value}
                name="payment_method"
                onChange={() => updateForm('payment_method', method.value)}
                type="radio"
              />{' '}
              {method.label}
            </label>
          ))}

          <label className="field">
            <span>訂單備註</span>
            <textarea
              placeholder="例如：白天請勿按門鈴、可晚間收貨。"
              rows={4}
              value={form.buyer_note}
              onChange={(event) => updateForm('buyer_note', event.target.value)}
            />
          </label>
        </section>
      </div>
    </div>
  )
}

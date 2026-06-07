'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * checkout 頁需要：
 * - 表單 state
 * - router 跳轉
 * - effect 抓 preview
 * - 事件處理與按鈕提交
 *
 * 所以必須在瀏覽器端執行。
 */

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'

import { apiFetch, dispatchAppBootstrapRefresh, toQueryString } from '@/lib/api'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { CheckoutPreviewPayload, Order } from '@/lib/types'

/**
 * checkout 表單真正送往後端時的最小欄位。
 * 其餘展示資訊都來自 preview payload，不另外在前端重組。
 *
 * 設計意義：
 * - 前端只保存必要的可編輯欄位
 * - 金額、賣家群組、發票摘要都依賴後端 preview
 * - 避免前端自己重算，造成與後端規則不一致
 */
type CheckoutFormState = {
  address_id: number
  shipping_method: string
  payment_method: string
  buyer_note: string
}

// 第一次進入 checkout，若沒有草稿就先用這組預設值。
const INITIAL_FORM: CheckoutFormState = {
  address_id: 0,
  shipping_method: 'home_delivery',
  payment_method: 'newebpay',
  buyer_note: '',
}

// cart 頁與 checkout 頁共用同一份草稿 key，方便跨頁延續配送方式。
const CHECKOUT_DRAFT_KEY = 'checkout-form'

/**
 * checkout 頁負責：
 * 1. 抓 preview payload 顯示購物車摘要
 * 2. 管理地址 / 配送 / 付款方式表單
 * 3. 送出 `/checkout/confirm/` 建立正式訂單
 *
 * 來源：
 * - `useRouter` 來自 `next/navigation`
 * - `useEffect` / `useMemo` / `useState` 來自 React
 * - 草稿暫存透過 `session-drafts` 封裝瀏覽器 `sessionStorage`
 */
export default function CheckoutPage() {
  const router = useRouter()
  // preview 來自後端聚合資料，是整個 checkout 頁面的單一資料來源。
  const [preview, setPreview] = useState<CheckoutPreviewPayload | null>(null)
  const [form, setForm] = useState<CheckoutFormState>(() => getSessionDraft<CheckoutFormState>(CHECKOUT_DRAFT_KEY) ?? INITIAL_FORM)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  // 避免初次載入前就因 watch shipping_method 再觸發一次 preview API。
  const [previewReady, setPreviewReady] = useState(false)

  /**
   * 任何表單變動都先寫回草稿。
   *
   * `useEffect` 依賴 `form`：
   * - 代表每次 form 任何欄位變動後都會執行一次
   * - 適合做這種「跟 state 同步到瀏覽器儲存」的副作用
   */
  useEffect(() => {
    setSessionDraft(CHECKOUT_DRAFT_KEY, form)
  }, [form])

  /**
   * 重新抓 checkout preview。
   * 這裡會同時負責：
   * - 以後端回傳的合法選項修正表單
   * - 決定預設地址與付款方式
   * - 保留仍然有效的草稿值
   *
   * 程式語法：
   * - `await apiFetch<CheckoutPreviewPayload>(...)` 會先等後端回傳 preview
   * - 然後再依 preview 與 draft 合成最終要放進表單的 state
   */
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
        payment_method: payload.selected_payment_method ?? 'newebpay',
        buyer_note: '',
      }
      const draft = getSessionDraft<Partial<CheckoutFormState>>(CHECKOUT_DRAFT_KEY)
      const nextForm = draft ? { ...baseForm, ...draft } : baseForm
      nextForm.shipping_method = payload.selected_shipping_method ?? nextForm.shipping_method
      nextForm.payment_method = payload.selected_payment_method ?? 'newebpay'
      if (!payload.addresses.some((address) => address.id === nextForm.address_id)) {
        nextForm.address_id = baseForm.address_id
      }
      setForm(nextForm)
      setError(payload.detail ?? '')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入結帳資料失敗。')
    } finally {
      setPreviewReady(true)
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadPreview(form.shipping_method)
  }, [])

  /**
   * 配送方式一改變，就要求後端重新計算 preview。
   *
   * 原因：
   * - 運費可能跟配送方式綁定
   * - 賣家群組可用配送方式也可能不同
   * - 所以前端不自己重算，統一回後端取最新 canonical preview
   */
  useEffect(() => {
    if (!previewReady || !preview) {
      return
    }
    if (form.shipping_method === preview.selected_shipping_method) {
      return
    }
    void loadPreview(form.shipping_method)
  }, [form.shipping_method, preview, previewReady])

  /**
   * 小型 helper，統一處理欄位更新。
   *
   * `K extends keyof CheckoutFormState`
   * - 來源：TypeScript generic constraint
   * - 意思是 `field` 只能是 `CheckoutFormState` 的合法欄位名
   * - 這樣 `value` 也會自動跟著推斷成正確欄位型別
   */
  function updateForm<K extends keyof CheckoutFormState>(field: K, value: CheckoutFormState[K]) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  /**
   * 真正建立訂單。
   * 成功後會：
   * 1. 清掉 checkout 草稿
   * 2. 刷新 header 的 cart count
   * 3. 導去訂單詳情頁
   */
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

  /**
   * 這三個 `useMemo` 都是在做「從選中的 id / value 反查完整物件」。
   *
   * 用途：
   * - JSX 顯示時不必每次內嵌 `find(...)`
   * - 讓畫面上的摘要欄位更好讀
   * - 把衍生值與原始 state 分開
   */
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

  const canSubmit =
    !preview?.requires_login &&
    Boolean(preview?.item_count) &&
    Boolean(form.address_id) &&
    !error &&
    !submitting

  if (loading) {
    return <section className="card">載入結帳資料中...</section>
  }

  if (!preview) {
    return <section className="card">目前無法取得結帳資料。</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>結帳</h1>
        <div className="muted">
          結帳頁只保留配送方式選擇。付款與超商門市選擇會在藍新支付頁面完成，避免站內資料與藍新實際回傳不一致。
        </div>
        {preview.requires_login ? <div className="notice">請先登入後再進行結帳。</div> : null}
        {error ? <div className="notice">{error}</div> : null}
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
                  <div className="muted">
                    {group.selected_shipping_method_label}運費 ${group.shipping_fee}
                  </div>
                  <div className="muted">
                    {group.free_shipping_applied
                      ? `已達免運門檻 $${group.free_shipping_threshold}`
                      : `免運門檻 $${group.free_shipping_threshold}`}
                  </div>
                  {!group.selected_shipping_method_supported ? (
                    <div className="notice">目前選擇的配送方式不適用於這個賣家，請先調整配送方式。</div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          <div className="muted">
            配送方式：{selectedShippingMethod?.label ?? '-'} / 付款方式：{selectedPaymentMethod?.label ?? '藍新支付'}
          </div>
          <button className="btn-primary" disabled={!canSubmit} onClick={confirmCheckout} type="button">
            {submitting ? '建立訂單中...' : '建立訂單'}
          </button>
        </section>
      </div>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>收件地址</h2>
          {!preview.addresses.length ? (
            <div className="stack">
              <div className="muted">目前沒有可用地址，請先到會員中心新增收件地址。</div>
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
            <div className="muted">目前沒有發票設定，建立訂單前可以先到會員中心設定。</div>
          ) : (
            <div className="stack">
              <div>發票類型：{preview.invoice_profile.invoice_type}</div>
              {preview.invoice_profile.company_name ? <div>公司名稱：{preview.invoice_profile.company_name}</div> : null}
              {preview.invoice_profile.tax_id ? <div>統一編號：{preview.invoice_profile.tax_id}</div> : null}
              {preview.invoice_profile.carrier_code ? <div>載具：{preview.invoice_profile.carrier_code}</div> : null}
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

          {form.shipping_method === 'convenience_store' ? (
            <div className="card stack">
              <strong>超商取貨說明</strong>
              <div className="muted">
                建立訂單後，請在藍新付款頁面選擇付款方式與取貨門市。訂單中的超商門市資訊會以藍新實際回傳資料為準。
              </div>
            </div>
          ) : (
            <div className="card stack">
              <strong>宅配到府說明</strong>
              <div className="muted">宅配訂單會使用你目前選取的收件地址，藍新付款頁不會再要求選擇超商門市。</div>
            </div>
          )}
        </section>

        <section className="card stack">
          <h2>付款方式與備註</h2>
          <div className="card stack">
            <strong>{selectedPaymentMethod?.label ?? '藍新支付'}</strong>
            <div className="muted">建立訂單後，會到訂單頁再正式送往藍新付款，實際付款工具以藍新頁面選擇與回傳為準。</div>
          </div>

          <label className="field">
            <span>訂單備註</span>
            <textarea
              placeholder="例如收貨時段、聯絡方式等。"
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

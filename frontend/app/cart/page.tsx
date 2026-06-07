'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 理由：
 * - 購物車頁需要 React hooks
 * - 需要在瀏覽器中響應輸入框變更、radio 切換、按鈕點擊
 * - 也需要把 checkout 草稿寫進 `sessionStorage`
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { apiFetch, dispatchAppBootstrapRefresh, toQueryString } from '@/lib/api'
import { getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { CartPayload } from '@/lib/types'

// 購物車頁若尚未選配送方式，就先以宅配作為預設值。
const DEFAULT_SHIPPING_METHOD = 'home_delivery'
// 前往 checkout 前，先把購物車頁選到的配送方式暫存到 session draft。
const CHECKOUT_DRAFT_KEY = 'checkout-form'

/**
 * 購物車頁負責：
 * 1. 讀取目前購物車內容
 * 2. 調整數量、刪除商品、套用折扣碼
 * 3. 選擇配送方式
 * 4. 把配送方式帶進 checkout 草稿
 *
 * 來源：
 * - `useRouter` 來自 `next/navigation`
 * - `useEffect` / `useState` 來自 React
 * - `sessionStorage` 封裝在 `@/lib/session-drafts`
 * - API 呼叫統一透過 `@/lib/api`
 *
 * 程式語法：
 * - 這是一個 Client Component，所以整個函式會在每次 render 時重新執行
 * - 真正的資料抓取與副作用工作，必須放進 `useEffect` 或事件 handler，而不是直接寫在函式本體
 */
export default function CartPage() {
  const router = useRouter()
  // cart 直接對應後端 `/cart/` payload，頁面所有摘要都由它推導。
  const [cart, setCart] = useState<CartPayload | null>(null)
  const [coupon, setCoupon] = useState('')
  // 使用者目前在頁面上選到的配送方式，會驅動重新抓運費與賣家分組摘要。
  const [selectedShippingMethod, setSelectedShippingMethod] = useState(DEFAULT_SHIPPING_METHOD)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  // 初次載入完成後才允許由配送方式變更觸發第二次 request，避免 mount 時重複打 API。
  const [cartReady, setCartReady] = useState(false)

  /**
   * 單一入口重新抓購物車資料。
   * 所有畫面上的 totals、賣家運費群組、折扣碼狀態都以這次回傳為準。
   *
   * 用法：
   * - 進入購物車頁時執行一次
   * - 切換配送方式後再執行一次，讓後端重算運費與摘要
   *
   * 程式語法：
   * - `async function` 讓函式內可以用 `await apiFetch(...)`
   * - `try / catch / finally` 分別處理成功、失敗與收尾狀態
   */
  async function loadCart(preferredShippingMethod?: string) {
    setLoading(true)
    try {
      const payload = await apiFetch<CartPayload>(
        `/cart/${toQueryString({
          shipping_method: preferredShippingMethod || selectedShippingMethod || DEFAULT_SHIPPING_METHOD,
        })}`,
      )
      setCart(payload)
      setCoupon(payload.coupon ?? '')
      setSelectedShippingMethod(payload.selected_shipping_method ?? preferredShippingMethod ?? DEFAULT_SHIPPING_METHOD)
      setError(payload.detail ?? '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cart.')
    } finally {
      setCartReady(true)
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadCart(selectedShippingMethod)
  }, [])

  /**
   * `useEffect` 是 React 的副作用 hook。
   *
   * 這一段的意思是：
   * - 畫面第一次 mount 後，額外去做一次 API 請求
   * - 因為抓資料這件事不能直接在 render 階段做
   *
   * `void loadCart(...)` 只是明確表示：
   * - 這裡有呼叫 async function
   * - 但不在此處直接接它回傳的 Promise
   */
  /**
   * 配送方式切換後重新抓購物車。
   *
   * 依賴陣列中放的是：
   * - `cart?.selected_shipping_method`
   * - `cartReady`
   * - `selectedShippingMethod`
   *
   * 意思是只要這三者其中之一改變，React 就會重新執行這個 effect。
   */
  useEffect(() => {
    if (!cartReady) {
      return
    }
    if (selectedShippingMethod === (cart?.selected_shipping_method ?? DEFAULT_SHIPPING_METHOD)) {
      return
    }
    void loadCart(selectedShippingMethod)
  }, [cart?.selected_shipping_method, cartReady, selectedShippingMethod])

  /**
   * 所有會改動購物車的操作都走這個 wrapper：
   * - 顯示送出中狀態
   * - 更新畫面上的 cart payload
   * - 同步刷新 header 的 cart count
   *
   * 來源：
   * - `dispatchAppBootstrapRefresh` 會通知 site header 重新抓全站計數
   *
   * 程式語法：
   * - `task` 是 callback function，型別是 `() => Promise<CartPayload>`
   * - 意思是「這個參數本身是一個函式；呼叫後會回傳 Promise，最終 resolve 成 CartPayload」
   * - 這樣 `updateQty` / `removeItem` / `applyCoupon` 就可以共用同一套 loading/error 邏輯
   */
  async function withMutation(task: () => Promise<CartPayload>) {
    try {
      setSubmitting(true)
      setError('')
      const next = await task()
      setCart(next)
      setCoupon(next.coupon ?? '')
      setSelectedShippingMethod(next.selected_shipping_method ?? selectedShippingMethod)
      setError(next.detail ?? '')
      dispatchAppBootstrapRefresh({ cart_count: next.item_count })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update cart.')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 調整單一 item 數量。
   *
   * 來源：
   * - `PATCH` 來自 HTTP method 慣例，表示部分更新單一資源
   */
  function updateQty(itemKey: string, qty: number) {
    return withMutation(() =>
      apiFetch<CartPayload>(
        `/cart/items/${encodeURIComponent(itemKey)}/${toQueryString({
          shipping_method: selectedShippingMethod,
        })}`,
        {
          method: 'PATCH',
          body: JSON.stringify({ qty }),
        },
      ),
    )
  }

  /**
   * 移除購物車項目。
   *
   * 用法：
   * - 送出 `DELETE`
   * - 後端回傳最新購物車 payload
   * - 前端直接用最新 payload 覆蓋舊 state
   */
  function removeItem(itemKey: string) {
    return withMutation(() =>
      apiFetch<CartPayload>(
        `/cart/items/${encodeURIComponent(itemKey)}/${toQueryString({
          shipping_method: selectedShippingMethod,
        })}`,
        {
          method: 'DELETE',
        },
      ),
    )
  }

  /**
   * 套用折扣碼。
   *
   * 不單獨做成另一組 state 計算，而是直接依賴後端重算結果，
   * 這樣 subtotal / shipping / discount / total 永遠來自同一份來源。
   */
  function applyCoupon() {
    return withMutation(() =>
      apiFetch<CartPayload>(
        `/cart/${toQueryString({
          shipping_method: selectedShippingMethod,
        })}`,
        {
          method: 'POST',
          body: JSON.stringify({ code: coupon }),
        },
      ),
    )
  }

  /**
   * 前往 checkout 前，把需要延續的 UI 狀態寫進 draft。
   *
   * 來源：
   * - `sessionStorage` 屬於瀏覽器 Web Storage API
   * - 本專案用 `getSessionDraft` / `setSessionDraft` 做包裝
   *
   * 為什麼不直接把配送方式塞進 query string：
   * - checkout 後續還會保存更多表單狀態
   * - 用 draft 比較適合承接多欄位跨頁資料
   */
  function proceedToCheckout() {
    const existingDraft = getSessionDraft<Record<string, unknown>>(CHECKOUT_DRAFT_KEY) ?? {}
    setSessionDraft(CHECKOUT_DRAFT_KEY, {
      ...existingDraft,
      shipping_method: selectedShippingMethod,
    })
    router.push('/checkout')
  }

  if (loading) {
    return <section className="card">載入購物車中...</section>
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h1>購物車</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!cart?.items.length ? (
          <div className="muted">你的購物車目前沒有商品。</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>商品</th>
                <th>數量</th>
                <th>小計</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cart.items.map((item) => (
                <tr key={item.key}>
                  <td>
                    <strong>{item.display_name}</strong>
                    <div className="muted">{item.sku ?? ''}</div>
                  </td>
                  <td>
                    <input
                      disabled={submitting}
                      min={0}
                      type="number"
                      value={item.qty}
                      onChange={(event) => updateQty(item.key, Number(event.target.value) || 0)}
                    />
                  </td>
                  <td>${item.line_total.toFixed(2)}</td>
                  <td>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => removeItem(item.key)} type="button">
                      移除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="grid grid-2">
        <section className="card stack">
          <h2>配送方式</h2>
          {!cart?.shipping_methods?.length ? (
            <div className="muted">目前沒有可用配送方式。</div>
          ) : (
            cart.shipping_methods.map((method) => (
              <label key={method.value}>
                <input
                  checked={selectedShippingMethod === method.value}
                  disabled={submitting || !cart.items.length}
                  name="shipping_method"
                  onChange={() => setSelectedShippingMethod(method.value)}
                  type="radio"
                />{' '}
                {method.label}
              </label>
            ))
          )}

          {cart?.seller_shipping_groups?.length ? (
            <div className="stack" style={{ gap: '0.75rem' }}>
              <strong>分賣家運費預估</strong>
              {cart.seller_shipping_groups.map((group) => (
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
                    <div className="notice">
                      這位賣家的商品不支援目前配送方式，請改選其他配送方式後再結帳。
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <section className="card grid grid-2">
          <div className="stack">
            <label className="field">
              <span>折扣碼</span>
              <input disabled={submitting} value={coupon} onChange={(event) => setCoupon(event.target.value)} />
            </label>
            <button className="btn btn-secondary" disabled={submitting || !cart} onClick={applyCoupon} type="button">
              {submitting ? '處理中...' : '套用折扣碼'}
            </button>
          </div>

          <div className="stack">
            <strong>小計 ${cart?.totals.subtotal ?? '0.00'}</strong>
            <span className="muted">運費 ${cart?.totals.shipping ?? '0.00'}</span>
            <span className="muted">折扣 -${cart?.totals.discount ?? '0.00'}</span>
            <strong>總計 ${cart?.totals.total ?? '0.00'}</strong>
            <button className="btn" disabled={!cart?.items.length || submitting} onClick={proceedToCheckout} type="button">
              前往結帳
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}

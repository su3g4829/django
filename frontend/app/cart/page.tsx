'use client'

/**
 * 購物車頁
 *
 * 功能：
 * - 顯示購物車內容
 * - 更新數量、移除項目、套用折扣碼
 * - 顯示 loading、submitting、error 狀態
 *
 * 主要 API：
 * - GET `/api/v1/cart/`
 * - PATCH `/api/v1/cart/items/:itemKey/`
 * - DELETE `/api/v1/cart/items/:itemKey/`
 * - POST `/api/v1/cart/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CartPayload } from '@/lib/types'

export default function CartPage() {
  /** 後端購物車 API 回傳的完整購物車資料。 */
  const [cart, setCart] = useState<CartPayload | null>(null)
  /** 折扣碼輸入框內容。 */
  const [coupon, setCoupon] = useState('')
  /** 載入或提交失敗時顯示的錯誤訊息。 */
  const [error, setError] = useState('')
  /** 首次讀取購物車資料時的 loading 狀態。 */
  const [loading, setLoading] = useState(true)
  /** 更新數量、刪除、套用折扣碼時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    /** 首次進頁面時，從 session 購物車載入最新內容。 */
    setLoading(true)
    apiFetch<CartPayload>('/cart/')
      .then((payload) => {
        setCart(payload)
        setCoupon(payload.coupon ?? '')
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  /**
   * 共用 mutation 包裝器，統一處理 submitting 與 error 狀態。
   *
   * task:
   * - 真正執行 API 寫入的非同步函式，成功後應回傳最新購物車資料。
   */
  async function withMutation(task: () => Promise<CartPayload>) {
    try {
      setSubmitting(true)
      setError('')
      const next = await task()
      setCart(next)
      setCoupon(next.coupon ?? '')
    } catch (err) {
      setError(err instanceof Error ? err.message : '購物車操作失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 更新單一購物車項目的數量。
   *
   * itemKey:
   * - 後端用來辨識購物車項目的唯一鍵值。
   * qty:
   * - 使用者想更新成的數量。
   */
  function updateQty(itemKey: string, qty: number) {
    return withMutation(() =>
      apiFetch<CartPayload>(`/cart/items/${encodeURIComponent(itemKey)}/`, {
        method: 'PATCH',
        body: JSON.stringify({ qty }),
      }),
    )
  }

  /**
   * 移除單一購物車項目。
   *
   * itemKey:
   * - 要刪除的購物車項目唯一鍵值。
   */
  function removeItem(itemKey: string) {
    return withMutation(() =>
      apiFetch<CartPayload>(`/cart/items/${encodeURIComponent(itemKey)}/`, {
        method: 'DELETE',
      }),
    )
  }

  /** 將目前 `coupon` state 套用到購物車。 */
  function applyCoupon() {
    return withMutation(() =>
      apiFetch<CartPayload>('/cart/', {
        method: 'POST',
        body: JSON.stringify({ code: coupon }),
      }),
    )
  }

  if (loading) {
    return <section className="card">載入購物車中…</section>
  }

  return (
    <div className="stack">
      {/* 購物車主表格：顯示商品、數量、金額與刪除操作。 */}
      <section className="card stack">
        <h1>購物車</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!cart?.items.length ? (
          <div className="muted">目前購物車是空的。</div>
        ) : (
          <table className="table">
            {/* 表頭：定義主清單欄位。 */}
            <thead>
              <tr>
                <th>商品</th>
                <th>數量</th>
                <th>小計</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {/* 每一列都是單一購物車項目，可直接調整數量或刪除。 */}
              {cart.items.map((item) => (
                <tr key={item.key}>
                  <td>
                    {/* 商品名稱與 SKU 摘要。 */}
                    <strong>{item.display_name}</strong>
                    <div className="muted">{item.sku ?? ''}</div>
                  </td>
                  <td>
                    {/* 數量輸入框：變更時即呼叫 PATCH 更新後端 cart item。 */}
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
                    {/* 單列刪除按鈕：對應 DELETE `/api/v1/cart/items/:itemKey/`。 */}
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

      {/* 結帳摘要：折扣碼、運費、總額與結帳按鈕。 */}
      <section className="card grid grid-2">
        <div className="stack">
          {/* 左欄：優惠碼輸入與套用操作。 */}
          <label className="field">
            <span>折扣碼</span>
            <input disabled={submitting} value={coupon} onChange={(event) => setCoupon(event.target.value)} />
          </label>
          <button className="btn btn-secondary" disabled={submitting || !cart} onClick={applyCoupon} type="button">
            {submitting ? '套用中…' : '套用折扣碼'}
          </button>
        </div>
        <div className="stack">
          {/* 右欄：金額總覽與導向結帳頁的 CTA。 */}
          <strong>小計 ${cart?.totals.subtotal ?? '0.00'}</strong>
          <span className="muted">運費 ${cart?.totals.shipping ?? '0.00'}</span>
          <span className="muted">折扣 -${cart?.totals.discount ?? '0.00'}</span>
          <strong>總計 ${cart?.totals.total ?? '0.00'}</strong>
          <a className="btn" href="/checkout">
            前往結帳
          </a>
        </div>
      </section>
    </div>
  )
}

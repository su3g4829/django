'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { apiFetch, dispatchAppBootstrapRefresh, toQueryString } from '@/lib/api'
import { getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { CartPayload } from '@/lib/types'

const DEFAULT_SHIPPING_METHOD = 'home_delivery'
const CHECKOUT_DRAFT_KEY = 'checkout-form'

export default function CartPage() {
  const router = useRouter()
  const [cart, setCart] = useState<CartPayload | null>(null)
  const [coupon, setCoupon] = useState('')
  const [selectedShippingMethod, setSelectedShippingMethod] = useState(DEFAULT_SHIPPING_METHOD)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [cartReady, setCartReady] = useState(false)

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

  useEffect(() => {
    if (!cartReady) {
      return
    }
    if (selectedShippingMethod === (cart?.selected_shipping_method ?? DEFAULT_SHIPPING_METHOD)) {
      return
    }
    void loadCart(selectedShippingMethod)
  }, [cart?.selected_shipping_method, cartReady, selectedShippingMethod])

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

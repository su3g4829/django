'use client'

/**
 * 結帳頁
 *
 * 功能：
 * - 顯示結帳預覽
 * - 顯示預設收件地址
 * - 送出確認下單
 *
 * 主要 API：
 * - GET `/api/v1/checkout/preview/`
 * - POST `/api/v1/checkout/confirm/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CartPayload, DemoUser, Order } from '@/lib/types'

type CheckoutPreviewPayload = CartPayload & {
  user: DemoUser | null
  requires_login: boolean
  can_confirm: boolean
  default_address?: Record<string, string> | null
}

export default function CheckoutPage() {
  /** 結帳預覽資料，包含購物車總額與預設地址。 */
  const [preview, setPreview] = useState<CheckoutPreviewPayload | null>(null)
  /** 首次載入結帳預覽時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 確認下單時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 成功建立訂單後顯示的提示訊息。 */
  const [message, setMessage] = useState('')
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    /** 進入頁面後先讀取結帳預覽資料。 */
    setLoading(true)
    apiFetch<CheckoutPreviewPayload>('/checkout/preview/')
      .then((payload) => {
        setPreview(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  /** 呼叫確認下單 API，成功後顯示訂單編號。 */
  async function confirmCheckout() {
    try {
      setSubmitting(true)
      const order = await apiFetch<Order>('/checkout/confirm/', { method: 'POST' })
      setMessage(`訂單已建立，訂單編號 #${order.id}`)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '結帳失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入結帳預覽中…</section>
  }

  return (
    <div className="grid grid-2">
      {/* 左欄：訂單摘要與確認下單主操作。 */}
      <section className="card stack">
        <h1>結帳預覽</h1>
        {preview?.requires_login ? <div className="notice">請先登入後再建立訂單。</div> : null}
        {error ? <div className="notice">{error}</div> : null}
        {message ? <div className="notice success">{message}</div> : null}
        <div className="muted">商品件數：{preview?.item_count ?? 0}</div>
        <div className="muted">訂單總額：${preview?.totals.total ?? '0.00'}</div>
        <button className="btn" disabled={!preview?.can_confirm || submitting} onClick={confirmCheckout} type="button">
          {submitting ? '建立訂單中…' : '確認下單'}
        </button>
      </section>

      {/* 右欄：顯示目前預設的收件地址快照。 */}
      <section className="card stack">
        <h2>收件地址</h2>
        {preview?.default_address ? (
          <div className="stack">
            {/* 地址摘要：供使用者確認本次配送資訊。 */}
            <div>{preview.default_address.recipient}</div>
            <div className="muted">
              {preview.default_address.city}
              {preview.default_address.district}
              {preview.default_address.address_line}
            </div>
          </div>
        ) : (
          <p className="muted">目前尚未設定預設收件地址。</p>
        )}
      </section>
    </div>
  )
}

'use client'

/**
 * 管理者審核台頁
 *
 * 功能：
 * - 顯示待審商品與賣家申請
 * - 提供審核操作
 *
 * 主要 API：
 * - GET `/api/v1/staff/reviews/`
 * - POST `/api/v1/staff/products/:slug/review/`
 * - POST `/api/v1/staff/seller-requests/:username/review/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { StaffReviewDashboard } from '@/lib/types'

export default function StaffReviewsPage() {
  /** 審核台資料，包含賣家申請與待審商品。 */
  const [data, setData] = useState<StaffReviewDashboard | null>(null)
  /** 初次載入審核台時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 執行審核時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /** 載入審核台資料。 */
  async function loadDashboard() {
    setLoading(true)
    try {
      const payload = await apiFetch<StaffReviewDashboard>('/staff/reviews/')
      setData(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入審核資料失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDashboard()
  }, [])

  /**
   * 審核賣家申請。
   *
   * username:
   * - 要審核的使用者帳號。
   * approved:
   * - `true` 代表核准，`false` 代表駁回。
   */
  async function reviewSeller(username: string, approved: boolean) {
    try {
      setSubmitting(true)
      await apiFetch(`/staff/seller-requests/${username}/review/`, {
        method: 'POST',
        body: JSON.stringify({ approved }),
      })
      await loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : '審核賣家申請失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 審核商品上架申請。
   *
   * slug:
   * - 要審核的商品 slug。
   * approved:
   * - `true` 代表核准，`false` 代表駁回。
   */
  async function reviewProduct(slug: string, approved: boolean) {
    try {
      setSubmitting(true)
      await apiFetch(`/staff/products/${slug}/review/`, {
        method: 'POST',
        body: JSON.stringify({
          approved,
          note: approved ? 'Approved in Next.js frontend.' : 'Rejected in Next.js frontend.',
        }),
      })
      await loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : '審核商品失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入審核台中…</section>
  }

  return (
    <div className="grid grid-2">
      {/* 左欄：賣家申請審核。 */}
      <section className="card stack">
        <h1>賣家申請審核</h1>
        {error ? <div className="notice">{error}</div> : null}
        {!data?.seller_requests.length ? (
          <div className="muted">目前沒有待審核的賣家申請。</div>
        ) : (
          data.seller_requests.map((user) => (
            <div className="card stack" key={user.username}>
              {/* 單筆賣家申請卡：帳號、顯示名稱與核准/駁回。 */}
              <strong>{user.display_name}</strong>
              <div className="muted">@{user.username}</div>
              <div className="row">
                <button className="btn" disabled={submitting} onClick={() => reviewSeller(user.username, true)} type="button">
                  核准
                </button>
                <button className="btn btn-secondary" disabled={submitting} onClick={() => reviewSeller(user.username, false)} type="button">
                  駁回
                </button>
              </div>
            </div>
          ))
        )}
      </section>

      {/* 右欄：商品上架審核。 */}
      <section className="card stack">
        <h1>商品上架審核</h1>
        {!data?.pending_products.length ? (
          <div className="muted">目前沒有待審核商品。</div>
        ) : (
          data.pending_products.map((product) => (
            <div className="card stack" key={product.slug}>
              {/* 單筆待審商品卡：品牌、分類與審核操作。 */}
              <strong>{product.name}</strong>
              <div className="muted">
                {product.brand} ｜ {product.category}
              </div>
              <div className="row">
                <button className="btn" disabled={submitting} onClick={() => reviewProduct(product.slug, true)} type="button">
                  核准
                </button>
                <button className="btn btn-secondary" disabled={submitting} onClick={() => reviewProduct(product.slug, false)} type="button">
                  駁回
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

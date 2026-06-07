'use client'

/**
 * 管理端快速審核頁。
 *
 * 這頁聚合兩種常見處理：
 * - 賣家申請審核
 * - 商品快速下架
 */

/**
 * 管理者處理台頁
 *
 * 功能：
 * - 顯示賣家申請
 * - 顯示目前已上架商品，提供強制下架操作
 *
 * 主要 API：
 * - GET `/api/v1/staff/reviews/`
 * - POST `/api/v1/staff/products/:slug/archive/`
 * - POST `/api/v1/staff/seller-requests/:username/review/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { StaffReviewDashboard } from '@/lib/types'

export default function StaffReviewsPage() {
  // 這頁走 dashboard 型 payload，一次抓回待審賣家與待管理商品。
  /** 處理台資料，包含賣家申請與商品管理清單。 */
  const [data, setData] = useState<StaffReviewDashboard | null>(null)
  /** 初次載入審核台時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 執行審核時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /** 載入審核台資料。 */
  async function loadDashboard() {
    // 每次審核或下架後都重新抓 dashboard，避免前端自行拼接結果。
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
    // 審核賣家後直接重整 dashboard，讓待審列表即時更新。
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

  /** 管理者強制下架商品。 */
  async function archiveProduct(slug: string) {
    // 這裡提供管理者快速下架入口，不需要跳到商品管理頁。
    try {
      setSubmitting(true)
      await apiFetch(`/staff/products/${slug}/archive/`, {
        method: 'POST',
        body: JSON.stringify({
          note: 'Forced down in admin panel.',
        }),
      })
      await loadDashboard()
    } catch (err) {
      setError(err instanceof Error ? err.message : '商品下架失敗，請稍後再試。')
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

      {/* 右欄：商品上架管理，管理者可直接強制下架。 */}
      <section className="card stack">
        <h1>商品上架管理</h1>
        {!data?.managed_products.length ? (
          <div className="muted">目前沒有已上架商品。</div>
        ) : (
          data.managed_products.map((product) => (
            <div className="card stack" key={product.slug}>
              {/* 單筆上架商品卡：顯示商品摘要與強制下架按鈕。 */}
              <strong>{product.name}</strong>
              <div className="muted">
                {product.brand} ｜ {product.category} ｜ {product.status_label ?? product.status}
              </div>
              <div className="row">
                <button className="btn btn-secondary" disabled={submitting} onClick={() => archiveProduct(product.slug)} type="button">
                  強制下架
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}

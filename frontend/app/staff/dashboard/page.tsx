'use client'

/**
 * 管理後台首頁
 *
 * 功能：
 * - 顯示平台整體摘要數據
 * - 作為管理功能入口
 *
 * 主要 API：
 * - GET `/api/v1/staff/dashboard/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { AdminDashboard } from '@/lib/types'

export default function StaffDashboardPage() {
  /** 管理後台摘要資料。 */
  const [data, setData] = useState<AdminDashboard | null>(null)
  /** 初次載入儀表板時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    /** 載入管理後台首頁摘要資料。 */
    setLoading(true)
    apiFetch<AdminDashboard>('/staff/dashboard/')
      .then((payload) => {
        setData(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <section className="card">載入管理後台中…</section>
  }

  return (
    <div className="stack">
      {/* 後台頁首說明。 */}
      <section className="hero">
        <h1>管理後台</h1>
        <p className="muted">這裡顯示平台整體摘要資訊，資料來源為 Django DRF `/api/v1/staff/dashboard/`。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data ? null : (
        <>
          {/* 核心統計卡片：會員、商品、訂單、內容總數。 */}
          <section className="grid grid-4">
            <div className="card stack">
              <span className="muted">會員</span>
              <strong>{String(data.users.total ?? '-')}</strong>
            </div>
            <div className="card stack">
              <span className="muted">商品</span>
              <strong>{String(data.products.total ?? '-')}</strong>
            </div>
            <div className="card stack">
              <span className="muted">訂單</span>
              <strong>{String(data.orders.total ?? '-')}</strong>
            </div>
            <div className="card stack">
              <span className="muted">內容</span>
              <strong>{String(data.content.total ?? '-')}</strong>
            </div>
          </section>

          {/* 最近活動摘要：最新評論、提問、論壇文章。 */}
          <section className="grid grid-3">
            <div className="card stack">
              {/* 最新評論清單。 */}
              <h2>最新評論</h2>
              {data.recent_reviews.length ? (
                data.recent_reviews.map((item, index) => (
                  <div className="muted" key={`review-${index}`}>
                    {String(item.title ?? '未命名評論')}
                  </div>
                ))
              ) : (
                <div className="muted">目前沒有資料。</div>
              )}
            </div>
            <div className="card stack">
              {/* 最新提問清單。 */}
              <h2>最新提問</h2>
              {data.recent_questions.length ? (
                data.recent_questions.map((item, index) => (
                  <div className="muted" key={`question-${index}`}>
                    {String(item.title ?? '未命名提問')}
                  </div>
                ))
              ) : (
                <div className="muted">目前沒有資料。</div>
              )}
            </div>
            <div className="card stack">
              {/* 最新論壇文章清單。 */}
              <h2>最新論壇文章</h2>
              {data.recent_posts.length ? (
                data.recent_posts.map((item, index) => (
                  <div className="muted" key={`post-${index}`}>
                    {String(item.title ?? '未命名文章')}
                  </div>
                ))
              ) : (
                <div className="muted">目前沒有資料。</div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

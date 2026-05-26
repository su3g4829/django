'use client'

/**
 * 會員中心首頁
 *
 * 功能：
 * - 顯示會員摘要資訊
 * - 顯示收藏、最近瀏覽、我的商品與互動統計
 *
 * 主要 API：
 * - GET `/api/v1/me/dashboard/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { MeDashboard } from '@/lib/types'

export default function MeDashboardPage() {
  /** 會員中心儀表板資料。 */
  const [data, setData] = useState<MeDashboard | null>(null)
  /** 初次載入儀表板時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    /** 載入會員中心首頁摘要資料。 */
    setLoading(true)
    apiFetch<MeDashboard>('/me/dashboard/')
      .then((payload) => {
        setData(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <section className="card">載入會員中心中…</section>
  }

  return (
    <div className="stack">
      {/* 頁首說明。 */}
      <section className="hero">
        <h1>會員中心</h1>
        <p className="muted">這裡彙整目前登入者的互動統計、收藏商品、最近瀏覽與我的商品摘要。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data ? null : (
        <>
          {/* 互動統計數字卡：快速查看評論、提問、回答、文章數量。 */}
          <section className="grid grid-4">
            <div className="card stack">
              <span className="muted">評論</span>
              <strong>{data.review_count}</strong>
            </div>
            <div className="card stack">
              <span className="muted">提問</span>
              <strong>{data.question_count}</strong>
            </div>
            <div className="card stack">
              <span className="muted">回答</span>
              <strong>{data.answer_count}</strong>
            </div>
            <div className="card stack">
              <span className="muted">論壇文章</span>
              <strong>{data.post_count}</strong>
            </div>
          </section>

          {/* 個人內容摘要：收藏、最近瀏覽、我的商品。 */}
          <section className="grid grid-3">
            <div className="card stack">
              {/* 收藏商品列表。 */}
              <h2>收藏商品</h2>
              {!data.favorite_products.length ? (
                <div className="muted">目前沒有收藏商品。</div>
              ) : (
                data.favorite_products.map((item) => (
                  <a href={`/products/${item.slug}`} key={item.slug}>
                    {item.name}
                  </a>
                ))
              )}
            </div>

            <div className="card stack">
              {/* 最近瀏覽商品列表。 */}
              <h2>最近瀏覽</h2>
              {!data.recent_products.length ? (
                <div className="muted">目前沒有最近瀏覽紀錄。</div>
              ) : (
                data.recent_products.map((item) => (
                  <a href={`/products/${item.slug}`} key={item.slug}>
                    {item.name}
                  </a>
                ))
              )}
            </div>

            <div className="card stack">
              {/* 我的商品摘要：賣家可快速進入編輯頁。 */}
              <h2>我的商品</h2>
              {!data.owned_products.length ? (
                <div className="muted">目前沒有管理中的商品。</div>
              ) : (
                data.owned_products.map((item) => (
                  <a href={`/me/products/${item.slug}`} key={item.slug}>
                    {item.name}
                  </a>
                ))
              )}
            </div>
          </section>

          {/* 快速入口：導向訂單、會員資料、地址與商品管理。 */}
          <section className="card stack">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h2>快速操作</h2>
              <span className="muted">訂單數：{data.order_count}</span>
            </div>
            <div className="row">
              <a className="btn btn-secondary" href="/orders">
                查看訂單
              </a>
              <a className="btn btn-secondary" href="/me/profile">
                編輯會員資料
              </a>
              <a className="btn btn-secondary" href="/me/addresses">
                管理地址
              </a>
              <a className="btn btn-secondary" href="/me/products">
                管理商品
              </a>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

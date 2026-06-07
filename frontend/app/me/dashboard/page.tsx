'use client'

/**
 * Next.js App Router 的 `use client` 指示詞。
 *
 * 來源：
 * - Next.js App Router 規範
 *
 * 用法：
 * - 放在檔案第一行，表示這個頁面要在瀏覽器端執行。
 * - 本頁使用 React hook 與瀏覽器互動，因此不能維持純 Server Component。
 */

/**
 * 會員中心 dashboard 頁面。
 *
 * 功能：
 * - 顯示會員摘要統計
 * - 顯示收藏、最近瀏覽、自己擁有的商品
 * - 提供訂單與會員設定快捷入口
 *
 * API：
 * - `GET /api/v1/me/dashboard/`
 */

import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { MeDashboard } from '@/lib/types'

export default function MeDashboardPage() {
  /**
   * React `useState` hook。
   *
   * 來源：
   * - `react`
   *
   * 用法：
   * - `useState<T>(initialValue)` 會回傳 `[state, setState]`
   * - `MeDashboard | null` 是 TypeScript union type，表示資料尚未載入完成前可以先是 `null`
   */
  const [data, setData] = useState<MeDashboard | null>(null)
  /** 控制載入中 UI。 */
  const [loading, setLoading] = useState(true)
  /** 儲存 API 失敗訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    /**
     * `useEffect(..., [])` 代表元件第一次掛載後執行一次。
     *
     * 為什麼抓資料放這裡：
     * - render 階段應保持純函式，不應直接觸發副作用
     * - API 請求屬於副作用，因此要放進 effect
     */
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
    return <section className="card">載入會員中心資料中...</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>會員中心</h1>
        <p className="muted">這頁會聚合會員主頁常用統計與捷徑，避免前端一次打很多零碎 API。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data ? null : (
        <>
          {/* KPI 區：顯示純數值統計。 */}
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
              <span className="muted">社群文章</span>
              <strong>{data.post_count}</strong>
            </div>
          </section>

          <section className="grid grid-3">
            <div className="card stack">
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
              <h2>我的商品</h2>
              {!data.owned_products.length ? (
                <div className="muted">目前沒有自己擁有的商品。</div>
              ) : (
                data.owned_products.map((item) => (
                  <a href={`/me/products/${item.slug}`} key={item.slug}>
                    {item.name}
                  </a>
                ))
              )}
            </div>
          </section>

          <section className="card stack">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h2>快速入口</h2>
              <span className="muted">訂單數：{data.order_count}</span>
            </div>
            <div className="row">
              <a className="btn btn-secondary" href="/orders">
                我的訂單
              </a>
              <a className="btn btn-secondary" href="/me/profile">
                會員資料
              </a>
              <a className="btn btn-secondary" href="/me/addresses">
                地址管理
              </a>
              <a className="btn btn-secondary" href="/me/products">
                我的商品
              </a>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

'use client'

import Link from 'next/link'
import { type ReactNode, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'

type SummaryCounts = Record<string, string | number>

type DashboardReviewItem = {
  id: number
  title: string
  author: string
  created_at_display?: string
  rating?: number
  product_name?: string
  source_url?: string
  management_url?: string
}

type DashboardQuestionItem = {
  id: number
  title: string
  author: string
  created_at_display?: string
  answer_count?: number
  product_name?: string
  source_url?: string
  management_url?: string
}

type DashboardPostItem = {
  id: number
  title: string
  author: string
  created_at_display?: string
  topic?: string
  reply_count?: number
  source_url?: string
  management_url?: string
}

type AdminDashboardPayload = {
  users: SummaryCounts
  products: SummaryCounts
  orders: SummaryCounts
  content: SummaryCounts
  recent_reviews: DashboardReviewItem[]
  recent_questions: DashboardQuestionItem[]
  recent_posts: DashboardPostItem[]
}

function MetricCard({
  href,
  label,
  value,
  detail,
}: {
  href: string
  label: string
  value: string
  detail: string
}) {
  return (
    <Link className="card stack summary-card" href={href}>
      <span className="muted">{label}</span>
      <strong>{value}</strong>
      <span className="muted">{detail}</span>
    </Link>
  )
}

function EmptyState({ children }: { children: ReactNode }) {
  return <div className="muted">{children}</div>
}

export default function StaffDashboardPage() {
  const [data, setData] = useState<AdminDashboardPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true)
    apiFetch<AdminDashboardPayload>('/staff/dashboard/')
      .then((payload) => {
        setData(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <section className="card">載入管理後台摘要中...</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>管理後台</h1>
        <p className="muted">這裡集中顯示平台會員、商品、訂單與站內內容的管理摘要，並可直接跳到對應管理頁。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {!data ? null : (
        <>
          <section className="grid grid-4">
            <MetricCard
              href="/staff/users"
              label="會員"
              value={String(data.users.total ?? '-')}
              detail={`啟用 ${String(data.users.active ?? 0)} / 停權 ${String(data.users.suspended ?? 0)}`}
            />
            <MetricCard
              href="/staff/products"
              label="商品"
              value={String(data.products.total ?? '-')}
              detail={`上架 ${String(data.products.active ?? 0)} / 草稿 ${String(data.products.draft ?? 0)}`}
            />
            <MetricCard
              href="/staff/orders"
              label="訂單"
              value={String(data.orders.total ?? '-')}
              detail={`待處理 ${String(data.orders.pending ?? 0)} / 已完成 ${String(data.orders.completed ?? 0)}`}
            />
            <div className="card stack">
              <span className="muted">內容</span>
              <div className="dashboard-stat-list">
                <Link href="/staff/content/reviews">評論 {String(data.content.reviews ?? 0)}</Link>
                <Link href="/staff/content/questions">提問 {String(data.content.questions ?? 0)}</Link>
                <Link href="/staff/content/posts">文章 {String(data.content.posts ?? 0)}</Link>
              </div>
              <span className="muted">總計 {String(data.content.total ?? 0)}</span>
            </div>
          </section>

          <section className="grid grid-3">
            <div className="card stack">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <h2>最新評論</h2>
                <Link href="/staff/content/reviews">查看全部</Link>
              </div>
              {!data.recent_reviews.length ? (
                <EmptyState>目前沒有評論資料。</EmptyState>
              ) : (
                data.recent_reviews.map((item) => (
                  <div className="card stack" key={`review-${item.id}`}>
                    <strong>{item.title}</strong>
                    <div className="muted">
                      {item.author} · {item.product_name || '未知商品'} · {item.created_at_display || '-'}
                    </div>
                    <div className="row">
                      {item.source_url ? <Link href={item.source_url}>前往原始內容</Link> : null}
                      <span className="badge">{item.rating ?? 0} / 5</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="card stack">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <h2>最新提問</h2>
                <Link href="/staff/content/questions">查看全部</Link>
              </div>
              {!data.recent_questions.length ? (
                <EmptyState>目前沒有提問資料。</EmptyState>
              ) : (
                data.recent_questions.map((item) => (
                  <div className="card stack" key={`question-${item.id}`}>
                    <strong>{item.title}</strong>
                    <div className="muted">
                      {item.author} · {item.product_name || '未知商品'} · {item.created_at_display || '-'}
                    </div>
                    <div className="row">
                      {item.source_url ? <Link href={item.source_url}>前往原始內容</Link> : null}
                      <span className="badge">回答 {item.answer_count ?? 0}</span>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="card stack">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <h2>最新論壇文章</h2>
                <Link href="/staff/content/posts">查看全部</Link>
              </div>
              {!data.recent_posts.length ? (
                <EmptyState>目前沒有論壇文章。</EmptyState>
              ) : (
                data.recent_posts.map((item) => (
                  <div className="card stack" key={`post-${item.id}`}>
                    <strong>{item.title}</strong>
                    <div className="muted">
                      {item.author} · {item.created_at_display || '-'}
                    </div>
                    <div className="row">
                      {item.source_url ? <Link href={item.source_url}>前往原始內容</Link> : null}
                      <span className="badge">
                        {item.topic || 'general'} / 回覆 {item.reply_count ?? 0}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </>
      )}
    </div>
  )
}

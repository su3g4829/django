'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'

type AdminReview = {
  id: number
  title: string
  body: string
  author: string
  rating: number
  product_name?: string
  source_url?: string
  created_at_display?: string
}

type ReviewListPayload = {
  items: AdminReview[]
}

type ReviewSortKey = 'created_desc' | 'created_asc' | 'rating_desc' | 'rating_asc' | 'title_asc'

export default function AdminReviewManagementPage() {
  const [items, setItems] = useState<AdminReview[]>([])
  const [filters, setFilters] = useState({ q: '', rating: '' })
  const [sortBy, setSortBy] = useState<ReviewSortKey>('created_desc')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadItems(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<ReviewListPayload>(`/staff/content/reviews/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取評論列表失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadItems()
  }, [])

  const sortedItems = useMemo(() => {
    const next = [...items]
    switch (sortBy) {
      case 'created_asc':
        next.sort((a, b) => String(a.created_at_display || '').localeCompare(String(b.created_at_display || '')))
        break
      case 'rating_desc':
        next.sort((a, b) => b.rating - a.rating)
        break
      case 'rating_asc':
        next.sort((a, b) => a.rating - b.rating)
        break
      case 'title_asc':
        next.sort((a, b) => a.title.localeCompare(b.title))
        break
      case 'created_desc':
      default:
        next.sort((a, b) => String(b.created_at_display || '').localeCompare(String(a.created_at_display || '')))
        break
    }
    return next
  }, [items, sortBy])

  async function deleteItem(reviewId: number) {
    if (!window.confirm('確定要刪除這筆評論嗎？')) {
      return
    }
    try {
      setSubmitting(true)
      await apiFetch(`/staff/content/reviews/${reviewId}/`, { method: 'DELETE' })
      await loadItems(filters)
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除評論失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <h1>評論總覽</h1>

      <div className="grid grid-3">
        <label className="field">
          <span>搜尋關鍵字</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="評論標題、商品名稱、作者"
          />
        </label>
        <label className="field">
          <span>評分</span>
          <select value={filters.rating} onChange={(event) => setFilters((prev) => ({ ...prev, rating: event.target.value }))}>
            <option value="">全部評分</option>
            <option value="5">5 分</option>
            <option value="4">4 分</option>
            <option value="3">3 分</option>
            <option value="2">2 分</option>
            <option value="1">1 分</option>
          </select>
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as ReviewSortKey)}>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="rating_desc">評分：高到低</option>
            <option value="rating_asc">評分：低到高</option>
            <option value="title_asc">標題：A 到 Z</option>
          </select>
        </label>
      </div>

      <div className="row">
        <button className="btn btn-secondary" onClick={() => void loadItems(filters)} type="button">
          套用篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">正在讀取評論列表...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的評論。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>標題</th>
              <th>商品</th>
              <th>作者</th>
              <th>評分</th>
              <th>建立時間</th>
              <th>內容</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item) => (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{item.product_name || '-'}</td>
                <td>{item.author}</td>
                <td>{item.rating} / 5</td>
                <td>{item.created_at_display || '-'}</td>
                <td>{item.body}</td>
                <td>
                  <div className="stack" style={{ gap: '0.5rem' }}>
                    {item.source_url ? <Link href={item.source_url}>查看原始內容</Link> : null}
                    <button className="btn btn-danger" disabled={submitting} onClick={() => void deleteItem(item.id)} type="button">
                      刪除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

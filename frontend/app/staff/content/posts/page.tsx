'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'

type AdminPost = {
  id: number
  title: string
  body: string
  author: string
  topic: string
  reply_count: number
  source_url?: string
  created_at_display?: string
}

type PostListPayload = {
  items: AdminPost[]
}

type PostSortKey = 'created_desc' | 'created_asc' | 'replies_desc' | 'replies_asc' | 'title_asc'

export default function AdminPostManagementPage() {
  const [items, setItems] = useState<AdminPost[]>([])
  const [filters, setFilters] = useState({ q: '', topic: '' })
  const [sortBy, setSortBy] = useState<PostSortKey>('created_desc')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadItems(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<PostListPayload>(`/staff/content/posts/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取論壇文章失敗。')
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
      case 'replies_desc':
        next.sort((a, b) => b.reply_count - a.reply_count)
        break
      case 'replies_asc':
        next.sort((a, b) => a.reply_count - b.reply_count)
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

  async function deleteItem(postId: number) {
    if (!window.confirm('確定要刪除這篇論壇文章嗎？')) {
      return
    }
    try {
      setSubmitting(true)
      await apiFetch(`/staff/content/posts/${postId}/`, { method: 'DELETE' })
      await loadItems(filters)
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除論壇文章失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <h1>論壇文章總覽</h1>

      <div className="grid grid-3">
        <label className="field">
          <span>搜尋關鍵字</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="文章標題、作者、主題分類"
          />
        </label>
        <label className="field">
          <span>主題分類</span>
          <input value={filters.topic} onChange={(event) => setFilters((prev) => ({ ...prev, topic: event.target.value }))} />
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as PostSortKey)}>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="replies_desc">回覆數：多到少</option>
            <option value="replies_asc">回覆數：少到多</option>
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
        <div className="muted">正在讀取論壇文章...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的論壇文章。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>標題</th>
              <th>作者</th>
              <th>主題分類</th>
              <th>回覆數</th>
              <th>建立時間</th>
              <th>內容</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item) => (
              <tr key={item.id}>
                <td>{item.title}</td>
                <td>{item.author}</td>
                <td>{item.topic}</td>
                <td>{item.reply_count}</td>
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

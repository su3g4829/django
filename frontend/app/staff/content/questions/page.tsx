'use client'

/**
 * 管理端商品問答管理頁。
 *
 * 讓管理者依關鍵字與回答狀態篩選，
 * 並清理不適合保留的提問。
 */

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'

type AdminQuestion = {
  id: number
  title: string
  body: string
  author: string
  answer_count: number
  is_answered: boolean
  product_name?: string
  source_url?: string
  created_at_display?: string
}

type QuestionListPayload = {
  items: AdminQuestion[]
}

type QuestionSortKey = 'created_desc' | 'created_asc' | 'answers_desc' | 'answers_asc' | 'title_asc'

export default function AdminQuestionManagementPage() {
  // 問答列表、篩選條件與排序條件拆開保存，方便重查與重排。
  const [items, setItems] = useState<AdminQuestion[]>([])
  const [filters, setFilters] = useState({ q: '', answered: '' })
  const [sortBy, setSortBy] = useState<QuestionSortKey>('created_desc')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadItems(nextFilters = filters) {
    // 列表查詢交給後端，前端只做展示排序與過濾條件輸入。
    setLoading(true)
    try {
      const payload = await apiFetch<QuestionListPayload>(`/staff/content/questions/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取提問列表失敗。')
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
      case 'answers_desc':
        next.sort((a, b) => b.answer_count - a.answer_count)
        break
      case 'answers_asc':
        next.sort((a, b) => a.answer_count - b.answer_count)
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

  async function deleteItem(questionId: number) {
    // 刪除提問後重抓列表，讓回答數與已回答狀態保持同步。
    if (!window.confirm('確定要刪除這筆提問嗎？')) {
      return
    }
    try {
      setSubmitting(true)
      await apiFetch(`/staff/content/questions/${questionId}/`, { method: 'DELETE' })
      await loadItems(filters)
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除提問失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <h1>提問總覽</h1>

      <div className="grid grid-3">
        <label className="field">
          <span>搜尋關鍵字</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="提問標題、商品名稱、作者"
          />
        </label>
        <label className="field">
          <span>回答狀態</span>
          <select value={filters.answered} onChange={(event) => setFilters((prev) => ({ ...prev, answered: event.target.value }))}>
            <option value="">全部狀態</option>
            <option value="answered">已回答</option>
            <option value="unanswered">未回答</option>
          </select>
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as QuestionSortKey)}>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="answers_desc">回答數：多到少</option>
            <option value="answers_asc">回答數：少到多</option>
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
        <div className="muted">正在讀取提問列表...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的提問。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>標題</th>
              <th>商品</th>
              <th>作者</th>
              <th>回答數</th>
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
                <td>{item.answer_count}</td>
                <td>{item.created_at_display || '-'}</td>
                <td>{item.body}</td>
                <td>
                  <div className="stack" style={{ gap: '0.5rem' }}>
                    {item.source_url ? <Link href={item.source_url}>查看原始內容</Link> : null}
                    <span className="badge">{item.is_answered ? '已回答' : '未回答'}</span>
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

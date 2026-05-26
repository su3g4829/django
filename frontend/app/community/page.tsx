'use client'

/**
 * 社群文章列表頁
 *
 * 功能：
 * - 顯示社群文章列表
 * - 提供發文表單
 * - 顯示 loading 與 error 狀態
 *
 * 主要 API：
 * - GET `/api/v1/community/posts/`
 * - POST `/api/v1/community/posts/`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CommunityPost, CommunityPostListPayload } from '@/lib/types'

export default function CommunityPage() {
  /** 社群文章列表。 */
  const [posts, setPosts] = useState<CommunityPost[]>([])
  /** 首次載入文章列表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 發文時避免重複提交。 */
  const [submitting, setSubmitting] = useState(false)
  /** 列表或送出失敗時的錯誤訊息。 */
  const [error, setError] = useState('')
  /** 發文表單內容。 */
  const [form, setForm] = useState({ topic: 'general', title: '', body: '', tags: '' })

  /** 重新載入社群文章列表。 */
  async function loadPosts() {
    setLoading(true)
    try {
      const payload = await apiFetch<CommunityPostListPayload>('/community/posts/')
      setPosts(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入社群文章失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPosts()
  }, [])

  /**
   * 提交新增文章表單。
   *
   * event:
   * - form submit 事件，需先阻止預設送出行為。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      await apiFetch('/community/posts/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      setForm({ topic: 'general', title: '', body: '', tags: '' })
      await loadPosts()
    } catch (err) {
      setError(err instanceof Error ? err.message : '發文失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入社群文章中…</section>
  }

  return (
    <div className="stack">
      {/* 頁首說明：交代這裡是前端論壇首頁。 */}
      <section className="hero">
        <h1>社群論壇</h1>
        <p className="muted">這裡顯示由 Next.js 呈現的社群文章列表，資料由 Django DRF API 提供。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {/* 發文表單區：建立新文章。 */}
      <section className="card stack">
        <h2>新增文章</h2>
        <form className="stack" onSubmit={handleSubmit}>
          {/* 文章基本欄位：分類、標題、內容、標籤。 */}
          <label className="field">
            <span>主題分類</span>
            <input value={form.topic} onChange={(event) => setForm((prev) => ({ ...prev, topic: event.target.value }))} />
          </label>
          <label className="field">
            <span>標題</span>
            <input value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} />
          </label>
          <label className="field">
            <span>內容</span>
            <textarea value={form.body} onChange={(event) => setForm((prev) => ({ ...prev, body: event.target.value }))} rows={5} />
          </label>
          <label className="field">
            <span>標籤</span>
            <input value={form.tags} onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))} />
          </label>
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '送出中…' : '發表文章'}
          </button>
        </form>
      </section>

      {/* 文章列表區：逐筆顯示文章摘要與詳情入口。 */}
      <section className="stack">
        {posts.map((post) => (
          <article className="card stack" key={post.id}>
            {/* 文章摘要卡：標題、分類、作者、票數與回覆數。 */}
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <strong>{post.title}</strong>
              <span className="badge">{post.topic}</span>
            </div>
            <div className="muted">作者：{post.author} ｜ 讚數：{post.votes} ｜ 回覆：{post.reply_count ?? 0}</div>
            <p>{post.body}</p>
            <a className="btn btn-secondary" href={`/community/${post.id}`}>
              查看文章
            </a>
          </article>
        ))}
      </section>
    </div>
  )
}

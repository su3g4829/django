'use client'

/**
 * 社群文章詳情頁
 *
 * 功能：
 * - 顯示單篇社群文章內容
 * - 顯示回覆列表
 * - 提供新增回覆功能
 *
 * 主要 API：
 * - GET `/api/v1/community/posts/:id/`
 * - POST `/api/v1/community/posts/:id/replies/`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CommunityPost } from '@/lib/types'

type CommunityDetailProps = {
  /** `id` 來自 `/community/[id]` 動態路由。 */
  params: Promise<{ id: string }>
}

export default function CommunityDetailPage({ params }: CommunityDetailProps) {
  /** 目前文章 id，會從動態路由解析而來。 */
  const [postId, setPostId] = useState<number | null>(null)
  /** 單篇文章詳情資料。 */
  const [post, setPost] = useState<CommunityPost | null>(null)
  /** 首次載入文章詳情時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 送出回覆或按讚時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 畫面上的錯誤訊息。 */
  const [error, setError] = useState('')
  /** 回覆表單內容。 */
  const [replyBody, setReplyBody] = useState('')

  useEffect(() => {
    params.then(({ id }) => setPostId(Number(id)))
  }, [params])

  /** 依文章 id 載入單篇文章詳情。 */
  async function loadPost(id: number) {
    setLoading(true)
    try {
      const payload = await apiFetch<CommunityPost>(`/community/posts/${id}/`)
      setPost(payload)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入文章失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (postId) {
      loadPost(postId)
    }
  }, [postId])

  /**
   * 提交新增回覆表單。
   *
   * event:
   * - form submit 事件，需先阻止頁面重新整理。
   */
  async function handleReplySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!postId) return
    try {
      setSubmitting(true)
      await apiFetch(`/community/posts/${postId}/replies/`, {
        method: 'POST',
        body: JSON.stringify({ body: replyBody }),
      })
      setReplyBody('')
      await loadPost(postId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出回覆失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /** 對目前文章送出按讚操作。 */
  async function vote() {
    if (!postId) return
    try {
      setSubmitting(true)
      await apiFetch(`/community/posts/${postId}/vote/`, { method: 'POST' })
      await loadPost(postId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '按讚失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading || !post) {
    return <section className="card">載入文章內容中…</section>
  }

  return (
    <div className="stack">
      {/* 頁首摘要：文章標題、作者、主題與投票數。 */}
      <section className="hero">
        <h1>{post.title}</h1>
        <p className="muted">作者：{post.author} ｜ 主題：{post.topic} ｜ 讚數：{post.votes}</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {/* 文章本文與按讚操作。 */}
      <section className="card stack">
        <p>{post.body}</p>
        <div className="row">
          <button className="btn btn-secondary" disabled={submitting} onClick={vote} type="button">
            按讚
          </button>
        </div>
      </section>

      {/* 回覆表單：對目前文章新增一則回覆。 */}
      <section className="card stack">
        <h2>新增回覆</h2>
        <form className="stack" onSubmit={handleReplySubmit}>
          <label className="field">
            <span>回覆內容</span>
            <textarea rows={4} value={replyBody} onChange={(event) => setReplyBody(event.target.value)} />
          </label>
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '送出中…' : '送出回覆'}
          </button>
        </form>
      </section>

      {/* 回覆列表：顯示所有已送出的回覆內容。 */}
      <section className="stack">
        <h2>回覆列表</h2>
        {!post.replies?.length ? (
          <div className="card muted">目前還沒有任何回覆。</div>
        ) : (
          post.replies.map((reply) => (
            <article className="card stack" key={reply.id}>
              <strong>{reply.author}</strong>
              <div className="muted">{reply.created_at_display ?? reply.created_at}</div>
              <p>{reply.body}</p>
            </article>
          ))
        )}
      </section>
    </div>
  )
}

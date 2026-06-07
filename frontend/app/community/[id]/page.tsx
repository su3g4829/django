'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 讀 route params 與 query string
 * - 維護編輯器與回覆表單 state
 * - 執行文章 CRUD 與投票
 *
 * 因此必須是 Client Component。
 */

/**
 * 社群文章詳情頁。
 *
 * 這頁同時處理：
 * - 單篇文章讀取
 * - 回覆送出
 * - 作者編輯 / 刪除
 * - 投票更新
 *
 * 來源：
 * - `useRouter` / `useSearchParams` 來自 `next/navigation`
 * - `RichTextEditor` / `RichTextContent` 來自本專案共用元件
 */

import { FormEvent, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

import { RichTextContent } from '@/components/rich-text-content'
import { RichTextEditor } from '@/components/rich-text-editor'
import { apiFetch } from '@/lib/api'
import { uploadCommunityEditorImage } from '@/lib/community-editor'
import { hasMeaningfulRichText, prepareRichTextForStorage } from '@/lib/rich-text'
import type { CommunityPost } from '@/lib/types'

type CommunityDetailProps = {
  params: Promise<{ id: string }>
}

type CommunityPostFormState = {
  topic: string
  title: string
  body: string
  tags: string
}

const EMPTY_FORM: CommunityPostFormState = {
  topic: 'general',
  title: '',
  body: '',
  tags: '',
}

export default function CommunityDetailPage({ params }: CommunityDetailProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  /**
   * App Router 傳入的是 Promise 版 params。
   *
   * 這裡先把 `id` 解析成數字，再交給後面 effect 讀文章。
   * 這樣可把「解析 route」與「抓 API」拆成兩步，責任更清楚。
   */
  const [postId, setPostId] = useState<number | null>(null)
  const [post, setPost] = useState<CommunityPost | null>(null)
  const [loading, setLoading] = useState(true)
  const [replySubmitting, setReplySubmitting] = useState(false)
  const [savingPost, setSavingPost] = useState(false)
  const [deletingPost, setDeletingPost] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [error, setError] = useState('')
  const [replyBody, setReplyBody] = useState('')
  const [form, setForm] = useState<CommunityPostFormState>(EMPTY_FORM)

  useEffect(() => {
    void params.then(({ id }) => setPostId(Number(id)))
  }, [params])

  async function loadPost(id: number) {
    /**
     * 所有互動完成後都重抓單篇資料。
     *
     * 原因：
     * - 票數、回覆、可編輯狀態都可能一起改
     * - 前端不自己 patch 多個欄位，直接以後端 canonical payload 為準
     */
    setLoading(true)
    try {
      const payload = await apiFetch<CommunityPost>(`/community/posts/${id}/`)
      setPost(payload)
      setForm({
        topic: payload.topic || 'general',
        title: payload.title,
        body: payload.body,
        tags: payload.tags?.join(', ') ?? '',
      })
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '文章載入失敗。')
      setPost(null)
    } finally {
      setLoading(false)
    }
  }

  /**
   * `postId` 準備好後才讀文章。
   *
   * 這是典型「第二階段 effect」：
   * - 第一階段：從 route 解析出 id
   * - 第二階段：用 id 打 API
   */
  useEffect(() => {
    if (postId) {
      void loadPost(postId)
    }
  }, [postId])

  /**
   * 若網址帶 `?edit=1`，且目前使用者有權限，就自動切進編輯模式。
   */
  useEffect(() => {
    if (post?.can_edit && searchParams.get('edit') === '1') {
      setEditMode(true)
    }
  }, [post, searchParams])

  async function handleReplySubmit(event: FormEvent<HTMLFormElement>) {
    /**
     * 回覆送出。
     *
     * `FormEvent<HTMLFormElement>`
     * - 來源：React 事件型別
     * - 代表這個 handler 綁在 `<form>` submit 事件上
     */
    event.preventDefault()
    if (!postId) {
      return
    }
    if (!replyBody.trim()) {
      setError('請輸入回覆內容。')
      return
    }

    try {
      setReplySubmitting(true)
      setError('')
      await apiFetch(`/community/posts/${postId}/replies/`, {
        method: 'POST',
        body: JSON.stringify({ body: replyBody }),
      })
      setReplyBody('')
      await loadPost(postId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '發表回覆失敗。')
    } finally {
      setReplySubmitting(false)
    }
  }

  async function handleSavePost(event: FormEvent<HTMLFormElement>) {
    /**
     * 儲存文章編輯。
     *
     * 編輯模式沿用發文表單結構，
     * 這樣建立與更新可以共用同一套富文字欄位資料形狀。
     */
    event.preventDefault()
    if (!postId) {
      return
    }
    if (!form.title.trim()) {
      setError('請輸入文章標題。')
      return
    }
    if (!hasMeaningfulRichText(form.body)) {
      setError('請輸入文章內容。')
      return
    }

    try {
      setSavingPost(true)
      setError('')
      await apiFetch<CommunityPost>(`/community/posts/${postId}/`, {
        method: 'PUT',
        body: JSON.stringify({
          ...form,
          body: prepareRichTextForStorage(form.body),
        }),
      })
      router.push('/community')
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新文章失敗。')
    } finally {
      setSavingPost(false)
    }
  }

  async function handleDeletePost() {
    /**
     * 刪除屬破壞性操作，先要求二次確認。
     *
     * `window.confirm`
     * - 來源：瀏覽器 Window API
     * - 適合做最基本的破壞性操作確認
     */
    if (!postId || !post?.can_delete) {
      return
    }
    if (!window.confirm('確定要刪除這篇文章嗎？刪除後無法復原。')) {
      return
    }

    try {
      setDeletingPost(true)
      setError('')
      await apiFetch(`/community/posts/${postId}/`, {
        method: 'DELETE',
      })
      router.push('/community')
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除文章失敗。')
      setDeletingPost(false)
    }
  }

  async function vote() {
    /**
     * 投票後不在前端直接加減票數。
     *
     * 後端可能有：
     * - 重複投票保護
     * - 再次點擊取消投票
     * - 其他商業規則
     *
     * 所以統一重新抓文章最穩。
     */
    if (!postId) {
      return
    }
    if (post?.has_voted) {
      return
    }
    try {
      setError('')
      const payload = await apiFetch<{ id: number; votes: number; has_voted?: boolean }>(`/community/posts/${postId}/vote/`, {
        method: 'POST',
      })
      setPost((current) =>
        current && current.id === payload.id
          ? {
              ...current,
              votes: payload.votes,
              has_voted: payload.has_voted ?? true,
            }
          : current,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '文章按讚失敗。')
    }
  }

  function cancelEdit() {
    /**
     * 取消編輯時把表單還原成目前文章內容。
     *
     * 這頁不額外保存編輯草稿，
     * 因為詳情頁的編輯模式偏向一次性修改流程。
     */
    if (!post) {
      return
    }
    setForm({
      topic: post.topic || 'general',
      title: post.title,
      body: post.body,
      tags: post.tags?.join(', ') ?? '',
    })
    setEditMode(false)
    setError('')
  }

  if (loading) {
    return <section className="card">文章載入中...</section>
  }

  if (!post) {
    return <section className="card">找不到這篇文章。</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>{post.title}</h1>
        <p className="muted">
          作者：{post.author} | 分類：{post.topic} | 讚數：{post.votes}
          {post.created_at_display ? ` | 發表時間：${post.created_at_display}` : ''}
        </p>
        {post.tags?.length ? <p className="muted">標籤：{post.tags.join(', ')}</p> : null}
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {editMode ? (
        <section className="card stack">
          <h2>編輯文章</h2>
          <form className="stack" onSubmit={handleSavePost}>
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
              <RichTextEditor
                value={form.body}
                onChange={(body) => setForm((prev) => ({ ...prev, body }))}
                onImageUpload={uploadCommunityEditorImage}
              />
            </label>

            <label className="field">
              <span>標籤</span>
              <input value={form.tags} onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))} />
            </label>

            <div className="row">
              <button className="btn" disabled={savingPost || deletingPost} type="submit">
                {savingPost ? '儲存中...' : '儲存變更'}
              </button>
              <button className="btn btn-secondary" disabled={savingPost || deletingPost} onClick={cancelEdit} type="button">
                取消
              </button>
            </div>
          </form>
        </section>
      ) : (
        <section className="card stack">
          <RichTextContent className="rich-text-content rich-text-body" html={post.body} />
          <div className="row">
            <button
              className="btn btn-secondary"
              disabled={replySubmitting || savingPost || deletingPost || Boolean(post.has_voted)}
              onClick={vote}
              type="button"
            >
              {post.has_voted ? '已按讚' : '按讚'}
            </button>
            {post.can_edit ? (
              <button className="btn" disabled={replySubmitting || savingPost || deletingPost} onClick={() => setEditMode(true)} type="button">
                編輯文章
              </button>
            ) : null}
            {post.can_delete ? (
              <button className="btn btn-secondary" disabled={replySubmitting || savingPost || deletingPost} onClick={handleDeletePost} type="button">
                {deletingPost ? '刪除中...' : '刪除文章'}
              </button>
            ) : null}
          </div>
        </section>
      )}

      <section className="card stack">
        <h2>新增回覆</h2>
        <form className="stack" onSubmit={handleReplySubmit}>
          <label className="field">
            <span>回覆內容</span>
            <textarea rows={4} value={replyBody} onChange={(event) => setReplyBody(event.target.value)} />
          </label>
          <button className="btn" disabled={replySubmitting || savingPost || deletingPost} type="submit">
            {replySubmitting ? '送出中...' : '送出回覆'}
          </button>
        </form>
      </section>

      <section className="stack">
        <h2>回覆列表</h2>
        {!post.replies?.length ? (
          <div className="card muted">目前還沒有回覆。</div>
        ) : (
          post.replies.map((reply) => (
            <article className="card stack" key={reply.id}>
              <strong>{reply.author}</strong>
              <div className="muted">{reply.created_at_display ?? reply.created_at}</div>
              <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{reply.body}</p>
            </article>
          ))
        )}
      </section>
    </div>
  )
}

'use client'

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

  useEffect(() => {
    if (postId) {
      void loadPost(postId)
    }
  }, [postId])

  useEffect(() => {
    if (post?.can_edit && searchParams.get('edit') === '1') {
      setEditMode(true)
    }
  }, [post, searchParams])

  async function handleReplySubmit(event: FormEvent<HTMLFormElement>) {
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
    if (!postId) {
      return
    }
    try {
      setError('')
      await apiFetch(`/community/posts/${postId}/vote/`, { method: 'POST' })
      await loadPost(postId)
    } catch (err) {
      setError(err instanceof Error ? err.message : '文章按讚失敗。')
    }
  }

  function cancelEdit() {
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
            <button className="btn btn-secondary" disabled={replySubmitting || savingPost || deletingPost} onClick={vote} type="button">
              按讚
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

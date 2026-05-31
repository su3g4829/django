'use client'

import Link from 'next/link'
import { FormEvent, useEffect, useState } from 'react'

import { RichTextContent } from '@/components/rich-text-content'
import { RichTextEditor } from '@/components/rich-text-editor'
import { apiFetch } from '@/lib/api'
import { uploadCommunityEditorImage } from '@/lib/community-editor'
import { hasMeaningfulRichText, prepareRichTextForStorage } from '@/lib/rich-text'
import type { CommunityPost, CommunityPostListPayload } from '@/lib/types'

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

export default function CommunityPage() {
  const [posts, setPosts] = useState<CommunityPost[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showComposer, setShowComposer] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState<CommunityPostFormState>(EMPTY_FORM)

  async function loadPosts() {
    setLoading(true)
    try {
      const payload = await apiFetch<CommunityPostListPayload>('/community/posts/')
      setPosts(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '文章載入失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadPosts()
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!form.title.trim()) {
      setError('請輸入文章標題。')
      return
    }
    if (!hasMeaningfulRichText(form.body)) {
      setError('請輸入文章內容。')
      return
    }

    try {
      setSubmitting(true)
      setError('')
      await apiFetch('/community/posts/', {
        method: 'POST',
        body: JSON.stringify({
          ...form,
          body: prepareRichTextForStorage(form.body),
        }),
      })
      setForm(EMPTY_FORM)
      setShowComposer(false)
      await loadPosts()
    } catch (err) {
      setError(err instanceof Error ? err.message : '發表文章失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">文章載入中...</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>社群論壇</h1>
        <p className="muted">在這裡發表商品心得、穿搭分享、保養技巧或購買建議。</p>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ margin: 0 }}>新增文章</h2>
          <button className="btn" onClick={() => setShowComposer((prev) => !prev)} type="button">
            {showComposer ? '收起輸入窗' : '新增文章'}
          </button>
        </div>

        {showComposer ? (
          <form className="stack" onSubmit={handleSubmit}>
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
              <button className="btn" disabled={submitting} type="submit">
                {submitting ? '發表中...' : '發表文章'}
              </button>
              <button
                className="btn btn-secondary"
                disabled={submitting}
                onClick={() => {
                  setForm(EMPTY_FORM)
                  setShowComposer(false)
                  setError('')
                }}
                type="button"
              >
                取消
              </button>
            </div>
          </form>
        ) : (
          <p className="muted" style={{ margin: 0 }}>
            點選右側按鈕後才會展開輸入窗。
          </p>
        )}
      </section>

      <section className="stack">
        {!posts.length ? <div className="card muted">目前還沒有文章。</div> : null}
        {posts.map((post) => (
          <article className="card stack" key={post.id}>
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div className="stack" style={{ gap: '0.4rem' }}>
                <strong>{post.title}</strong>
                <div className="muted">
                  作者：{post.author} | 讚數：{post.votes} | 回覆：{post.reply_count ?? 0}
                </div>
              </div>
              <span className="badge">{post.topic}</span>
            </div>
            <RichTextContent className="rich-text-content rich-text-preview" html={post.body} />
            {post.tags?.length ? <div className="muted">標籤：{post.tags.join(', ')}</div> : null}
            <div className="row">
              <Link className="btn btn-secondary" href={`/community/${post.id}`}>
                查看文章
              </Link>
              {post.can_edit ? (
                <Link className="btn" href={`/community/${post.id}?edit=1`}>
                  編輯文章
                </Link>
              ) : null}
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}

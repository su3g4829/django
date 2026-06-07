'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 讀社群列表 API
 * - 控制發文輸入窗開關
 * - 維護富文字表單 state
 *
 * 因此必須在瀏覽器端執行。
 */

/**
 * 社群列表頁。
 *
 * 主要責任：
 * - 讀取討論串列表
 * - 控制發文表單開關
 * - 送出新文章後重新整理列表
 *
 * 來源：
 * - `Link` 來自 Next.js
 * - `FormEvent` / `useEffect` / `useState` 來自 React
 * - `RichTextEditor` / `RichTextContent` 是本專案富文字輸入與顯示元件
 */

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
  /**
   * 列表、表單與 API 狀態集中放在頁面層。
   *
   * 原因：
   * - 發文成功後需要直接刷新整個列表
   * - 如果把 composer 拆到更深層，狀態回傳路徑會比較繞
   */
  const [posts, setPosts] = useState<CommunityPost[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showComposer, setShowComposer] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState<CommunityPostFormState>(EMPTY_FORM)

  async function loadPosts() {
    /**
     * 進頁與發文完成後都共用這支讀取函式。
     *
     * 這是典型 loader pattern：
     * - 頁面初次載入用它
     * - mutation 成功後 refresh 也用它
     */
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
    /**
     * 送出前先驗證標題與富文字內容，避免建立空白文章。
     *
     * `prepareRichTextForStorage`
     * - 會把編輯器 HTML 清洗成適合送往後端的格式
     * - 避免把純編輯器暫存標記直接存進資料庫
     */
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

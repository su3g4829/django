'use client'

/**
 * 登入頁
 *
 * 功能：
 * - 提供帳號密碼登入表單
 * - 呼叫 Django DRF 的登入 API
 *
 * 主要 API：
 * - POST `/api/v1/auth/login/`
 */

import { FormEvent, useState } from 'react'

import { apiFetch } from '@/lib/api'

export default function LoginPage() {
  /** 使用者輸入的登入帳號。 */
  const [username, setUsername] = useState('')
  /** 使用者輸入的登入密碼。 */
  const [password, setPassword] = useState('')
  /** 送出表單時的狀態，用來避免重複提交。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 失敗時顯示在畫面上的錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 提交登入表單。
   *
   * event:
   * - 瀏覽器原生 form submit 事件，需先 `preventDefault()` 以避免整頁重新整理。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      await apiFetch('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      window.location.href = '/'
    } catch (err) {
      setError(err instanceof Error ? err.message : '登入失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack" style={{ maxWidth: 480, margin: '0 auto' }}>
      {/* 頁首說明：告訴使用者這是 session 型登入頁。 */}
      <h1>登入</h1>
      <p className="muted">表單會透過 Next.js proxy 呼叫 Django session-based auth API，並自動帶上 CSRF 與 cookie。</p>
      {error ? <div className="notice">{error}</div> : null}
      <form className="stack" onSubmit={handleSubmit}>
        {/* 登入欄位：帳號與密碼。 */}
        <label className="field">
          <span>帳號</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label className="field">
          <span>密碼</span>
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        <button className="btn" disabled={submitting} type="submit">
          {/* 送出按鈕：依提交狀態切換顯示文字。 */}
          {submitting ? '登入中…' : '登入'}
        </button>
      </form>
    </section>
  )
}

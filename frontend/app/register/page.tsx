'use client'

/**
 * 註冊頁
 *
 * 功能：
 * - 建立新的 demo auth 使用者
 * - 註冊成功後更新前端登入狀態
 *
 * 主要 API：
 * - POST `/api/v1/auth/register/`
 */

import { FormEvent, useState } from 'react'

import { apiFetch } from '@/lib/api'

export default function RegisterPage() {
  /** 註冊表單內容。 */
  const [form, setForm] = useState({
    username: '',
    display_name: '',
    email: '',
    password: '',
    password_confirm: '',
  })
  /** 送出註冊表單時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 註冊失敗時顯示的錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 提交註冊表單。
   *
   * event:
   * - 瀏覽器原生 form submit 事件，需先阻止預設送出行為。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      await apiFetch('/auth/register/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      window.location.href = '/'
    } catch (err) {
      setError(err instanceof Error ? err.message : '註冊失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack" style={{ maxWidth: 560, margin: '0 auto' }}>
      {/* 頁首區：標題與錯誤訊息。 */}
      <h1>註冊</h1>
      {error ? <div className="notice">{error}</div> : null}
      <form className="grid grid-2" onSubmit={handleSubmit}>
        {/* 基本會員欄位：帳號、顯示名稱、Email、密碼。 */}
        <label className="field">
          <span>帳號</span>
          <input value={form.username} onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))} />
        </label>
        <label className="field">
          <span>顯示名稱</span>
          <input value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} />
        </label>
        <label className="field">
          <span>Email</span>
          <input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
        </label>
        <label className="field">
          <span>密碼</span>
          <input type="password" value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} />
        </label>
        <label className="field">
          <span>確認密碼</span>
          <input
            type="password"
            value={form.password_confirm}
            onChange={(event) => setForm((prev) => ({ ...prev, password_confirm: event.target.value }))}
          />
        </label>
        <div className="row" style={{ alignSelf: 'end' }}>
          {/* 送出區：建立帳號。 */}
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '註冊中…' : '建立帳號'}
          </button>
        </div>
      </form>
    </section>
  )
}

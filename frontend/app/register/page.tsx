'use client'

/**
 * 註冊頁。
 *
 * 提供 demo 會員註冊流程，並用 session draft 保留尚未送出的表單內容。
 */

/**
 * 註冊頁
 *
 * 功能：
 * - 建立新的 demo 會員帳號
 * - 在送出前先做基本前端驗證，避免使用者只看到後端錯誤
 *
 * API：
 * - POST `/api/v1/auth/register/`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'

const MIN_PASSWORD_LENGTH = 6
const REGISTER_DRAFT_KEY = 'register-form'

export default function RegisterPage() {
  // 表單初始化時先嘗試讀 session draft，避免使用者刷新後內容消失。
  /** 註冊表單內容。 */
  const [form, setForm] = useState(
    () =>
      getSessionDraft<{
        username: string
        display_name: string
        email: string
        password: string
        password_confirm: string
      }>(REGISTER_DRAFT_KEY) ?? {
        username: '',
        display_name: '',
        email: '',
        password: '',
        password_confirm: '',
      },
  )

  /** 送出中狀態，避免重複提交。 */
  const [submitting, setSubmitting] = useState(false)

  /** 顯示於表單上方的錯誤訊息。 */
  const [error, setError] = useState('')

  useEffect(() => {
    // 表單任一欄位變動時就寫回 session draft，讓填寫過程可恢復。
    setSessionDraft(REGISTER_DRAFT_KEY, form)
  }, [form])

  /**
   * 送出註冊表單。
   *
   * event:
   * - 表單 submit 事件
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    // 送出前先做最基本的密碼長度與確認欄位比對。
    event.preventDefault()

    if (form.password.length < MIN_PASSWORD_LENGTH) {
      setError(`密碼至少需要 ${MIN_PASSWORD_LENGTH} 個字元。`)
      return
    }

    if (form.password !== form.password_confirm) {
      setError('兩次輸入的密碼不一致。')
      return
    }

    try {
      setSubmitting(true)
      setError('')
      await apiFetch('/auth/register/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      clearSessionDraft(REGISTER_DRAFT_KEY)
      window.location.href = '/'
    } catch (err) {
      setError(err instanceof Error ? err.message : '註冊失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack" style={{ maxWidth: 560, margin: '0 auto' }}>
      <h1>註冊</h1>
      {error ? <div className="notice">{error}</div> : null}

      <form className="grid grid-2" onSubmit={handleSubmit}>
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
          <small className="muted">密碼至少需要 6 個字元。</small>
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
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '註冊中...' : '建立帳號'}
          </button>
        </div>
      </form>
    </section>
  )
}

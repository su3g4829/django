'use client'

/**
 * 會員資料頁
 *
 * 功能：
 * - 讀取目前登入者資料
 * - 更新顯示名稱、email、密碼
 *
 * 主要 API：
 * - GET `/api/v1/me/profile/`
 * - POST `/api/v1/me/profile/`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { DemoUser } from '@/lib/types'

type MePayload = {
  user: DemoUser | null
}

export default function MeProfilePage() {
  /** 個人資料表單。 */
  const [form, setForm] = useState({
    display_name: '',
    email: '',
    new_password: '',
    confirm_password: '',
  })
  /** 讀取初始資料時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 送出表單時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 錯誤訊息。 */
  const [error, setError] = useState('')
  /** 成功訊息。 */
  const [message, setMessage] = useState('')

  useEffect(() => {
    /** 載入目前登入者資料，填入表單預設值。 */
    setLoading(true)
    apiFetch<MePayload>('/me/profile/')
      .then((payload) => {
        const user = payload.user
        setForm((prev) => ({
          ...prev,
          display_name: user?.display_name ?? '',
          email: user?.email ?? '',
        }))
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  /**
   * 提交會員資料更新表單。
   *
   * event:
   * - form submit 事件，需先阻止預設送出行為。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      const payload = await apiFetch<{ detail: string; user: DemoUser }>('/me/profile/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      setMessage(payload.detail)
      setForm((prev) => ({ ...prev, new_password: '', confirm_password: '' }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新會員資料失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入會員資料中…</section>
  }

  return (
    <section className="card stack" style={{ maxWidth: 720 }}>
      {/* 個人資料編輯表單：更新顯示名稱、Email 與密碼。 */}
      <h1>會員資料</h1>
      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}
      <form className="grid grid-2" onSubmit={handleSubmit}>
        {/* 基本欄位：顯示名稱與 Email。 */}
        <label className="field">
          <span>顯示名稱</span>
          <input value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} />
        </label>
        <label className="field">
          <span>Email</span>
          <input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
        </label>
        {/* 密碼更新欄位：可選填，送出時由後端驗證。 */}
        <label className="field">
          <span>新密碼</span>
          <input type="password" value={form.new_password} onChange={(event) => setForm((prev) => ({ ...prev, new_password: event.target.value }))} />
        </label>
        <label className="field">
          <span>確認新密碼</span>
          <input
            type="password"
            value={form.confirm_password}
            onChange={(event) => setForm((prev) => ({ ...prev, confirm_password: event.target.value }))}
          />
        </label>
        <div className="row">
          {/* 儲存按鈕：提交會員資料更新。 */}
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '儲存中…' : '儲存資料'}
          </button>
        </div>
      </form>
    </section>
  )
}

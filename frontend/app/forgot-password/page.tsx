'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'

import { apiFetch } from '@/lib/api'

type ResetRequestResponse = {
  detail: string
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      const response = await apiFetch<ResetRequestResponse>('/auth/password-reset/request/', {
        method: 'POST',
        body: JSON.stringify({ email }),
      })
      setSuccess(response.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出失敗，請稍後再試。')
      setSuccess('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack" style={{ maxWidth: 560, margin: '0 auto' }}>
      <h1>忘記密碼</h1>
      <p className="muted">輸入註冊 Email 後，系統會在開發信箱頁產生一封模擬重設信件。</p>
      {error ? <div className="notice">{error}</div> : null}
      {success ? <div className="notice success">{success}</div> : null}
      <form className="stack" onSubmit={handleSubmit}>
        <label className="field">
          <span>Email</span>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <button className="btn" disabled={submitting} type="submit">
          {submitting ? '送出中...' : '建立重設連結'}
        </button>
      </form>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
        <Link className="muted" href="/login">
          返回登入
        </Link>
        <Link className="muted" href={`/dev/mailbox${email ? `?email=${encodeURIComponent(email)}` : ''}`}>
          前往開發信箱
        </Link>
      </div>
    </section>
  )
}

'use client'

import Link from 'next/link'
import { FormEvent, useState } from 'react'

import { apiFetch } from '@/lib/api'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

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
      <h1>登入</h1>
      <p className="muted">請輸入帳號與密碼登入；若要測試忘記密碼流程，也可直接前往開發信箱查看重設連結。</p>
      {error ? <div className="notice">{error}</div> : null}
      <form className="stack" onSubmit={handleSubmit}>
        <label className="field">
          <span>帳號</span>
          <input value={username} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label className="field">
          <span>密碼</span>
          <div style={{ position: 'relative' }}>
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              style={{ paddingRight: '3rem' }}
            />
            <button
              aria-label={showPassword ? '隱藏密碼' : '顯示密碼'}
              className="btn btn-secondary"
              onClick={() => setShowPassword((value) => !value)}
              style={{
                position: 'absolute',
                right: '0.4rem',
                top: '50%',
                transform: 'translateY(-50%)',
                minWidth: '2.2rem',
                padding: '0.35rem',
              }}
              type="button"
            >
              <svg
                aria-hidden="true"
                fill="none"
                height="18"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.8"
                viewBox="0 0 24 24"
                width="18"
              >
                <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
                <circle cx="12" cy="12" r="3" />
                {showPassword ? <path d="M4 4l16 16" /> : null}
              </svg>
            </button>
          </div>
        </label>
        <button className="btn" disabled={submitting} type="submit">
          {submitting ? '登入中...' : '登入'}
        </button>
      </form>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
        <Link className="muted" href="/forgot-password">
          忘記密碼
        </Link>
        <Link className="muted" href="/dev/mailbox">
          前往開發信箱
        </Link>
        <Link className="muted" href="/register">
          前往註冊
        </Link>
      </div>
    </section>
  )
}

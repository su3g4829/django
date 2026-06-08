'use client'

import Link from 'next/link'
import { FormEvent, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'

type VerifyResponse = {
  detail: string
  item: {
    display_name: string
    email: string
    expires_at_display: string
  }
}

type ConfirmResponse = {
  detail: string
}

export default function ResetPasswordPage() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token') || ''
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [targetLabel, setTargetLabel] = useState('')
  const [expiresAt, setExpiresAt] = useState('')

  useEffect(() => {
    async function verifyToken() {
      if (!token) {
        setError('缺少重設 token。')
        setLoading(false)
        return
      }
      try {
        setLoading(true)
        setError('')
        const response = await apiFetch<VerifyResponse>(`/auth/password-reset/verify/?token=${encodeURIComponent(token)}`)
        setTargetLabel(`${response.item.display_name} (${response.item.email})`)
        setExpiresAt(response.item.expires_at_display)
      } catch (err) {
        setError(err instanceof Error ? err.message : '重設連結已失效。')
      } finally {
        setLoading(false)
      }
    }

    void verifyToken()
  }, [token])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      setSuccess('')
      const response = await apiFetch<ConfirmResponse>('/auth/password-reset/confirm/', {
        method: 'POST',
        body: JSON.stringify({
          token,
          new_password: password,
          password_confirm: passwordConfirm,
        }),
      })
      setSuccess(response.detail)
      setPassword('')
      setPasswordConfirm('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '重設密碼失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack" style={{ maxWidth: 560, margin: '0 auto' }}>
      <h1>重設密碼</h1>
      {loading ? <p className="muted">驗證連結中...</p> : null}
      {!loading && targetLabel ? (
        <div className="notice success">
          目前重設對象：{targetLabel}
          {expiresAt ? `，連結到期時間：${expiresAt}` : ''}
        </div>
      ) : null}
      {error ? <div className="notice">{error}</div> : null}
      {success ? <div className="notice success">{success}</div> : null}

      <form className="stack" onSubmit={handleSubmit}>
        <label className="field">
          <span>新密碼</span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={loading || !!success}
          />
        </label>
        <label className="field">
          <span>確認新密碼</span>
          <input
            type="password"
            value={passwordConfirm}
            onChange={(event) => setPasswordConfirm(event.target.value)}
            disabled={loading || !!success}
          />
        </label>
        <button className="btn" disabled={loading || submitting || !!success} type="submit">
          {submitting ? '送出中...' : '更新密碼'}
        </button>
      </form>

      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
        <Link className="muted" href="/login">
          返回登入
        </Link>
        <Link className="muted" href="/dev/mailbox">
          前往開發信箱
        </Link>
      </div>
    </section>
  )
}

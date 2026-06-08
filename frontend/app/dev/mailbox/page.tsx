'use client'

import Link from 'next/link'
import { FormEvent, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import { apiFetch } from '@/lib/api'

type MailboxItem = {
  id?: number
  username: string
  display_name: string
  email: string
  reset_url: string
  subject: string
  preview: string
  status: string
  status_label?: string
  created_at_display: string
  expires_at_display: string
  used_at_display?: string
}

type MailboxResponse = {
  items: MailboxItem[]
}

export default function DevMailboxPage() {
  const searchParams = useSearchParams()
  const [email, setEmail] = useState(searchParams.get('email') || '')
  const [items, setItems] = useState<MailboxItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function loadMailbox(targetEmail: string) {
    try {
      setLoading(true)
      setError('')
      const query = targetEmail ? `?email=${encodeURIComponent(targetEmail)}` : ''
      const response = await apiFetch<MailboxResponse>(`/auth/password-reset/dev-mailbox/${query}`)
      setItems(response.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取開發信箱失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const initialEmail = searchParams.get('email') || ''
    setEmail(initialEmail)
    void loadMailbox(initialEmail)
  }, [searchParams])

  function handleFilter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const target = email.trim()
    const query = target ? `?email=${encodeURIComponent(target)}` : ''
    window.history.replaceState(null, '', `/dev/mailbox${query}`)
    void loadMailbox(target)
  }

  return (
    <section className="card stack" style={{ maxWidth: 880, margin: '0 auto' }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
        <div className="stack" style={{ gap: '0.35rem' }}>
          <h1 style={{ margin: 0 }}>開發信箱</h1>
          <p className="muted" style={{ margin: 0 }}>
            這裡會顯示忘記密碼流程產生的模擬信件，方便開發與展示時直接打開重設連結。
          </p>
        </div>
        <Link className="muted" href="/forgot-password">
          返回忘記密碼
        </Link>
      </div>

      <form className="row" onSubmit={handleFilter}>
        <label className="field" style={{ flex: '1 1 320px' }}>
          <span>篩選 Email</span>
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <button className="btn btn-secondary" style={{ marginTop: '1.6rem' }} type="submit">
          查詢
        </button>
      </form>

      {error ? <div className="notice">{error}</div> : null}
      {loading ? <p className="muted">載入中...</p> : null}
      {!loading && !items.length ? <p className="muted">目前沒有符合條件的重設信件。</p> : null}

      <div className="stack">
        {items.map((item) => (
          <article className="card stack" key={`${item.email}-${item.reset_url}`} style={{ borderRadius: 14 }}>
            <div className="row" style={{ justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
              <div className="stack" style={{ gap: '0.25rem' }}>
                <strong>{item.subject}</strong>
                <div className="muted">
                  收件人：{item.display_name} ({item.email})
                </div>
              </div>
              <span className="badge">{item.status_label || item.status}</span>
            </div>
            <div className="muted">{item.preview}</div>
            <div className="muted">
              建立時間：{item.created_at_display || '-'} / 到期時間：{item.expires_at_display || '-'}
              {item.used_at_display ? ` / 使用時間：${item.used_at_display}` : ''}
            </div>
            <Link className="btn" href={item.reset_url}>
              開啟重設連結
            </Link>
          </article>
        ))}
      </div>
    </section>
  )
}

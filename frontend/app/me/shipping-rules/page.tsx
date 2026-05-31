'use client'

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { SellerShippingRules } from '@/lib/types'

const EMPTY_RULES: SellerShippingRules = {
  home_delivery_enabled: true,
  home_delivery_fee: '80.00',
  convenience_store_enabled: true,
  convenience_store_fee: '60.00',
  free_shipping_threshold: '1200.00',
}

export default function SellerShippingRulesPage() {
  const [rules, setRules] = useState<SellerShippingRules>(EMPTY_RULES)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  useEffect(() => {
    async function loadRules() {
      try {
        setLoading(true)
        const payload = await apiFetch<SellerShippingRules>('/me/shipping-rules/')
        setRules(payload)
        setError('')
      } catch (err) {
        setError(err instanceof Error ? err.message : '無法讀取運費設定。')
      } finally {
        setLoading(false)
      }
    }

    void loadRules()
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      setMessage('')
      const payload = await apiFetch<{ detail: string; rules: SellerShippingRules }>('/me/shipping-rules/', {
        method: 'PUT',
        body: JSON.stringify(rules),
      })
      setRules(payload.rules)
      setMessage(payload.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新運費設定失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">正在讀取運費設定...</section>
  }

  return (
    <section className="card stack">
      <div className="stack" style={{ gap: '0.25rem' }}>
        <h1>賣家運費設定</h1>
        <p className="muted">先設定賣家主規則。結帳時若購物車含不同賣家商品，系統會依賣家分組各自計算運費。</p>
      </div>

      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}

      <form className="grid grid-2" onSubmit={handleSubmit}>
        <label className="field">
          <span>宅配啟用</span>
          <select
            value={rules.home_delivery_enabled ? 'true' : 'false'}
            onChange={(event) =>
              setRules((current) => ({ ...current, home_delivery_enabled: event.target.value === 'true' }))
            }
          >
            <option value="true">啟用</option>
            <option value="false">停用</option>
          </select>
        </label>

        <label className="field">
          <span>宅配運費</span>
          <input
            value={rules.home_delivery_fee}
            onChange={(event) => setRules((current) => ({ ...current, home_delivery_fee: event.target.value }))}
          />
        </label>

        <label className="field">
          <span>超商取貨啟用</span>
          <select
            value={rules.convenience_store_enabled ? 'true' : 'false'}
            onChange={(event) =>
              setRules((current) => ({ ...current, convenience_store_enabled: event.target.value === 'true' }))
            }
          >
            <option value="true">啟用</option>
            <option value="false">停用</option>
          </select>
        </label>

        <label className="field">
          <span>超商運費</span>
          <input
            value={rules.convenience_store_fee}
            onChange={(event) => setRules((current) => ({ ...current, convenience_store_fee: event.target.value }))}
          />
        </label>

        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>免運門檻</span>
          <input
            value={rules.free_shipping_threshold}
            onChange={(event) => setRules((current) => ({ ...current, free_shipping_threshold: event.target.value }))}
          />
          <div className="muted">同一賣家分組小計達到門檻後，該賣家這組商品免運。</div>
        </label>

        <div className="row">
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '儲存中...' : '儲存運費設定'}
          </button>
        </div>
      </form>
    </section>
  )
}

'use client'

/**
 * 發票資料頁
 *
 * 功能：
 * - 讀取與更新發票資料
 * - 支援個人或公司發票欄位
 *
 * 主要 API：
 * - GET `/api/v1/me/invoice/`
 * - POST `/api/v1/me/invoice/`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { InvoiceProfile } from '@/lib/types'

const INVOICE_DRAFT_KEY = 'me-invoice-form'

export default function MeInvoicePage() {
  /** 發票資料表單。 */
  const [form, setForm] = useState<InvoiceProfile>(
    () =>
      getSessionDraft<InvoiceProfile>(INVOICE_DRAFT_KEY) ?? {
        invoice_type: 'personal',
        carrier_code: '',
        company_name: '',
        tax_id: '',
      },
  )
  /** 初次載入發票資料時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 送出更新時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 錯誤訊息。 */
  const [error, setError] = useState('')
  /** 成功訊息。 */
  const [message, setMessage] = useState('')

  useEffect(() => {
    setSessionDraft(INVOICE_DRAFT_KEY, form)
  }, [form])

  useEffect(() => {
    /** 載入目前登入者的發票資料。 */
    setLoading(true)
    apiFetch<InvoiceProfile>('/me/invoice/')
      .then((payload) => {
        const draft = getSessionDraft<Partial<InvoiceProfile>>(INVOICE_DRAFT_KEY)
        setForm(draft ? { ...payload, ...draft } : payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  /**
   * 提交發票資料表單。
   *
   * event:
   * - form submit 事件，需先阻止預設送出行為。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      const payload = await apiFetch<InvoiceProfile>('/me/invoice/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      clearSessionDraft(INVOICE_DRAFT_KEY)
      setForm(payload)
      setMessage('發票資料已更新。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新發票資料失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入發票資料中…</section>
  }

  return (
    <section className="card stack" style={{ maxWidth: 720 }}>
      {/* 發票資料編輯表單：可切換個人或公司發票欄位。 */}
      <h1>發票資料</h1>
      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}
      <form className="grid grid-2" onSubmit={handleSubmit}>
        {/* 發票基本欄位：類型、載具、公司名稱、統編。 */}
        <label className="field">
          <span>發票類型</span>
          <select value={form.invoice_type} onChange={(event) => setForm((prev) => ({ ...prev, invoice_type: event.target.value }))}>
            <option value="personal">個人發票</option>
            <option value="company">公司發票</option>
          </select>
        </label>
        <label className="field">
          <span>載具條碼</span>
          <input value={form.carrier_code ?? ''} onChange={(event) => setForm((prev) => ({ ...prev, carrier_code: event.target.value }))} />
        </label>
        <label className="field">
          <span>公司名稱</span>
          <input value={form.company_name ?? ''} onChange={(event) => setForm((prev) => ({ ...prev, company_name: event.target.value }))} />
        </label>
        <label className="field">
          <span>統一編號</span>
          <input value={form.tax_id ?? ''} onChange={(event) => setForm((prev) => ({ ...prev, tax_id: event.target.value }))} />
        </label>
        <div className="row">
          {/* 送出發票資料更新。 */}
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '儲存中…' : '儲存發票資料'}
          </button>
        </div>
      </form>
    </section>
  )
}

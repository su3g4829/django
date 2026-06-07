'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 讀寫地址 API
 * - 維護表單 state
 * - 使用 `sessionStorage` 草稿
 *
 * 因此必須在瀏覽器端執行。
 */

/**
 * 地址簿頁
 *
 * 功能：
 * - 列出地址
 * - 新增地址
 * - 設為預設地址
 * - 刪除地址
 *
 * 主要 API：
 * - GET/POST `/api/v1/me/addresses/`
 * - POST `/api/v1/me/addresses/:id/default/`
 * - DELETE `/api/v1/me/addresses/:id/`
 *
 * 來源：
 * - `FormEvent` / `useEffect` / `useState` 來自 React
 * - 草稿暫存透過 `session-drafts` 封裝瀏覽器 `sessionStorage`
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { clearSessionDraft, getSessionDraft, setSessionDraft } from '@/lib/session-drafts'
import type { Address } from '@/lib/types'

type AddressListPayload = {
  items: Address[]
}

const EMPTY_FORM = {
  label: '',
  recipient: '',
  phone: '',
  city: '',
  district: '',
  postal_code: '',
  address_line: '',
}
const ADDRESS_DRAFT_KEY = 'me-address-form'

/**
 * 會員地址管理頁。
 *
 * 主要操作：
 * - 讀取地址清單
 * - 新增地址
 * - 設成預設地址
 * - 刪除地址
 *
 * 設計方式：
 * - `items` 儲存後端地址列表
 * - `form` 儲存右側新增地址表單
 * - 兩者分離，避免列表刷新時覆蓋正在輸入的表單內容
 */
export default function MeAddressesPage() {
  /** 地址列表。 */
  const [items, setItems] = useState<Address[]>([])
  /** 新增地址表單。 */
  const [form, setForm] = useState(() => getSessionDraft<typeof EMPTY_FORM>(ADDRESS_DRAFT_KEY) ?? { ...EMPTY_FORM })
  /** 首次載入地址列表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 新增、刪除、設預設時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 表單尚未送出前先存到 session draft。
   *
   * 來源：
   * - `sessionStorage` 是瀏覽器 Web Storage API
   * - 專案用 `setSessionDraft` 包裝 key 命名與 JSON 序列化
   */
  useEffect(() => {
    setSessionDraft(ADDRESS_DRAFT_KEY, form)
  }, [form])

  /** 載入地址列表。 */
  /**
   * 所有地址清單刷新都走同一個 loader。
   *
   * 好處：
   * - 新增、刪除、設預設後都只要呼叫同一支函式
   * - loading / error 邏輯集中，避免每個 action 重寫一次
   */
  async function loadAddresses() {
    setLoading(true)
    try {
      const payload = await apiFetch<AddressListPayload>('/me/addresses/')
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入地址資料失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAddresses()
  }, [])

  /**
   * 提交新增地址表單。
   *
   * `FormEvent<HTMLFormElement>`
   * - 來源：React 對原生 DOM 事件的型別包裝
   * - 代表這個事件來自 `<form>`
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      await apiFetch<Address>('/me/addresses/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      clearSessionDraft(ADDRESS_DRAFT_KEY)
      setForm(EMPTY_FORM)
      await loadAddresses()
    } catch (err) {
      setError(err instanceof Error ? err.message : '新增地址失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 設定預設地址。
   *
   * addressId:
   * - 要設成預設的地址 id。
   */
  /**
   * 指定某一筆地址為預設值。
   *
   * 這裡送出 `POST` 而不是 `PATCH`，
   * 是因為後端把「設成預設地址」視為一個動作型 endpoint。
   */
  async function setDefault(addressId: number) {
    try {
      setSubmitting(true)
      await apiFetch<Address>(`/me/addresses/${addressId}/default/`, { method: 'POST' })
      await loadAddresses()
    } catch (err) {
      setError(err instanceof Error ? err.message : '設定預設地址失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 刪除地址。
   *
   * addressId:
   * - 要刪除的地址 id。
   */
  /**
   * 刪除後重新抓地址清單。
   *
   * 不在前端手動 splice 本地陣列，
   * 而是直接依後端最新結果為準，可避免預設地址等衍生狀態不同步。
   */
  async function removeAddress(addressId: number) {
    try {
      setSubmitting(true)
      await apiFetch(`/me/addresses/${addressId}/`, { method: 'DELETE' })
      await loadAddresses()
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除地址失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="grid grid-2">
      {/* 左欄：地址列表與每筆地址操作。 */}
      <section className="card stack">
        <h1>地址簿</h1>
        {error ? <div className="notice">{error}</div> : null}
        {loading ? (
          <div className="muted">載入地址資料中…</div>
        ) : !items.length ? (
          <div className="muted">目前沒有任何地址資料。</div>
        ) : (
          items.map((item) => (
            <div className="card stack" key={item.id}>
              {/* 單筆地址卡：顯示標籤、收件人與詳細地址。 */}
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <strong>{item.label}</strong>
                {item.is_default ? <span className="badge">預設</span> : null}
              </div>
              <div>{item.recipient}</div>
              <div className="muted">
                {item.city}
                {item.district}
                {item.address_line}
              </div>
              <div className="row">
                {/* 操作列：可設為預設或刪除。 */}
                {!item.is_default ? (
                  <button className="btn btn-secondary" disabled={submitting} onClick={() => setDefault(item.id)} type="button">
                    設為預設
                  </button>
                ) : null}
                <button className="btn btn-secondary" disabled={submitting} onClick={() => removeAddress(item.id)} type="button">
                  刪除
                </button>
              </div>
            </div>
          ))
        )}
      </section>

      {/* 右欄：新增地址表單。 */}
      <section className="card stack">
        <h2>新增地址</h2>
        <form className="grid grid-2" onSubmit={handleSubmit}>
          {/* 表單欄位：標籤、收件人、電話、郵遞區號、城市、行政區、詳細地址。 */}
          <label className="field">
            <span>地址標籤</span>
            <input value={form.label} onChange={(event) => setForm((prev) => ({ ...prev, label: event.target.value }))} />
          </label>
          <label className="field">
            <span>收件人</span>
            <input value={form.recipient} onChange={(event) => setForm((prev) => ({ ...prev, recipient: event.target.value }))} />
          </label>
          <label className="field">
            <span>電話</span>
            <input value={form.phone} onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))} />
          </label>
          <label className="field">
            <span>郵遞區號</span>
            <input value={form.postal_code} onChange={(event) => setForm((prev) => ({ ...prev, postal_code: event.target.value }))} />
          </label>
          <label className="field">
            <span>城市</span>
            <input value={form.city} onChange={(event) => setForm((prev) => ({ ...prev, city: event.target.value }))} />
          </label>
          <label className="field">
            <span>行政區</span>
            <input value={form.district} onChange={(event) => setForm((prev) => ({ ...prev, district: event.target.value }))} />
          </label>
          <label className="field" style={{ gridColumn: '1 / -1' }}>
            <span>詳細地址</span>
            <input value={form.address_line} onChange={(event) => setForm((prev) => ({ ...prev, address_line: event.target.value }))} />
          </label>
          <div className="row">
            {/* 送出新增地址。 */}
            <button className="btn" disabled={submitting} type="submit">
              {submitting ? '新增中…' : '新增地址'}
            </button>
          </div>
        </form>
      </section>
    </div>
  )
}

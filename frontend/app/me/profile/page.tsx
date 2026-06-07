'use client'

/**
 * `use client`
 * 來源：Next.js App Router。
 *
 * 這頁需要：
 * - 讀取會員 API
 * - 維護表單 state
 * - 送出更新與賣家申請
 *
 * 所以必須是 Client Component。
 */

/**
 * 會員資料頁
 *
 * 功能：
 * - 查詢與更新會員基本資料
 * - 修改密碼
 * - 顯示目前賣家申請狀態
 * - 提供一般會員送出「申請成為賣家」入口
 *
 * API：
 * - GET `/api/v1/me/profile/`
 * - POST `/api/v1/me/profile/`
 * - POST `/api/v1/me/seller-request/`
 *
 * 來源：
 * - `FormEvent`、`useEffect`、`useState` 來自 React
 * - `apiFetch` 來自專案 API helper
 */

import { FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { DemoUser } from '@/lib/types'

type MePayload = {
  user: DemoUser | null
}

type ProfileFormState = {
  display_name: string
  email: string
  new_password: string
  confirm_password: string
}

const EMPTY_FORM: ProfileFormState = {
  display_name: '',
  email: '',
  new_password: '',
  confirm_password: '',
}

/**
 * 將 seller request 與 role 狀態轉成頁面文案。
 *
 * 這種純轉換邏輯獨立成 helper，讓 JSX 不用塞一長串 if/switch。
 */
function getSellerRequestStatusLabel(user: DemoUser | null) {
  if (!user) return ''
  if (user.role === 'seller' || user.role === 'admin') return '已具備賣家權限'
  switch (user.seller_request_status) {
    case 'pending':
      return '賣家申請審核中'
    case 'approved':
      return '賣家申請已核准'
    case 'rejected':
      return '賣家申請已拒絕'
    default:
      return '尚未申請成為賣家'
  }
}

/**
 * 會員資料頁。
 *
 * 這裡同時處理：
 * - 基本資料更新
 * - 密碼更新
 * - 賣家申請與狀態顯示
 *
 * 設計方式：
 * - `user` 保存後端回傳的 canonical 使用者快照
 * - `form` 保存畫面上可編輯欄位
 * - 兩者拆開可避免每次輸入都直接污染原始使用者資料
 */
export default function MeProfilePage() {
  /** 表單欄位。 */
  const [form, setForm] = useState<ProfileFormState>(EMPTY_FORM)

  /** 目前登入使用者，用於顯示角色與賣家申請狀態。 */
  const [user, setUser] = useState<DemoUser | null>(null)

  /** 首次載入狀態。 */
  const [loading, setLoading] = useState(true)

  /** 更新資料中的狀態。 */
  const [submitting, setSubmitting] = useState(false)

  /** 送出賣家申請中的狀態。 */
  const [requestingSeller, setRequestingSeller] = useState(false)

  /** 錯誤訊息。 */
  const [error, setError] = useState('')

  /** 成功訊息。 */
  const [message, setMessage] = useState('')

  useEffect(() => {
    /**
     * 初始化會員資料，並同步成表單預設值。
     *
     * `useEffect(() => {}, [])`
     * - 代表只在 mount 後執行一次
     * - 適合頁面初次抓資料
     */
    setLoading(true)
    apiFetch<MePayload>('/me/profile/')
      .then((payload) => {
        const nextUser = payload.user
        setUser(nextUser)
        setForm({
          display_name: nextUser?.display_name ?? '',
          email: nextUser?.email ?? '',
          new_password: '',
          confirm_password: '',
        })
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  /**
   * 更新會員資料。
   *
   * `event.preventDefault()`
   * 來源：DOM form submit 規範。
   *
   * 用途：
   * - 阻止瀏覽器原生 form submit 直接整頁刷新
   * - 讓 React 可以留在單頁應用流程中自行呼叫 API
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      setMessage('')
      const payload = await apiFetch<{ detail: string; user: DemoUser }>('/me/profile/', {
        method: 'POST',
        body: JSON.stringify(form),
      })
      setUser(payload.user)
      setMessage(payload.detail)
      setForm({
        display_name: payload.user.display_name ?? '',
        email: payload.user.email ?? '',
        new_password: '',
        confirm_password: '',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新會員資料失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  /**
   * 送出賣家申請。
   *
   * 成功後直接用後端回傳的 `user` 覆蓋 state，
   * 讓角色/申請狀態文字立即更新。
   */
  async function handleSellerRequest() {
    try {
      setRequestingSeller(true)
      setError('')
      setMessage('')
      const payload = await apiFetch<{ detail: string; user: DemoUser }>('/me/seller-request/', {
        method: 'POST',
      })
      setUser(payload.user)
      setMessage(payload.detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出賣家申請失敗，請稍後再試。')
    } finally {
      setRequestingSeller(false)
    }
  }

  if (loading) {
    return <section className="card">讀取會員資料中...</section>
  }

  const sellerStatusLabel = getSellerRequestStatusLabel(user)
  const canRequestSeller = Boolean(user && user.role === 'member' && user.seller_request_status !== 'pending')

  return (
    <section className="card stack" style={{ maxWidth: 720 }}>
      <h1>會員資料</h1>
      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}

      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div className="stack" style={{ gap: '0.25rem' }}>
            <strong>角色：{user?.role ?? 'member'}</strong>
            <span className="muted">{sellerStatusLabel}</span>
          </div>

          {canRequestSeller ? (
            <button className="btn" disabled={requestingSeller} onClick={handleSellerRequest} type="button">
              {requestingSeller ? '送出申請中...' : '申請成為賣家'}
            </button>
          ) : null}
        </div>
      </section>

      <form className="grid grid-2" onSubmit={handleSubmit}>
        <label className="field">
          <span>顯示名稱</span>
          <input value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} />
        </label>

        <label className="field">
          <span>Email</span>
          <input value={form.email} onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))} />
        </label>

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
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '更新中...' : '更新資料'}
          </button>
        </div>
      </form>
    </section>
  )
}

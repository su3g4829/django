'use client'

/**
 * 管理者會員列表頁
 *
 * 功能：
 * - 查詢會員
 * - 更新會員狀態
 *
 * 主要 API：
 * - GET `/api/v1/staff/users/`
 * - POST `/api/v1/staff/users/:username/status/`
 */

import { useEffect, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { DemoUser } from '@/lib/types'

type UserListPayload = {
  items: DemoUser[]
}

export default function AdminUsersPage() {
  /** 管理端會員列表。 */
  const [items, setItems] = useState<DemoUser[]>([])
  /** 會員查詢與篩選條件。 */
  const [filters, setFilters] = useState({ q: '', role: '', account_status: '' })
  /** 初次載入列表時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 更新會員狀態時的提交狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 載入會員列表。
   *
   * nextFilters:
   * - 要送給後端的篩選條件；未傳入時會沿用目前 `filters` state。
   */
  async function loadUsers(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<UserListPayload>(`/staff/users/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入會員資料失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
  }, [])

  /**
   * 更新會員狀態。
   *
   * username:
   * - 目標會員帳號。
   * accountStatus:
   * - 要更新成的帳號狀態，目前支援 `active` 與 `suspended`。
   */
  async function updateStatus(username: string, accountStatus: 'active' | 'suspended') {
    try {
      setSubmitting(true)
      await apiFetch(`/staff/users/${username}/status/`, {
        method: 'POST',
        body: JSON.stringify({ account_status: accountStatus }),
      })
      await loadUsers()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新會員狀態失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      {/* 會員查詢與篩選區：關鍵字、角色與帳號狀態。 */}
      <h1>會員列表</h1>
      <div className="grid grid-3">
        <label className="field">
          <span>關鍵字</span>
          <input value={filters.q} onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))} />
        </label>
        <label className="field">
          <span>角色</span>
          <input value={filters.role} onChange={(event) => setFilters((prev) => ({ ...prev, role: event.target.value }))} />
        </label>
        <label className="field">
          <span>帳號狀態</span>
          <input value={filters.account_status} onChange={(event) => setFilters((prev) => ({ ...prev, account_status: event.target.value }))} />
        </label>
      </div>
      <div className="row">
        {/* 套用篩選條件並重新查詢。 */}
        <button className="btn btn-secondary" onClick={() => loadUsers(filters)} type="button">
          套用篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">載入會員資料中…</div>
      ) : !items.length ? (
        <div className="muted">目前沒有符合條件的會員。</div>
      ) : (
        <table className="table">
          {/* 表頭：會員識別、角色、狀態與操作。 */}
          <thead>
            <tr>
              <th>帳號</th>
              <th>顯示名稱</th>
              <th>角色</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {/* 每列可直接對會員執行啟用或停權。 */}
            {items.map((item) => (
              <tr key={item.username}>
                <td>@{item.username}</td>
                <td>{item.display_name}</td>
                <td>{item.role}</td>
                <td>{item.account_status ?? 'active'}</td>
                <td>
                  <div className="row">
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => updateStatus(item.username, 'active')} type="button">
                      啟用
                    </button>
                    <button className="btn btn-secondary" disabled={submitting} onClick={() => updateStatus(item.username, 'suspended')} type="button">
                      停權
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

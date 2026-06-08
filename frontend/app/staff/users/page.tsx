'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'

type AdminUser = {
  id: number
  username: string
  display_name: string
  role: string
  account_status?: string
  email?: string
  created_at?: string
}

type PasswordResetRecord = {
  id?: number
  username: string
  display_name: string
  email: string
  reset_url: string
  status: string
  status_label?: string
  created_at_display?: string
  expires_at_display?: string
  used_at_display?: string
}

type UserListPayload = {
  items: AdminUser[]
  reset_records: PasswordResetRecord[]
}

type UserSortKey = 'created_desc' | 'created_asc' | 'username_asc' | 'username_desc'

export default function AdminUsersPage() {
  const [items, setItems] = useState<AdminUser[]>([])
  const [resetRecords, setResetRecords] = useState<PasswordResetRecord[]>([])
  const [filters, setFilters] = useState({ q: '', role: '', account_status: '' })
  const [sortBy, setSortBy] = useState<UserSortKey>('created_desc')
  const [resetSearch, setResetSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadUsers(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<UserListPayload>(`/staff/users/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setResetRecords(payload.reset_records || [])
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取會員資料失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadUsers()
  }, [])

  const sortedItems = useMemo(() => {
    const next = [...items]
    switch (sortBy) {
      case 'created_asc':
        next.sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')))
        break
      case 'username_asc':
        next.sort((a, b) => a.username.localeCompare(b.username))
        break
      case 'username_desc':
        next.sort((a, b) => b.username.localeCompare(a.username))
        break
      case 'created_desc':
      default:
        next.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
        break
    }
    return next
  }, [items, sortBy])

  const filteredResetRecords = useMemo(() => {
    const query = resetSearch.trim().toLowerCase()
    if (!query) {
      return resetRecords
    }
    return resetRecords.filter((item) => {
      return [item.username, item.display_name, item.email, item.status, item.status_label]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query))
    })
  }, [resetRecords, resetSearch])

  async function updateStatus(username: string, accountStatus: 'active' | 'suspended') {
    try {
      setSubmitting(true)
      await apiFetch(`/staff/users/${username}/status/`, {
        method: 'POST',
        body: JSON.stringify({ account_status: accountStatus }),
      })
      await loadUsers(filters)
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新會員狀態失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <h1>會員管理</h1>

      <div className="grid grid-3">
        <label className="field">
          <span>關鍵字搜尋</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="帳號或顯示名稱"
          />
        </label>
        <label className="field">
          <span>角色</span>
          <select value={filters.role} onChange={(event) => setFilters((prev) => ({ ...prev, role: event.target.value }))}>
            <option value="">全部角色</option>
            <option value="member">會員</option>
            <option value="seller">賣家</option>
            <option value="admin">管理者</option>
          </select>
        </label>
        <label className="field">
          <span>帳號狀態</span>
          <select
            value={filters.account_status}
            onChange={(event) => setFilters((prev) => ({ ...prev, account_status: event.target.value }))}
          >
            <option value="">全部狀態</option>
            <option value="active">正常</option>
            <option value="suspended">停權</option>
          </select>
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as UserSortKey)}>
            <option value="created_desc">建立時間新到舊</option>
            <option value="created_asc">建立時間舊到新</option>
            <option value="username_asc">帳號 A 到 Z</option>
            <option value="username_desc">帳號 Z 到 A</option>
          </select>
        </label>
      </div>

      <div className="row">
        <button className="btn btn-secondary" onClick={() => void loadUsers(filters)} type="button">
          套用篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <div className="muted">讀取會員資料中...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的會員。</div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>帳號</th>
              <th>顯示名稱</th>
              <th>角色</th>
              <th>Email</th>
              <th>建立時間</th>
              <th>狀態</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {sortedItems.map((item) => (
              <tr key={item.username}>
                <td>@{item.username}</td>
                <td>{item.display_name}</td>
                <td>{item.role}</td>
                <td>{item.email || '-'}</td>
                <td>{item.created_at ? item.created_at.slice(0, 16).replace('T', ' ') : '-'}</td>
                <td>{item.account_status || 'active'}</td>
                <td>
                  <div className="row">
                    <button
                      className="btn btn-secondary"
                      disabled={submitting}
                      onClick={() => void updateStatus(item.username, 'active')}
                      type="button"
                    >
                      啟用
                    </button>
                    <button
                      className="btn btn-secondary"
                      disabled={submitting}
                      onClick={() => void updateStatus(item.username, 'suspended')}
                      type="button"
                    >
                      停權
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <section className="card stack" style={{ marginTop: '1rem' }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: '1rem' }}>
          <div className="stack" style={{ gap: '0.35rem' }}>
            <h2 style={{ margin: 0 }}>密碼重設紀錄</h2>
            <p className="muted" style={{ margin: 0 }}>
              顯示最近產生的重設連結，可直接跳往開發信箱或開啟指定重設連結。
            </p>
          </div>
          <div className="row" style={{ alignItems: 'flex-end', flexWrap: 'wrap', gap: '0.75rem' }}>
            <label className="field" style={{ minWidth: 240 }}>
              <span>篩選紀錄</span>
              <input
                value={resetSearch}
                onChange={(event) => setResetSearch(event.target.value)}
                placeholder="帳號、名稱、Email、狀態"
              />
            </label>
            <Link className="btn btn-secondary" href="/dev/mailbox">
              前往開發信箱
            </Link>
          </div>
        </div>

        {!filteredResetRecords.length ? (
          <div className="muted">目前沒有符合條件的重設紀錄。</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>帳號</th>
                <th>Email</th>
                <th>建立時間</th>
                <th>到期時間</th>
                <th>使用時間</th>
                <th>狀態</th>
                <th>連結</th>
              </tr>
            </thead>
            <tbody>
              {filteredResetRecords.map((item) => (
                <tr key={`${item.username}-${item.reset_url}`}>
                  <td>
                    {item.display_name}
                    <div className="muted">@{item.username}</div>
                  </td>
                  <td>{item.email}</td>
                  <td>{item.created_at_display || '-'}</td>
                  <td>{item.expires_at_display || '-'}</td>
                  <td>{item.used_at_display || '-'}</td>
                  <td>{item.status_label || item.status}</td>
                  <td>
                    <Link className="btn btn-secondary" href={item.reset_url} rel="noreferrer" target="_blank">
                      開啟
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </section>
  )
}

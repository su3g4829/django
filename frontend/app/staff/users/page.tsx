'use client'

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

type UserListPayload = {
  items: AdminUser[]
}

type UserSortKey = 'created_desc' | 'created_asc' | 'username_asc' | 'username_desc'

export default function AdminUsersPage() {
  const [items, setItems] = useState<AdminUser[]>([])
  const [filters, setFilters] = useState({ q: '', role: '', account_status: '' })
  const [sortBy, setSortBy] = useState<UserSortKey>('created_desc')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function loadUsers(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<UserListPayload>(`/staff/users/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '讀取會員列表失敗。')
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
          <span>搜尋關鍵字</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="帳號、顯示名稱"
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
            <option value="active">啟用中</option>
            <option value="suspended">已停權</option>
          </select>
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as UserSortKey)}>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="username_asc">帳號：A 到 Z</option>
            <option value="username_desc">帳號：Z 到 A</option>
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
        <div className="muted">正在讀取會員資料...</div>
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
    </section>
  )
}

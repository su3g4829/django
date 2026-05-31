'use client'

import { type ChangeEvent, useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import { bannerImageRules, validateBannerImageFile } from '@/lib/banner-image'
import type { Banner, BannerListPayload } from '@/lib/types'

type BannerEditor = Banner & {
  replacementImage?: File | null
}

type AdminCreateFormState = {
  title: string
  copy_text: string
  link_url: string
  starts_at: string
  ends_at: string
  position: string
  note: string
  is_active: boolean
  image: File | null
}

type ApprovedFilter = 'all' | 'active' | 'expired'

const POSITION_OPTIONS = [{ value: 'home_main', label: '首頁主 Banner' }]

const EMPTY_CREATE_FORM: AdminCreateFormState = {
  title: '',
  copy_text: '',
  link_url: '',
  starts_at: '',
  ends_at: '',
  position: 'home_main',
  note: '',
  is_active: true,
  image: null,
}

function toEditor(item: Banner): BannerEditor {
  return { ...item, replacementImage: null }
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

function isBannerNotFoundError(message: string) {
  return /banner not found/i.test(message)
}

function buildAdminCreateFormData(form: AdminCreateFormState) {
  const formData = new FormData()
  formData.set('title', form.title)
  formData.set('copy_text', form.copy_text)
  formData.set('link_url', form.link_url)
  formData.set('starts_at', form.starts_at)
  formData.set('ends_at', form.ends_at)
  formData.set('position', form.position)
  formData.set('note', form.note)
  formData.set('is_active', form.is_active ? 'true' : 'false')
  if (form.image) {
    formData.set('image', form.image)
  }
  return formData
}

function buildAdminUpdateFormData(item: BannerEditor) {
  const formData = new FormData()
  formData.set('title', item.title ?? '')
  formData.set('copy_text', item.copy_text ?? '')
  formData.set('link_url', item.link_url ?? '')
  formData.set('starts_at', item.starts_at ?? '')
  formData.set('ends_at', item.ends_at ?? '')
  formData.set('position', item.position ?? 'home_main')
  formData.set('note', item.note ?? '')
  formData.set('is_active', item.is_active ? 'true' : 'false')
  formData.set('sort_order', String(item.sort_order))
  if (item.replacementImage) {
    formData.set('image', item.replacementImage)
  }
  return formData
}

function formatDateTime(value?: string) {
  if (!value) {
    return '未提供'
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(parsed)
}

function isExpiredBanner(item: Banner) {
  if (!item.ends_at) {
    return false
  }
  const today = new Date()
  const todayKey = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const endDate = new Date(`${item.ends_at}T00:00:00`).getTime()
  return Number.isFinite(endDate) && endDate < todayKey
}

export default function AdminBannersPage() {
  const [items, setItems] = useState<BannerEditor[]>([])
  const [createForm, setCreateForm] = useState<AdminCreateFormState>(EMPTY_CREATE_FORM)
  const [reviewDrafts, setReviewDrafts] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [approvedFilter, setApprovedFilter] = useState<ApprovedFilter>('all')
  const [expandedApprovedId, setExpandedApprovedId] = useState<number | null>(null)
  const [expandedRejectedId, setExpandedRejectedId] = useState<number | null>(null)

  const pendingItems = useMemo(() => items.filter((item) => item.status === 'pending'), [items])
  const approvedItems = useMemo(
    () =>
      [...items.filter((item) => item.status === 'approved')].sort(
        (left, right) => left.sort_order - right.sort_order || left.id - right.id,
      ),
    [items],
  )
  const rejectedItems = useMemo(
    () =>
      [...items.filter((item) => item.status === 'rejected')].sort(
        (left, right) => {
          const leftTime = left.created_at ? new Date(left.created_at).getTime() : 0
          const rightTime = right.created_at ? new Date(right.created_at).getTime() : 0
          return rightTime - leftTime || right.id - left.id
        },
      ),
    [items],
  )

  const approvedActiveItems = useMemo(() => approvedItems.filter((item) => item.is_currently_visible), [approvedItems])
  const approvedExpiredItems = useMemo(() => approvedItems.filter((item) => isExpiredBanner(item)), [approvedItems])
  const filteredApprovedItems = useMemo(() => {
    if (approvedFilter === 'active') {
      return approvedActiveItems
    }
    if (approvedFilter === 'expired') {
      return approvedExpiredItems
    }
    return approvedItems
  }, [approvedActiveItems, approvedExpiredItems, approvedFilter, approvedItems])

  async function loadBanners(showLoading = true) {
    if (showLoading) {
      setLoading(true)
    }
    try {
      const payload = await apiFetch<BannerListPayload>('/staff/banners/')
      setItems(payload.items.map(toEditor))
      setError('')
    } catch (fetchError) {
      setError(getErrorMessage(fetchError, '讀取 Banner 列表失敗。'))
    } finally {
      if (showLoading) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    void loadBanners()
  }, [])

  function updateItem(id: number, patch: Partial<BannerEditor>) {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)))
  }

  function moveReviewedItem(id: number, direction: -1 | 1) {
    setItems((current) => {
      const pending = current.filter((item) => item.status === 'pending')
      const rejected = current.filter((item) => item.status === 'rejected')
      const reviewed = [...current.filter((item) => item.status === 'approved')].sort(
        (left, right) => left.sort_order - right.sort_order || left.id - right.id,
      )
      const index = reviewed.findIndex((item) => item.id === id)
      const nextIndex = index + direction
      if (index < 0 || nextIndex < 0 || nextIndex >= reviewed.length) {
        return current
      }

      ;[reviewed[index], reviewed[nextIndex]] = [reviewed[nextIndex], reviewed[index]]
      const reordered = reviewed.map((item, orderIndex) => ({ ...item, sort_order: orderIndex + 1 }))
      return [...pending, ...reordered, ...rejected]
    })
  }

  async function handleValidatedImage(file: File | null, onValid: (file: File | null) => void) {
    if (!file) {
      onValid(null)
      return
    }
    try {
      await validateBannerImageFile(file)
      onValid(file)
      setError('')
    } catch (validationError) {
      onValid(null)
      setError(getErrorMessage(validationError, 'Banner 圖片驗證失敗。'))
      setSuccess('')
    }
  }

  async function createBanner() {
    if (!createForm.image) {
      setError('請先選擇 Banner 圖片。')
      setSuccess('')
      return
    }

    try {
      setSaving(true)
      await apiFetch<Banner>('/staff/banners/', {
        method: 'POST',
        body: buildAdminCreateFormData(createForm),
      })
      setCreateForm(EMPTY_CREATE_FORM)
      await loadBanners(false)
      setSuccess('管理者 Banner 已建立。')
      setError('')
    } catch (requestError) {
      setError(getErrorMessage(requestError, '建立 Banner 失敗。'))
      setSuccess('')
    } finally {
      setSaving(false)
    }
  }

  async function saveBanner(item: BannerEditor) {
    try {
      setSaving(true)
      await apiFetch<Banner>(`/staff/banners/${item.id}/`, {
        method: 'PUT',
        body: buildAdminUpdateFormData(item),
      })
      await loadBanners(false)
      setSuccess('Banner 修改已儲存。')
      setError('')
    } catch (requestError) {
      const message = getErrorMessage(requestError, '儲存 Banner 失敗。')
      if (isBannerNotFoundError(message)) {
        await loadBanners(false)
        setError('這筆 Banner 已不存在，列表已重新同步。')
      } else {
        setError(message)
      }
      setSuccess('')
    } finally {
      setSaving(false)
    }
  }

  async function reviewBanner(item: BannerEditor, approved: boolean) {
    try {
      setSaving(true)
      await apiFetch<Banner>(`/staff/banners/${item.id}/review/`, {
        method: 'POST',
        body: JSON.stringify({
          approved,
          rejection_reason: reviewDrafts[item.id] ?? '',
        }),
      })
      setReviewDrafts((current) => ({ ...current, [item.id]: '' }))
      await loadBanners(false)
      setSuccess(approved ? '申請已核准。' : '申請已拒絕。')
      setError('')
    } catch (requestError) {
      const message = getErrorMessage(requestError, '審核 Banner 申請失敗。')
      if (isBannerNotFoundError(message)) {
        await loadBanners(false)
        setError('這筆 Banner 已不存在，列表已重新同步。')
      } else {
        setError(message)
      }
      setSuccess('')
    } finally {
      setSaving(false)
    }
  }

  async function saveOrder() {
    try {
      setSaving(true)
      const payload = await apiFetch<BannerListPayload>('/staff/banners/reorder/', {
        method: 'POST',
        body: JSON.stringify({ ids: approvedItems.map((item) => item.id) }),
      })
      setItems(payload.items.map(toEditor))
      setSuccess('首頁排序已儲存。')
      setError('')
    } catch (requestError) {
      setError(getErrorMessage(requestError, '儲存排序失敗。'))
      setSuccess('')
    } finally {
      setSaving(false)
    }
  }

  async function deleteBanner(id: number) {
    try {
      setSaving(true)
      await apiFetch(`/staff/banners/${id}/`, { method: 'DELETE' })
      if (expandedApprovedId === id) {
        setExpandedApprovedId(null)
      }
      if (expandedRejectedId === id) {
        setExpandedRejectedId(null)
      }
      await loadBanners(false)
      setSuccess('Banner 已刪除。')
      setError('')
    } catch (requestError) {
      const message = getErrorMessage(requestError, '刪除 Banner 失敗。')
      if (isBannerNotFoundError(message)) {
        await loadBanners(false)
        setError('這筆 Banner 已不存在，列表已重新同步。')
      } else {
        setError(message)
      }
      setSuccess('')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <section className="card">正在讀取 Banner 管理資料...</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>首頁 Banner 審核與管理</h1>
        <p className="muted">管理者可以查看申請、預覽圖片、核准或拒絕、設定排序、設定檔期，以及手動上架或下架。</p>
      </section>

      <section className="card stack">
        <h2>上架規格</h2>
        <div className="grid grid-3">
          <div className="card stack">
            <strong>後台限制</strong>
            <span className="muted">
              {bannerImageRules.width} x {bannerImageRules.height} px
            </span>
          </div>
          <div className="card stack">
            <strong>顯示比例</strong>
            <span className="muted">1120 x 420</span>
          </div>
          <div className="card stack">
            <strong>格式 / 大小</strong>
            <span className="muted">
              {bannerImageRules.allowedExtensions.join(', ')} / {bannerImageRules.maxFileSizeMb} MB 以下
            </span>
          </div>
        </div>
      </section>

      {error ? <div className="notice">{error}</div> : null}
      {success ? <div className="notice success">{success}</div> : null}

      <section className="card stack">
        <h2>管理者直接建立 Banner</h2>
        <div className="grid grid-2">
          <label className="field">
            <span>宣傳標題</span>
            <input value={createForm.title} onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))} />
          </label>
          <label className="field">
            <span>活動連結</span>
            <input value={createForm.link_url} onChange={(event) => setCreateForm((current) => ({ ...current, link_url: event.target.value }))} />
          </label>
        </div>
        <label className="field">
          <span>宣傳文案</span>
          <textarea rows={3} value={createForm.copy_text} onChange={(event) => setCreateForm((current) => ({ ...current, copy_text: event.target.value }))} />
        </label>
        <div className="grid grid-3">
          <label className="field">
            <span>開始日期</span>
            <input type="date" value={createForm.starts_at} onChange={(event) => setCreateForm((current) => ({ ...current, starts_at: event.target.value }))} />
          </label>
          <label className="field">
            <span>結束日期</span>
            <input type="date" value={createForm.ends_at} onChange={(event) => setCreateForm((current) => ({ ...current, ends_at: event.target.value }))} />
          </label>
          <label className="field">
            <span>宣傳位置</span>
            <select value={createForm.position} onChange={(event) => setCreateForm((current) => ({ ...current, position: event.target.value }))}>
              {POSITION_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field">
          <span>管理備註</span>
          <textarea rows={3} value={createForm.note} onChange={(event) => setCreateForm((current) => ({ ...current, note: event.target.value }))} />
        </label>
        <div className="grid grid-2">
          <label className="field">
            <span>Banner 圖片</span>
            <input
              accept=".jpg,.jpeg,.png,.webp"
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                void handleValidatedImage(event.target.files?.[0] ?? null, (file) => setCreateForm((current) => ({ ...current, image: file })))
              }
              type="file"
            />
          </label>
          <label className="field">
            <span>手動上架</span>
            <select value={createForm.is_active ? 'true' : 'false'} onChange={(event) => setCreateForm((current) => ({ ...current, is_active: event.target.value === 'true' }))}>
              <option value="true">上架</option>
              <option value="false">下架</option>
            </select>
          </label>
        </div>
        <div className="row">
          <button className="btn" disabled={saving} onClick={createBanner} type="button">
            建立 Banner
          </button>
        </div>
      </section>

      <section className="card stack">
        <h2>待審核申請</h2>
        {!pendingItems.length ? <div className="muted">目前沒有待審核的 Banner 申請。</div> : null}
        {pendingItems.map((item) => (
          <article className="card stack" key={item.id}>
            <div className="promotion-application-card">
              <div className="promotion-application-card__preview">
                <img alt={item.title || `banner-${item.id}`} src={toBackendAssetUrl(item.image_path)} />
              </div>
              <div className="stack" style={{ flex: 1 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <strong>{item.title || '未填標題'}</strong>
                  <span className="badge">{item.status_label || item.status}</span>
                </div>
                <div className="muted">
                  申請人：{item.applicant_display_name || item.applicant_username} ({item.applicant_username})
                </div>
                <div className="muted">申請時間：{formatDateTime(item.created_at)}</div>
                {item.copy_text ? <div>{item.copy_text}</div> : null}
                <div className="muted">
                  檔期：{item.starts_at} - {item.ends_at}
                </div>
                <div className="muted">位置：{item.position_label || item.position}</div>
                {item.link_url ? <div className="muted">連結：{item.link_url}</div> : null}
                {item.note ? <div className="muted">備註：{item.note}</div> : null}
                <label className="field">
                  <span>拒絕原因</span>
                  <textarea
                    rows={2}
                    value={reviewDrafts[item.id] ?? ''}
                    onChange={(event) => setReviewDrafts((current) => ({ ...current, [item.id]: event.target.value }))}
                  />
                </label>
                <div className="row">
                  <button className="btn" disabled={saving} onClick={() => reviewBanner(item, true)} type="button">
                    核准申請
                  </button>
                  <button className="btn btn-secondary" disabled={saving} onClick={() => reviewBanner(item, false)} type="button">
                    拒絕申請
                  </button>
                </div>
              </div>
            </div>
          </article>
        ))}
      </section>

      <section className="card stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2>已審核 Banner</h2>
          <button className="btn btn-secondary" disabled={saving || !approvedItems.length} onClick={saveOrder} type="button">
            儲存首頁排序
          </button>
        </div>

        <div className="row">
          <button
            className={`btn ${approvedFilter === 'all' ? '' : 'btn-secondary'}`}
            disabled={saving}
            onClick={() => setApprovedFilter('all')}
            type="button"
          >
            全部 {approvedItems.length}
          </button>
          <button
            className={`btn ${approvedFilter === 'active' ? '' : 'btn-secondary'}`}
            disabled={saving}
            onClick={() => setApprovedFilter('active')}
            type="button"
          >
            上架中 {approvedActiveItems.length}
          </button>
          <button
            className={`btn ${approvedFilter === 'expired' ? '' : 'btn-secondary'}`}
            disabled={saving}
            onClick={() => setApprovedFilter('expired')}
            type="button"
          >
            已過期 {approvedExpiredItems.length}
          </button>
        </div>

        {!filteredApprovedItems.length ? <div className="muted">目前沒有符合篩選條件的已審核 Banner。</div> : null}
        {filteredApprovedItems.map((item, index) => {
          const isExpanded = expandedApprovedId === item.id
          const actualIndex = approvedItems.findIndex((entry) => entry.id === item.id)

          return (
            <article className="card stack" key={item.id}>
              <button
                className="banner-list-summary"
                onClick={() => setExpandedApprovedId((current) => (current === item.id ? null : item.id))}
                type="button"
              >
                <div className="banner-list-summary__main">
                  <strong>{item.title || '未填標題 Banner'}</strong>
                  <div className="muted">申請人：{item.applicant_display_name || item.applicant_username}</div>
                  <div className="muted">申請時間：{formatDateTime(item.created_at)}</div>
                </div>
                <div className="banner-list-summary__meta">
                  <div className="row" style={{ justifyContent: 'flex-end' }}>
                    <span className="badge">{item.status_label || item.status}</span>
                    <span className="badge">{item.is_active ? '手動上架' : '手動下架'}</span>
                    <span className="badge">{item.is_currently_visible ? '首頁顯示中' : isExpiredBanner(item) ? '已過期' : '目前未顯示'}</span>
                  </div>
                  <span className="muted">{isExpanded ? '收起內容' : '展開內容'}</span>
                </div>
              </button>

              {isExpanded ? (
                <div className="admin-banner-card">
                  <div className="admin-banner-card__preview">
                    <img alt={item.title || `banner-${item.id}`} src={toBackendAssetUrl(item.image_path)} />
                  </div>
                  <div className="stack" style={{ flex: 1 }}>
                    <div className="grid grid-2">
                      <label className="field">
                        <span>宣傳標題</span>
                        <input value={item.title ?? ''} onChange={(event) => updateItem(item.id, { title: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>活動連結</span>
                        <input value={item.link_url ?? ''} onChange={(event) => updateItem(item.id, { link_url: event.target.value })} />
                      </label>
                    </div>

                    <label className="field">
                      <span>宣傳文案</span>
                      <textarea rows={3} value={item.copy_text ?? ''} onChange={(event) => updateItem(item.id, { copy_text: event.target.value })} />
                    </label>

                    <div className="grid grid-3">
                      <label className="field">
                        <span>開始日期</span>
                        <input type="date" value={item.starts_at ?? ''} onChange={(event) => updateItem(item.id, { starts_at: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>結束日期</span>
                        <input type="date" value={item.ends_at ?? ''} onChange={(event) => updateItem(item.id, { ends_at: event.target.value })} />
                      </label>
                      <label className="field">
                        <span>宣傳位置</span>
                        <select value={item.position ?? 'home_main'} onChange={(event) => updateItem(item.id, { position: event.target.value })}>
                          {POSITION_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="grid grid-2">
                      <label className="field">
                        <span>手動上架 / 下架</span>
                        <select value={item.is_active ? 'true' : 'false'} onChange={(event) => updateItem(item.id, { is_active: event.target.value === 'true' })}>
                          <option value="true">上架</option>
                          <option value="false">下架</option>
                        </select>
                      </label>
                      <label className="field">
                        <span>替換圖片</span>
                        <input
                          accept=".jpg,.jpeg,.png,.webp"
                          onChange={(event: ChangeEvent<HTMLInputElement>) =>
                            void handleValidatedImage(event.target.files?.[0] ?? null, (file) => updateItem(item.id, { replacementImage: file }))
                          }
                          type="file"
                        />
                      </label>
                    </div>

                    <label className="field">
                      <span>管理備註</span>
                      <textarea rows={2} value={item.note ?? ''} onChange={(event) => updateItem(item.id, { note: event.target.value })} />
                    </label>

                    {item.rejection_reason ? <div className="notice">最近一次拒絕原因：{item.rejection_reason}</div> : null}

                    <div className="row">
                      <button className="btn btn-secondary" disabled={saving || actualIndex === 0} onClick={() => moveReviewedItem(item.id, -1)} type="button">
                        上移
                      </button>
                      <button
                        className="btn btn-secondary"
                        disabled={saving || actualIndex === approvedItems.length - 1}
                        onClick={() => moveReviewedItem(item.id, 1)}
                        type="button"
                      >
                        下移
                      </button>
                      <button className="btn" disabled={saving} onClick={() => saveBanner(item)} type="button">
                        儲存修改
                      </button>
                      <button className="btn btn-danger" disabled={saving} onClick={() => deleteBanner(item.id)} type="button">
                        刪除
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
            </article>
          )
        })}
      </section>

      <section className="card stack">
        <h2>已拒絕申請</h2>
        {!rejectedItems.length ? <div className="muted">目前沒有已拒絕的 Banner 申請。</div> : null}
        {rejectedItems.map((item) => {
          const isExpanded = expandedRejectedId === item.id

          return (
            <article className="card stack" key={item.id}>
              <button
                className="banner-list-summary"
                onClick={() => setExpandedRejectedId((current) => (current === item.id ? null : item.id))}
                type="button"
              >
                <div className="banner-list-summary__main">
                  <strong>{item.title || '未填標題'}</strong>
                  <div className="muted">申請人：{item.applicant_display_name || item.applicant_username}</div>
                  <div className="muted">申請時間：{formatDateTime(item.created_at)}</div>
                </div>
                <div className="banner-list-summary__meta">
                  <div className="row" style={{ justifyContent: 'flex-end' }}>
                    <span className="badge">{item.status_label || item.status}</span>
                  </div>
                  <span className="muted">{isExpanded ? '收起內容' : '展開內容'}</span>
                </div>
              </button>

              {isExpanded ? (
                <div className="promotion-application-card">
                  <div className="promotion-application-card__preview">
                    <img alt={item.title || `rejected-${item.id}`} src={toBackendAssetUrl(item.image_path)} />
                  </div>
                  <div className="stack" style={{ flex: 1 }}>
                    {item.copy_text ? <div>{item.copy_text}</div> : null}
                    <div className="muted">
                      申請人：{item.applicant_display_name || item.applicant_username} ({item.applicant_username})
                    </div>
                    <div className="muted">申請時間：{formatDateTime(item.created_at)}</div>
                    {item.rejection_reason ? <div className="notice">拒絕原因：{item.rejection_reason}</div> : null}
                    <div className="row">
                      <button className="btn btn-danger" disabled={saving} onClick={() => deleteBanner(item.id)} type="button">
                        刪除申請
                      </button>
                    </div>
                  </div>
                </div>
              ) : null}
            </article>
          )
        })}
      </section>
    </div>
  )
}

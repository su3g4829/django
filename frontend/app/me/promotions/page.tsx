'use client'

import { ChangeEvent, FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import { bannerImageRules, type BannerImageInspection, validateBannerImageFile } from '@/lib/banner-image'
import type { Banner, BannerListPayload } from '@/lib/types'

type PromotionFormState = {
  title: string
  copy_text: string
  link_url: string
  starts_at: string
  ends_at: string
  position: string
  note: string
  image: File | null
}

const POSITION_OPTIONS = [{ value: 'home_main', label: '首頁主 Banner' }]

const EMPTY_FORM: PromotionFormState = {
  title: '',
  copy_text: '',
  link_url: '',
  starts_at: '',
  ends_at: '',
  position: 'home_main',
  note: '',
  image: null,
}

function buildPromotionFormData(form: PromotionFormState) {
  const formData = new FormData()
  formData.set('title', form.title)
  formData.set('copy_text', form.copy_text)
  formData.set('link_url', form.link_url)
  formData.set('starts_at', form.starts_at)
  formData.set('ends_at', form.ends_at)
  formData.set('position', form.position)
  formData.set('note', form.note)
  if (form.image) {
    formData.set('image', form.image)
  }
  return formData
}

export default function PromotionApplicationsPage() {
  const [items, setItems] = useState<Banner[]>([])
  const [form, setForm] = useState<PromotionFormState>(EMPTY_FORM)
  const [imageInspection, setImageInspection] = useState<BannerImageInspection | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function loadApplications() {
    setLoading(true)
    try {
      const payload = await apiFetch<BannerListPayload>('/me/banner-applications/')
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入宣傳申請失敗。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadApplications()
  }, [])

  async function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    if (!file) {
      setForm((current) => ({ ...current, image: null }))
      setImageInspection(null)
      return
    }

    try {
      const inspection = await validateBannerImageFile(file)
      setForm((current) => ({ ...current, image: file }))
      setImageInspection(inspection)
      setError('')
    } catch (err) {
      setForm((current) => ({ ...current, image: null }))
      setImageInspection(null)
      setError(err instanceof Error ? err.message : 'Banner 圖片驗證失敗。')
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!form.image) {
      setError('請上傳 Banner 圖片。')
      return
    }

    try {
      setSubmitting(true)
      const created = await apiFetch<Banner>('/me/banner-applications/', {
        method: 'POST',
        body: buildPromotionFormData(form),
      })
      setItems((current) => [created, ...current])
      setForm(EMPTY_FORM)
      setImageInspection(null)
      setSuccess('宣傳申請已送出，等待管理者審核。')
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出宣傳申請失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入宣傳申請資料中...</section>
  }

  return (
    <div className="stack">
      <section className="hero">
        <h1>首頁宣傳申請</h1>
        <p className="muted">登入會員或商家帳號後，可提交首頁 Banner 宣傳申請，待管理者審核通過後才會在首頁顯示。</p>
      </section>

      <section className="card stack">
        <h2>Banner 規格</h2>
        <div className="grid grid-3">
          <div className="card stack">
            <strong>圖片上限</strong>
            <span className="muted">
              不得超過 {bannerImageRules.width} x {bannerImageRules.height} px
            </span>
          </div>
          <div className="card stack">
            <strong>建議顯示比例</strong>
            <span className="muted">1120 x 420，建議維持 2240:840 比例</span>
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
        <h2>填寫申請表</h2>
        <form className="stack" onSubmit={handleSubmit}>
          <div className="grid grid-2">
            <label className="field">
              <span>宣傳標題</span>
              <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
            </label>
            <label className="field">
              <span>活動連結</span>
              <input
                placeholder="/products/category/t-shirt"
                value={form.link_url}
                onChange={(event) => setForm((current) => ({ ...current, link_url: event.target.value }))}
              />
            </label>
          </div>

          <label className="field">
            <span>宣傳文案</span>
            <textarea rows={3} value={form.copy_text} onChange={(event) => setForm((current) => ({ ...current, copy_text: event.target.value }))} />
          </label>

          <div className="grid grid-3">
            <label className="field">
              <span>開始日期</span>
              <input type="date" value={form.starts_at} onChange={(event) => setForm((current) => ({ ...current, starts_at: event.target.value }))} />
            </label>
            <label className="field">
              <span>結束日期</span>
              <input type="date" value={form.ends_at} onChange={(event) => setForm((current) => ({ ...current, ends_at: event.target.value }))} />
            </label>
            <label className="field">
              <span>宣傳位置</span>
              <select value={form.position} onChange={(event) => setForm((current) => ({ ...current, position: event.target.value }))}>
                {POSITION_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="field">
            <span>申請原因 / 備註</span>
            <textarea rows={3} value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))} />
          </label>

          <label className="field">
            <span>Banner 圖片</span>
            <input accept=".jpg,.jpeg,.png,.webp" onChange={handleImageChange} type="file" />
          </label>

          <div className="notice">
            建議使用接近 2240 x 840 的橫幅比例。
            <br />
            若圖片比例不符，前台顯示時可能出現裁切或變形。
            <br />
            若比例偏差過大或影響宣傳品質，管理者可能拒絕申請。
          </div>

          {imageInspection ? (
            <div className={imageInspection.isRecommendedRatio ? 'notice success' : 'notice'}>
              目前圖片尺寸：{imageInspection.width} x {imageInspection.height} px。
              {imageInspection.isRecommendedRatio ? ' 比例符合建議。' : ' 比例與建議橫幅不一致，可能導致顯示變形。'}
            </div>
          ) : null}

          <div className="row">
            <button className="btn" disabled={submitting} type="submit">
              {submitting ? '送出中...' : '送出申請'}
            </button>
          </div>
        </form>
      </section>

      <section className="card stack">
        <h2>我的申請紀錄</h2>
        {!items.length ? <div className="muted">目前還沒有宣傳申請。</div> : null}
        {items.map((item) => (
          <article className="card stack" key={item.id}>
            <div className="promotion-application-card">
              <div className="promotion-application-card__preview">
                <img alt={item.title || `promotion-${item.id}`} src={toBackendAssetUrl(item.image_path)} />
              </div>
              <div className="stack" style={{ flex: 1 }}>
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <strong>{item.title || '未命名申請'}</strong>
                  <span className="badge">{item.status_label || item.status}</span>
                </div>
                {item.copy_text ? <div>{item.copy_text}</div> : null}
                <div className="muted">
                  檔期：{item.starts_at} 至 {item.ends_at}
                </div>
                <div className="muted">位置：{item.position_label || item.position}</div>
                {item.link_url ? <div className="muted">連結：{item.link_url}</div> : null}
                {item.note ? <div className="muted">備註：{item.note}</div> : null}
                {item.rejection_reason ? <div className="notice">拒絕原因：{item.rejection_reason}</div> : null}
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}

'use client'

import { ChangeEvent, FormEvent, useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import { toBackendAssetUrl } from '@/lib/assets'
import { bannerImageRules, type BannerImageInspection, validateBannerImageFile } from '@/lib/banner-image'
import type { Banner, BannerListPayload, Product, ProductListPayload } from '@/lib/types'

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

type LinkMode = 'product' | 'manual'

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

function buildProductPath(slug: string) {
  return slug ? `/products/${slug}` : ''
}

export default function PromotionApplicationsPage() {
  const [items, setItems] = useState<Banner[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [form, setForm] = useState<PromotionFormState>(EMPTY_FORM)
  const [linkMode, setLinkMode] = useState<LinkMode>('product')
  const [selectedProductSlug, setSelectedProductSlug] = useState('')
  const [imageInspection, setImageInspection] = useState<BannerImageInspection | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  async function loadApplications() {
    const payload = await apiFetch<BannerListPayload>('/me/banner-applications/')
    setItems(payload.items)
  }

  async function loadProducts() {
    const payload = await apiFetch<ProductListPayload>('/me/products/')
    const ownProducts = payload.items ?? []
    setProducts(ownProducts)

    if (!ownProducts.length) {
      setLinkMode('manual')
      setSelectedProductSlug('')
      return
    }

    setSelectedProductSlug((current) => current || ownProducts[0].slug)
  }

  useEffect(() => {
    async function bootstrap() {
      setLoading(true)
      try {
        await Promise.all([loadApplications(), loadProducts()])
        setError('')
      } catch (err) {
        setError(err instanceof Error ? err.message : '載入 Banner 申請資料失敗。')
      } finally {
        setLoading(false)
      }
    }

    void bootstrap()
  }, [])

  useEffect(() => {
    if (linkMode !== 'product') {
      return
    }

    setForm((current) => ({
      ...current,
      link_url: buildProductPath(selectedProductSlug),
    }))
  }, [linkMode, selectedProductSlug])

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
      setError('請選擇 Banner 圖片。')
      return
    }

    if (!form.link_url.trim()) {
      setError('請填寫活動連結。')
      return
    }

    try {
      setSubmitting(true)
      const created = await apiFetch<Banner>('/me/banner-applications/', {
        method: 'POST',
        body: buildPromotionFormData(form),
      })
      setItems((current) => [created, ...current])
      setForm({
        ...EMPTY_FORM,
        link_url: linkMode === 'product' ? buildProductPath(selectedProductSlug) : '',
      })
      setImageInspection(null)
      setSuccess('Banner 申請已送出，等待管理員審核。')
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '送出 Banner 申請失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  const resolvedProductPath = buildProductPath(selectedProductSlug)

  if (loading) {
    return <section className="card">載入 Banner 申請資料中...</section>
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
          <label className="field">
            <span>宣傳標題</span>
            <input value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} />
          </label>

          <div className="field">
            <span>活動連結</span>
              <div className="stack">
                <div className="promotion-link-mode">
                  <label className={`promotion-link-mode__option${linkMode === 'product' ? ' is-active' : ''}${!products.length ? ' is-disabled' : ''}`}>
                    <input
                    checked={linkMode === 'product'}
                    disabled={!products.length}
                    name="link_mode"
                    onChange={() => setLinkMode('product')}
                    type="radio"
                    value="product"
                    />
                    <div className="stack" style={{ gap: 4 }}>
                      <strong>從我的商品選擇</strong>
                      <span className="muted">直接挑選自己的商品，自動帶入商品頁路徑。</span>
                    </div>
                  </label>

                  <label className={`promotion-link-mode__option${linkMode === 'manual' ? ' is-active' : ''}`}>
                    <input checked={linkMode === 'manual'} name="link_mode" onChange={() => setLinkMode('manual')} type="radio" value="manual" />
                    <div className="stack" style={{ gap: 4 }}>
                      <strong>手動輸入</strong>
                      <span className="muted">可填其他站內頁面或自訂活動連結。</span>
                    </div>
                  </label>
                </div>

              {linkMode === 'product' ? (
                <div className="stack">
                  <select
                    disabled={!products.length}
                    value={selectedProductSlug}
                    onChange={(event) => setSelectedProductSlug(event.target.value)}
                  >
                    {products.length ? null : <option value="">目前沒有可選商品</option>}
                    {products.map((product) => (
                      <option key={product.id} value={product.slug}>
                        {product.name} ({product.slug})
                      </option>
                    ))}
                  </select>

                  <label className="field promotion-link-path">
                    <span className="muted">將套用的活動路徑</span>
                    <input disabled value={resolvedProductPath} />
                  </label>
                </div>
              ) : (
                <input
                  placeholder="/products/category/t-shirt"
                  value={form.link_url}
                  onChange={(event) => setForm((current) => ({ ...current, link_url: event.target.value }))}
                />
              )}
            </div>
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
            建議上傳至少 2240 x 840 的圖片。
            <br />
            圖片內容請避免過多文字，以免首頁縮圖後影響閱讀。
            <br />
            日期區間會影響 Banner 顯示時段，請確認後再送出申請。
          </div>

          {imageInspection ? (
            <div className={imageInspection.isRecommendedRatio ? 'notice success' : 'notice'}>
              目前圖片尺寸：{imageInspection.width} x {imageInspection.height} px。
              {imageInspection.isRecommendedRatio ? ' 比例符合建議。' : ' 比例與建議不同，前台顯示時可能會裁切。'}
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
        {!items.length ? <div className="muted">目前還沒有 Banner 申請紀錄。</div> : null}
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
                  時間：{item.starts_at} 到 {item.ends_at}
                </div>
                <div className="muted">位置：{item.position_label || item.position}</div>
                {item.link_url ? <div className="muted">連結：{item.link_url}</div> : null}
                {item.note ? <div className="muted">備註：{item.note}</div> : null}
                {item.rejection_reason ? <div className="notice">退回原因：{item.rejection_reason}</div> : null}
              </div>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}

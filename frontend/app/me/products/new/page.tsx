'use client'

/**
 * 賣家新增商品頁
 *
 * 功能：
 * - 建立商品基本資料
 * - 上傳商品圖片
 *
 * 主要 API：
 * - POST `/api/v1/me/products/`
 */

import { FormEvent, useState } from 'react'

import { apiFetch } from '@/lib/api'

const EMPTY_FORM = {
  name: '',
  price: '',
  compare_at_price: '',
  stock: '0',
  brand: '',
  category: '',
  status: 'draft',
  tags: '',
  specs: '',
  variants: '',
}

export default function SellerProductCreatePage() {
  /** 商品建立表單。 */
  const [form, setForm] = useState(EMPTY_FORM)
  /** 使用者挑選的新圖片檔案。 */
  const [files, setFiles] = useState<FileList | null>(null)
  /** 送出建立商品時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * 提交新增商品表單。
   *
   * event:
   * - form submit 事件，需先阻止預設送出行為。
   */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError('')
      const payload = new FormData()
      Object.entries(form).forEach(([key, value]) => payload.append(key, value))
      Array.from(files ?? []).forEach((file) => payload.append('images', file))
      const created = await apiFetch<{ slug: string }>('/me/products/', {
        method: 'POST',
        body: payload,
      })
      window.location.href = `/me/products/${created.slug}`
    } catch (err) {
      setError(err instanceof Error ? err.message : '建立商品失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      {/* 新增商品表單：建立商品基本資料與圖片。 */}
      <h1>新增商品</h1>
      <p className="muted">可在此建立商品基本資料、圖片、規格與變體資訊。</p>
      {error ? <div className="notice">{error}</div> : null}
      <form className="grid grid-2" onSubmit={handleSubmit}>
        {/* 商品主欄位：名稱、品牌、價格、庫存、分類、狀態。 */}
        <label className="field">
          <span>商品名稱</span>
          <input value={form.name} onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))} />
        </label>
        <label className="field">
          <span>品牌</span>
          <input value={form.brand} onChange={(event) => setForm((prev) => ({ ...prev, brand: event.target.value }))} />
        </label>
        <label className="field">
          <span>售價</span>
          <input value={form.price} onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))} />
        </label>
        <label className="field">
          <span>原價</span>
          <input value={form.compare_at_price} onChange={(event) => setForm((prev) => ({ ...prev, compare_at_price: event.target.value }))} />
        </label>
        <label className="field">
          <span>庫存</span>
          <input value={form.stock} onChange={(event) => setForm((prev) => ({ ...prev, stock: event.target.value }))} />
        </label>
        <label className="field">
          <span>分類</span>
          <input value={form.category} onChange={(event) => setForm((prev) => ({ ...prev, category: event.target.value }))} />
        </label>
        <label className="field">
          <span>狀態</span>
          <select value={form.status} onChange={(event) => setForm((prev) => ({ ...prev, status: event.target.value }))}>
            <option value="draft">草稿</option>
            <option value="pending">待審核</option>
            <option value="active">上架中</option>
          </select>
        </label>
        <label className="field">
          <span>標籤</span>
          <input value={form.tags} onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))} />
        </label>
        {/* 長文字欄位：規格與變體 / SKU。 */}
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>商品規格</span>
          <textarea rows={5} value={form.specs} onChange={(event) => setForm((prev) => ({ ...prev, specs: event.target.value }))} />
        </label>
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>變體 / SKU</span>
          <textarea rows={6} value={form.variants} onChange={(event) => setForm((prev) => ({ ...prev, variants: event.target.value }))} />
        </label>
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>商品圖片</span>
          <input multiple type="file" onChange={(event) => setFiles(event.target.files)} />
        </label>
        <div className="row">
          {/* 提交建立商品。 */}
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '建立中…' : '建立商品'}
          </button>
        </div>
      </form>
    </section>
  )
}

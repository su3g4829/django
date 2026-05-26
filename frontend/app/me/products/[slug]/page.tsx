'use client'

/**
 * 賣家商品編輯頁
 *
 * 功能：
 * - 讀取單一商品
 * - 更新商品資料
 * - 管理既有圖片、新增圖片與刪除標記
 *
 * 主要 API：
 * - GET `/api/v1/me/products/:slug/`
 * - PUT `/api/v1/me/products/:slug/`
 */

import { FormEvent, useEffect, useMemo, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { Product } from '@/lib/types'

type EditableProduct = Product & {
  specs_text?: string
  variants_text?: string
}

export default function SellerProductEditPage({ params }: { params: { slug: string } }) {
  /** 從動態路由解析出的商品 slug。 */
  const slug = useMemo(() => params.slug, [params.slug])
  /** 後端載入的原始商品資料。 */
  const [product, setProduct] = useState<EditableProduct | null>(null)
  /** 可編輯表單內容。 */
  const [form, setForm] = useState({
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
  })
  /** 這次新增上傳的圖片。 */
  const [files, setFiles] = useState<FileList | null>(null)
  /** 既有圖片路徑。 */
  const [existingImages, setExistingImages] = useState<string[]>([])
  /** 被標記為待刪除的既有圖片路徑。 */
  const [removedImages, setRemovedImages] = useState<string[]>([])
  /** 初次載入商品資料時的狀態。 */
  const [loading, setLoading] = useState(true)
  /** 儲存商品時的狀態。 */
  const [submitting, setSubmitting] = useState(false)
  /** API 錯誤訊息。 */
  const [error, setError] = useState('')
  /** 成功訊息。 */
  const [message, setMessage] = useState('')

  useEffect(() => {
    /** 依 slug 載入商品資料並回填表單。 */
    setLoading(true)
    apiFetch<EditableProduct>(`/me/products/${slug}/`)
      .then((payload) => {
        setProduct(payload)
        setExistingImages(payload.images ?? [])
        setRemovedImages([])
        setForm({
          name: payload.name ?? '',
          price: String(payload.price ?? ''),
          compare_at_price: payload.compare_at_price ? String(payload.compare_at_price) : '',
          stock: String(payload.stock ?? 0),
          brand: payload.brand ?? '',
          category: payload.category ?? '',
          status: payload.status ?? 'draft',
          tags: Array.isArray(payload.tags) ? payload.tags.join(', ') : '',
          specs: payload.specs_text ?? '',
          variants: payload.variants_text ?? '',
        })
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [slug])

  /**
   * 提交商品更新表單。
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
      existingImages.forEach((image) => {
        if (!removedImages.includes(image)) {
          payload.append('existing_image_paths', image)
        }
      })
      removedImages.forEach((image) => payload.append('remove_image_paths', image))
      Array.from(files ?? []).forEach((file) => payload.append('images', file))
      const updated = await apiFetch<EditableProduct>(`/me/products/${slug}/`, {
        method: 'PUT',
        body: payload,
      })
      setProduct(updated)
      setExistingImages(updated.images ?? [])
      setRemovedImages([])
      setFiles(null)
      setMessage('商品資料已更新。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新商品失敗，請稍後再試。')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return <section className="card">載入商品資料中…</section>
  }

  /**
   * 調整既有圖片順序。
   *
   * index:
   * - 目前圖片所在的位置。
   * direction:
   * - `-1` 代表往前移，`1` 代表往後移。
   */
  function moveImage(index: number, direction: -1 | 1) {
    setExistingImages((prev) => {
      const next = [...prev]
      const target = index + direction
      if (target < 0 || target >= next.length) return prev
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  /**
   * 切換圖片是否標記為刪除。
   *
   * image:
   * - 既有圖片路徑。
   */
  function toggleRemoveImage(image: string) {
    setRemovedImages((prev) => (prev.includes(image) ? prev.filter((item) => item !== image) : [...prev, image]))
  }

  return (
    <section className="card stack">
      {/* 頁首與返回列表入口。 */}
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h1>編輯商品</h1>
          <p className="muted">目前正在編輯 `{product?.name ?? slug}`。</p>
        </div>
        <a className="btn btn-secondary" href="/me/products">
          返回商品列表
        </a>
      </div>

      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}
      {product?.review_note ? <div className="notice">{product.review_note}</div> : null}

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
            <option value="archived">封存</option>
          </select>
        </label>
        <label className="field">
          <span>標籤</span>
          <input value={form.tags} onChange={(event) => setForm((prev) => ({ ...prev, tags: event.target.value }))} />
        </label>
        {/* 長文字欄位：規格與變體 / SKU 描述。 */}
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>商品規格</span>
          <textarea rows={5} value={form.specs} onChange={(event) => setForm((prev) => ({ ...prev, specs: event.target.value }))} />
        </label>
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>變體 / SKU</span>
          <textarea rows={6} value={form.variants} onChange={(event) => setForm((prev) => ({ ...prev, variants: event.target.value }))} />
        </label>
        <label className="field" style={{ gridColumn: '1 / -1' }}>
          <span>追加圖片</span>
          <input multiple type="file" onChange={(event) => setFiles(event.target.files)} />
        </label>
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          {/* 既有圖片管理區：調整順序、標記刪除。 */}
          <span>既有圖片管理</span>
          {!existingImages.length ? (
            <div className="muted">目前沒有任何既有圖片。</div>
          ) : (
            <div className="grid grid-3">
              {existingImages.map((image, index) => {
                const removed = removedImages.includes(image)
                return (
                  <div className="card stack" key={`${image}-${index}`}>
                    {/* 單張既有圖片卡：可移動順序，也可標記為刪除。 */}
                    <div className="muted">圖片 {index + 1}</div>
                    <img alt={product?.name ?? 'product'} className="product-image" src={image} />
                    <div className="row">
                      <button className="btn btn-secondary" onClick={() => moveImage(index, -1)} type="button">
                        往前
                      </button>
                      <button className="btn btn-secondary" onClick={() => moveImage(index, 1)} type="button">
                        往後
                      </button>
                    </div>
                    <button className="btn btn-secondary" onClick={() => toggleRemoveImage(image)} type="button">
                      {removed ? '取消刪除標記' : '標記刪除'}
                    </button>
                    {removed ? <div className="notice">這張圖片會在儲存時刪除。</div> : null}
                  </div>
                )
              })}
            </div>
          )}
        </div>
        <div className="row">
          {/* 儲存商品變更。 */}
          <button className="btn" disabled={submitting} type="submit">
            {submitting ? '儲存中…' : '儲存商品'}
          </button>
        </div>
      </form>
    </section>
  )
}

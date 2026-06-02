'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, toQueryString } from '@/lib/api'
import type { ProductCategoryOption } from '@/lib/types'

type AdminProduct = {
  id: number
  slug: string
  name: string
  category: string
  category_slug?: string
  brand: string
  price: number
  compare_at_price?: number | null
  stock?: number | null
  stock_display?: string
  status?: string
  status_label?: string
  owner_username?: string
  owner_display_name?: string
  primary_image?: string
  created_at_display?: string
  updated_at_display?: string
}

type ProductListPayload = {
  items: AdminProduct[]
}

const EMPTY_FILTERS = {
  q: '',
  status: '',
  category: '',
  brand: '',
  owner: '',
}

type ProductSortKey =
  | 'updated_desc'
  | 'updated_asc'
  | 'created_desc'
  | 'created_asc'
  | 'price_desc'
  | 'price_asc'
  | 'stock_desc'
  | 'stock_asc'
  | 'name_asc'

function compareNullableNumber(a?: number | null, b?: number | null) {
  return Number(a ?? -1) - Number(b ?? -1)
}

export default function AdminProductsPage() {
  const [items, setItems] = useState<AdminProduct[]>([])
  const [categories, setCategories] = useState<ProductCategoryOption[]>([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [categoryForm, setCategoryForm] = useState({ name: '', slug: '' })
  const [sortBy, setSortBy] = useState<ProductSortKey>('updated_desc')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function loadProducts(nextFilters = filters) {
    setLoading(true)
    try {
      const payload = await apiFetch<ProductListPayload>(`/staff/products/${toQueryString(nextFilters)}`)
      setItems(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法載入商品列表。')
    } finally {
      setLoading(false)
    }
  }

  async function loadCategories() {
    try {
      const payload = await apiFetch<{ items: ProductCategoryOption[] }>('/staff/product-categories/')
      setCategories(payload.items)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '無法載入商品分類。')
    }
  }

  useEffect(() => {
    void loadProducts()
    void loadCategories()
  }, [])

  const sortedItems = useMemo(() => {
    const next = [...items]
    switch (sortBy) {
      case 'updated_asc':
        next.sort((a, b) => String(a.updated_at_display || '').localeCompare(String(b.updated_at_display || '')))
        break
      case 'created_desc':
        next.sort((a, b) => String(b.created_at_display || '').localeCompare(String(a.created_at_display || '')))
        break
      case 'created_asc':
        next.sort((a, b) => String(a.created_at_display || '').localeCompare(String(b.created_at_display || '')))
        break
      case 'price_desc':
        next.sort((a, b) => b.price - a.price)
        break
      case 'price_asc':
        next.sort((a, b) => a.price - b.price)
        break
      case 'stock_desc':
        next.sort((a, b) => compareNullableNumber(b.stock, a.stock))
        break
      case 'stock_asc':
        next.sort((a, b) => compareNullableNumber(a.stock, b.stock))
        break
      case 'name_asc':
        next.sort((a, b) => a.name.localeCompare(b.name))
        break
      case 'updated_desc':
      default:
        next.sort((a, b) => String(b.updated_at_display || '').localeCompare(String(a.updated_at_display || '')))
        break
    }
    return next
  }, [items, sortBy])

  async function handleStaleProduct() {
    await loadProducts(filters)
    setError('')
    setMessage('商品列表已重新整理。')
  }

  async function createCategory() {
    const name = categoryForm.name.trim()
    if (!name) {
      setError('請輸入分類名稱。')
      return
    }
    try {
      setSubmitting(true)
      setMessage('')
      await apiFetch('/staff/product-categories/', {
        method: 'POST',
        body: JSON.stringify({
          name,
          slug: categoryForm.slug.trim(),
        }),
      })
      setCategoryForm({ name: '', slug: '' })
      await loadCategories()
      setMessage('商品分類已建立。')
    } catch (err) {
      setError(err instanceof Error ? err.message : '建立商品分類失敗。')
    } finally {
      setSubmitting(false)
    }
  }

  async function archiveProduct(slug: string) {
    try {
      setSubmitting(true)
      setMessage('')
      await apiFetch(`/staff/products/${slug}/archive/`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Archived by admin.' }),
      })
      await loadProducts(filters)
      setMessage('商品已下架。')
    } catch (err) {
      const detail = err instanceof Error ? err.message : '下架商品失敗。'
      if (detail.toLowerCase().includes('not found')) {
        await handleStaleProduct()
      } else {
        setError(detail)
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function publishProduct(slug: string) {
    try {
      setSubmitting(true)
      setMessage('')
      await apiFetch(`/staff/products/${slug}/publish/`, {
        method: 'POST',
        body: JSON.stringify({ note: 'Published by admin.' }),
      })
      await loadProducts(filters)
      setMessage('商品已上架。')
    } catch (err) {
      const detail = err instanceof Error ? err.message : '上架商品失敗。'
      if (detail.toLowerCase().includes('not found')) {
        await handleStaleProduct()
      } else {
        setError(detail)
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function deleteProduct(slug: string) {
    if (!window.confirm('確定要刪除此商品嗎？這個動作無法復原。')) {
      return
    }
    try {
      setSubmitting(true)
      setMessage('')
      await apiFetch(`/staff/products/${slug}/`, { method: 'DELETE' })
      await loadProducts(filters)
      setMessage('商品已刪除。')
    } catch (err) {
      const detail = err instanceof Error ? err.message : '刪除商品失敗。'
      if (detail.toLowerCase().includes('not found')) {
        await handleStaleProduct()
      } else {
        setError(detail)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card stack">
      <div className="stack" style={{ gap: '0.25rem' }}>
        <h1>商品管理</h1>
        <p className="muted">管理者可在此檢視商品、建立商品分類，並對商品執行上架、下架或刪除。</p>
      </div>

      <section className="card stack">
        <div className="stack" style={{ gap: '0.25rem' }}>
          <h2>商品分類主表</h2>
          <p className="muted">賣家新增或編輯商品時，分類選單與前台商品篩選都會讀這份主表。</p>
        </div>

        <div className="grid grid-3">
          <label className="field">
            <span>分類名稱</span>
            <input
              value={categoryForm.name}
              onChange={(event) => setCategoryForm((current) => ({ ...current, name: event.target.value }))}
              placeholder="例如：上衣"
            />
          </label>
          <label className="field">
            <span>分類 slug</span>
            <input
              value={categoryForm.slug}
              onChange={(event) => setCategoryForm((current) => ({ ...current, slug: event.target.value }))}
              placeholder="可留空，自動產生"
            />
          </label>
          <div className="field" style={{ alignSelf: 'end' }}>
            <button className="btn" disabled={submitting} onClick={() => void createCategory()} type="button">
              建立分類
            </button>
          </div>
        </div>

        <div className="row" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
          {categories.map((category) => (
            <span key={category.slug} className="badge">
              {category.label} ({category.slug})
            </span>
          ))}
        </div>
      </section>

      <div className="grid grid-3">
        <label className="field">
          <span>關鍵字</span>
          <input
            value={filters.q}
            onChange={(event) => setFilters((prev) => ({ ...prev, q: event.target.value }))}
            placeholder="商品名稱、slug、品牌或賣家"
          />
        </label>
        <label className="field">
          <span>狀態</span>
          <select value={filters.status} onChange={(event) => setFilters((prev) => ({ ...prev, status: event.target.value }))}>
            <option value="">全部狀態</option>
            <option value="active">上架中</option>
            <option value="draft">草稿</option>
            <option value="archived">已下架</option>
          </select>
        </label>
        <label className="field">
          <span>分類</span>
          <select value={filters.category} onChange={(event) => setFilters((prev) => ({ ...prev, category: event.target.value }))}>
            <option value="">全部分類</option>
            {categories.map((category) => (
              <option key={category.slug} value={category.slug}>
                {category.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>品牌</span>
          <input value={filters.brand} onChange={(event) => setFilters((prev) => ({ ...prev, brand: event.target.value }))} />
        </label>
        <label className="field">
          <span>賣家</span>
          <input value={filters.owner} onChange={(event) => setFilters((prev) => ({ ...prev, owner: event.target.value }))} />
        </label>
        <label className="field">
          <span>排序</span>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as ProductSortKey)}>
            <option value="updated_desc">更新時間：新到舊</option>
            <option value="updated_asc">更新時間：舊到新</option>
            <option value="created_desc">建立時間：新到舊</option>
            <option value="created_asc">建立時間：舊到新</option>
            <option value="price_desc">價格：高到低</option>
            <option value="price_asc">價格：低到高</option>
            <option value="stock_desc">庫存：高到低</option>
            <option value="stock_asc">庫存：低到高</option>
            <option value="name_asc">名稱：A 到 Z</option>
          </select>
        </label>
      </div>

      <div className="row">
        <button className="btn btn-secondary" onClick={() => void loadProducts(filters)} type="button">
          套用篩選
        </button>
        <button
          className="btn btn-secondary"
          onClick={() => {
            setFilters(EMPTY_FILTERS)
            void loadProducts(EMPTY_FILTERS)
          }}
          type="button"
        >
          清除篩選
        </button>
      </div>

      {error ? <div className="notice">{error}</div> : null}
      {message ? <div className="notice success">{message}</div> : null}

      {loading ? (
        <div className="muted">載入商品中...</div>
      ) : !sortedItems.length ? (
        <div className="muted">目前沒有符合條件的商品。</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>縮圖</th>
                <th>商品</th>
                <th>分類</th>
                <th>品牌</th>
                <th>原價</th>
                <th>售價</th>
                <th>庫存</th>
                <th>狀態</th>
                <th>賣家</th>
                <th>建立時間</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item) => (
                <tr key={item.slug}>
                  <td>
                    {item.primary_image ? (
                      <img alt={item.name} className="management-thumbnail" src={item.primary_image} />
                    ) : (
                      <div className="muted">無圖片</div>
                    )}
                  </td>
                  <td>
                    <strong>{item.name}</strong>
                    <div className="muted">{item.slug}</div>
                  </td>
                  <td>{item.category || '-'}</td>
                  <td>{item.brand || '-'}</td>
                  <td>{item.compare_at_price ? `$${item.compare_at_price.toFixed(2)}` : '-'}</td>
                  <td>${item.price.toFixed(2)}</td>
                  <td>{item.stock_display || (item.stock ?? '-')}</td>
                  <td>{item.status_label || item.status || '-'}</td>
                  <td>
                    {item.owner_display_name || '-'}
                    <div className="muted">@{item.owner_username || '-'}</div>
                  </td>
                  <td>{item.created_at_display || '-'}</td>
                  <td>
                    <div className="stack" style={{ gap: '0.5rem' }}>
                      {item.status === 'active' ? (
                        <Link href={`/products/${item.slug}`}>查看前台</Link>
                      ) : (
                        <span className="muted">尚未公開</span>
                      )}
                      <Link href={`/me/products/${item.slug}?returnTo=/staff/products`}>編輯商品</Link>
                      {item.status === 'active' ? (
                        <button
                          className="btn btn-secondary"
                          disabled={submitting}
                          onClick={() => void archiveProduct(item.slug)}
                          type="button"
                        >
                          下架
                        </button>
                      ) : (
                        <button
                          className="btn btn-secondary"
                          disabled={submitting}
                          onClick={() => void publishProduct(item.slug)}
                          type="button"
                        >
                          上架
                        </button>
                      )}
                      <button className="btn btn-danger" disabled={submitting} onClick={() => void deleteProduct(item.slug)} type="button">
                        刪除
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

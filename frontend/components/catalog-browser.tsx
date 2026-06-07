'use client'

/**
 * 商品總覽共用瀏覽器。
 *
 * 這個元件會被多個頁面重用，例如：
 * - 全商品列表 `/products`
 * - 品牌頁
 * - 分類頁
 *
 * 它是 Client Component，因為會用到：
 * - `useState`
 * - `useEffect`
 * - `useMemo`
 * - `window.history.replaceState`
 *
 * 來源模組：
 * - React hooks 來自 `react`
 * - `apiFetch` / `toQueryString` 來自專案自己的 `frontend/lib/api.ts`
 * - `ProductCard` 來自共用展示元件
 */
import { useEffect, useMemo, useState } from 'react'

import { ProductCard } from '@/components/product-card'
import { apiFetch, toQueryString } from '@/lib/api'
import type { ProductCategoryOption, ProductListPayload } from '@/lib/types'

/**
 * CatalogBrowser 的外部輸入。
 *
 * `initialFilters` 是可選的，代表不同頁面可以預先帶入不同查詢條件。
 * 例如品牌頁會先帶 `brand`，分類頁會先帶 `category`。
 */
type CatalogBrowserProps = {
  title: string
  intro: string
  initialFilters?: {
    q?: string
    category?: string
    brand?: string
    color?: string
    size?: string
    page?: number
  }
  syncUrl?: boolean
}

export function CatalogBrowser({ title, intro, initialFilters, syncUrl = false }: CatalogBrowserProps) {
  /**
   * `query` 保存目前的查詢條件。
   *
   * 這裡用 `useState({...})` 而不是把每個欄位拆開，是因為它們會一起組成
   * `/products/?q=...&brand=...` 這種 API request。
   */
  const [query, setQuery] = useState({
    q: initialFilters?.q ?? '',
    category: initialFilters?.category ?? '',
    brand: initialFilters?.brand ?? '',
    color: initialFilters?.color ?? '',
    size: initialFilters?.size ?? '',
    page: initialFilters?.page ?? 1,
  })

  /**
   * `data` 保存後端回來的完整 payload。
   *
   * 它不是只有商品陣列，還包含：
   * - `items`
   * - `facets`
   * - `meta`
   *
   * 因為第一次 render 尚未載入完成，所以型別是 `ProductListPayload | null`。
   */
  const [data, setData] = useState<ProductListPayload | null>(null)

  /**
   * `loading` 與 `error` 是典型的資料抓取狀態。
   * 這種寫法來自常見 React data-fetching pattern。
   */
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  /**
   * `requestPath` 是送往 `/api/v1/products/` 的相對路徑。
   *
   * `useMemo` 來自 React。
   * 用途是：只有當 `query` 改變時，才重新計算 query string。
   */
  const requestPath = useMemo(() => `/products/${toQueryString(query)}`, [query])

  /**
   * 抓商品列表。
   *
   * `useEffect` 來自 React，專門處理 render 後的副作用。
   * 這裡不能直接在 render 階段呼叫 `apiFetch(...)`，
   * 否則每次 render 都會重複打 API。
   */
  useEffect(() => {
    setLoading(true)
    apiFetch<ProductListPayload>(requestPath)
      .then((payload) => {
        setData(payload)
        setError('')
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [requestPath])

  /**
   * 可選擇把目前篩選條件同步回網址列。
   *
   * `window.history.replaceState` 來自瀏覽器 History API。
   * 這裡用 `replaceState` 而不是 `pushState`，是因為每次切 filter 都只是更新目前畫面狀態，
   * 不想把每次小變更都塞成新的瀏覽紀錄。
   */
  useEffect(() => {
    if (!syncUrl || typeof window === 'undefined') {
      return
    }
    const nextUrl = `${window.location.pathname}${toQueryString(query)}`
    const currentUrl = `${window.location.pathname}${window.location.search}`
    if (nextUrl !== currentUrl) {
      window.history.replaceState(window.history.state, '', nextUrl)
    }
  }, [query, syncUrl])

  return (
    <div className="stack">
      <section className="hero">
        <h1>{title}</h1>
        <p className="muted">{intro}</p>
      </section>

      <section className="card stack">
        <div className="grid catalog-grid">
          <label className="field">
            <span>關鍵字搜尋</span>
            <input
              value={query.q}
              onChange={(event) => setQuery((prev) => ({ ...prev, q: event.target.value, page: 1 }))}
            />
          </label>

          <label className="field">
            <span>分類</span>
            <select
              value={query.category}
              onChange={(event) => setQuery((prev) => ({ ...prev, category: event.target.value, page: 1 }))}
            >
              <option value="">全部分類</option>
              {(data?.facets?.categories ?? []).map((item: ProductCategoryOption) => (
                <option key={item.slug} value={item.slug}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>品牌</span>
            <select
              value={query.brand}
              onChange={(event) => setQuery((prev) => ({ ...prev, brand: event.target.value, page: 1 }))}
            >
              <option value="">全部品牌</option>
              {data?.facets?.brands?.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>顏色</span>
            <select
              value={query.color}
              onChange={(event) => setQuery((prev) => ({ ...prev, color: event.target.value, page: 1 }))}
            >
              <option value="">全部顏色</option>
              {data?.facets?.colors?.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>尺寸</span>
            <select
              value={query.size}
              onChange={(event) => setQuery((prev) => ({ ...prev, size: event.target.value, page: 1 }))}
            >
              <option value="">全部尺寸</option>
              {data?.facets?.sizes?.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <section className="card">商品載入中...</section>
      ) : (
        <>
          <section className="grid product-list-grid">
            {data?.items?.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </section>

          {data?.meta?.total_pages && data.meta.total_pages > 1 ? (
            <section className="row" style={{ justifyContent: 'center' }}>
              <button
                className="btn btn-secondary"
                disabled={query.page <= 1}
                onClick={() => setQuery((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }))}
                type="button"
              >
                上一頁
              </button>
              <span className="muted">
                第 {data.meta.page} / {data.meta.total_pages} 頁
              </span>
              <button
                className="btn btn-secondary"
                disabled={query.page >= data.meta.total_pages}
                onClick={() =>
                  setQuery((prev) => ({
                    ...prev,
                    page: Math.min(data.meta.total_pages ?? prev.page, prev.page + 1),
                  }))
                }
                type="button"
              >
                下一頁
              </button>
            </section>
          ) : null}
        </>
      )}
    </div>
  )
}

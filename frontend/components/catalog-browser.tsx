'use client'

/**
 * 商品目錄瀏覽元件
 *
 * 功能：
 * - 呼叫 Django DRF 的 `/api/v1/products/` 取得商品列表
 * - 提供搜尋、分類、品牌、顏色、尺寸等篩選
 * - 控制分頁切換
 *
 * 使用位置：
 * - 首頁精選商品頁
 * - 商品總覽頁
 * - 品牌頁 / 分類頁
 */
import { useEffect, useMemo, useState } from 'react'

import { ProductCard } from '@/components/product-card'
import { apiFetch, toQueryString } from '@/lib/api'
import type { ProductCategoryOption, ProductListPayload } from '@/lib/types'

/**
 * 傳入目錄元件的外部參數。
 *
 * title:
 * - 頁面主標題，例如「全部商品」或「ACME 品牌商品」
 *
 * intro:
 * - 頁面簡介文字，說明此列表的用途或篩選範圍
 *
 * initialFilters:
 * - 初始篩選條件
 * - 可用於品牌頁、分類頁預先帶入對應參數
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

/**
 * 商品列表主要互動畫面。
 */
export function CatalogBrowser({ title, intro, initialFilters, syncUrl = false }: CatalogBrowserProps) {
  /**
   * query:
   * - 目前列表查詢條件
   * - 內容會轉成 query string，送到 Django DRF `/products/`
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
   * data:
   * - 後端回傳的商品列表 payload
   * - 包含 items、facets、meta 等資訊
   */
  const [data, setData] = useState<ProductListPayload | null>(null)

  /** loading: 是否正在向後端讀取資料。 */
  const [loading, setLoading] = useState(true)

  /** error: API 呼叫失敗時顯示的錯誤訊息。 */
  const [error, setError] = useState('')

  /**
   * requestPath:
   * - 將目前的 query 狀態組成 API 路徑
   * - 例如 `/products/?brand=ACME&page=2`
   */
  const requestPath = useMemo(() => `/products/${toQueryString(query)}`, [query])

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
      {/* 頁首說明區：顯示目前頁面標題與簡介。 */}
      <section className="hero">
        <h1>{title}</h1>
        <p className="muted">{intro}</p>
      </section>

      {/* 篩選表單：控制搜尋與各種 facet 條件。 */}
      <section className="card stack">
        <div className="grid catalog-grid">
          <label className="field">
            <span>搜尋關鍵字</span>
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

      {/* 錯誤訊息區：API 失敗時提示使用者。 */}
      {error ? <div className="notice">{error}</div> : null}

      {loading ? (
        <section className="card">正在載入商品資料…</section>
      ) : (
        <>
          {/* 商品卡片列表：逐筆渲染後端回傳的商品。 */}
          <section className="grid product-list-grid">
            {data?.items?.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </section>

          {/* 分頁控制區：顯示目前頁碼與前後頁按鈕。 */}
          <section className="row" style={{ justifyContent: 'space-between' }}>
            <span className="muted">
              第 {data?.meta.page ?? 1} / {data?.meta.total_pages ?? 1} 頁，共 {data?.meta.total_items ?? 0} 筆
            </span>
            <div className="row">
              <button
                className="btn btn-secondary"
                disabled={(data?.meta.page ?? 1) <= 1}
                onClick={() => setQuery((prev) => ({ ...prev, page: prev.page - 1 }))}
                type="button"
              >
                上一頁
              </button>
              <button
                className="btn btn-secondary"
                disabled={!data || data.meta.page >= data.meta.total_pages}
                onClick={() => setQuery((prev) => ({ ...prev, page: prev.page + 1 }))}
                type="button"
              >
                下一頁
              </button>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

'use client'

/**
 * 商品卡片元件。
 *
 * 這個元件專門負責「單一商品摘要」的顯示，不處理列表查詢或資料抓取。
 * 來源上會被：
 * - 商品列表
 * - 品牌頁
 * - 分類頁
 * 等多個頁面重用。
 */

import Link from 'next/link'

import { toBackendAssetUrl } from '@/lib/assets'
import { sortSizeValues } from '@/lib/product-variants'
import type { Product } from '@/lib/types'

type ProductCardProps = {
  product: Product
}

export function ProductCard({ product }: ProductCardProps) {
  /**
   * `Boolean(...)` 是 JavaScript 內建轉型寫法。
   * 這裡用來把品牌是否存在收斂成單純的 `true/false`。
   */
  const hasBrand = Boolean(product.brand && product.brand.toLowerCase() !== 'none')

  const hasColors = Boolean(product.color_options?.length)
  const hasSizes = Boolean(product.size_options?.length)

  /**
   * 尺寸顯示不直接用原始順序，而是經過 helper 正規化排序。
   * 這樣像 `S / M / L / XL` 才不會變成字串排序的混亂順序。
   */
  const orderedSizes = hasSizes ? sortSizeValues(product.size_options ?? []) : []

  /**
   * 賣家顯示名稱優先順序：
   * 1. `owner_display_name`
   * 2. `owner_username`
   *
   * 如果兩者都存在，會組成 `顯示名稱 (@username)`，方便辨識。
   */
  const sellerLabel =
    product.owner_display_name || product.owner_username
      ? `${product.owner_display_name || product.owner_username}${product.owner_username ? ` (@${product.owner_username})` : ''}`
      : ''

  return (
    <article className="card stack">
      {product.primary_image ? (
        <img alt={product.name} className="product-image product-card-image" src={toBackendAssetUrl(product.primary_image)} />
      ) : (
        <div className="product-image product-card-image" />
      )}

      <div className="stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <strong>{product.name}</strong>
          {hasBrand ? <span className="badge">{product.brand}</span> : null}
        </div>

        <div className="muted">
          {product.category} / {product.price_range_label ?? `$${product.price.toFixed(2)}`}
        </div>
        {sellerLabel ? <div className="muted">賣家：{sellerLabel}</div> : null}

        {hasColors ? <div className="muted">顏色：{product.color_options?.join(', ')}</div> : null}
        {hasSizes ? <div className="muted">尺寸：{orderedSizes.join(', ')}</div> : null}
      </div>

      <Link className="btn" href={`/products/${product.slug}`}>
        查看商品
      </Link>
    </article>
  )
}

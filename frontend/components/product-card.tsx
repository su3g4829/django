'use client'

import Link from 'next/link'

import { toBackendAssetUrl } from '@/lib/assets'
import { sortSizeValues } from '@/lib/product-variants'
import type { Product } from '@/lib/types'

type ProductCardProps = {
  product: Product
}

export function ProductCard({ product }: ProductCardProps) {
  const hasBrand = Boolean(product.brand && product.brand.toLowerCase() !== 'none')
  const hasColors = Boolean(product.color_options?.length)
  const hasSizes = Boolean(product.size_options?.length)
  const orderedSizes = hasSizes ? sortSizeValues(product.size_options ?? []) : []
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

'use client'

/**
 * 商品卡片元件
 *
 * 功能：
 * - 顯示單一商品的縮圖、名稱、品牌、分類與價格資訊
 * - 顯示可選顏色與尺寸摘要
 * - 提供前往商品詳情頁的連結
 */
import Link from 'next/link'

import type { Product } from '@/lib/types'

/**
 * 商品卡片外部參數。
 *
 * product:
 * - 後端回傳的單筆商品資料
 * - 內容包含基本資訊、圖片、顏色選項、尺寸選項等
 */
type ProductCardProps = {
  product: Product
}

/**
 * 單一商品卡片。
 */
export function ProductCard({ product }: ProductCardProps) {
  return (
    <article className="card stack">
      {/* 商品主圖：若尚未有圖片，保留空白框避免版面跳動。 */}
      {product.primary_image ? (
        <img alt={product.name} className="product-image" src={product.primary_image} />
      ) : (
        <div className="product-image" />
      )}

      {/* 商品摘要資訊：名稱、品牌、分類、價格。 */}
      <div className="stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <strong>{product.name}</strong>
          <span className="badge">{product.brand}</span>
        </div>

        <div className="muted">
          {product.category} · {product.price_range_label ?? `$${product.price.toFixed(2)}`}
        </div>

        <div className="muted">顏色：{product.color_options?.join(', ') || '尚未設定'}</div>
        <div className="muted">尺寸：{product.size_options?.join(', ') || '尚未設定'}</div>
      </div>

      {/* CTA：導向商品詳情頁。 */}
      <Link className="btn" href={`/products/${product.slug}`}>
        查看商品
      </Link>
    </article>
  )
}

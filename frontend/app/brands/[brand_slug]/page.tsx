/**
 * 品牌商品頁
 *
 * 功能：
 * - 依品牌 slug 建立品牌篩選條件
 * - 重用共用商品瀏覽元件顯示該品牌商品
 *
 * 主要 API：
 * - GET `/api/v1/products/`
 */

import { CatalogBrowser } from '@/components/catalog-browser'

type BrandPageProps = {
  /** `brand_slug` 來自 `/brands/[brand_slug]` 動態路由。 */
  params: Promise<{ brand_slug: string }>
}

/**
 * 品牌頁元件。
 *
 * params:
 * - `brand_slug`: URL 中的品牌 slug，會先解碼，再傳給商品列表作為初始篩選條件。
 */
export default async function BrandPage({ params }: BrandPageProps) {
  const { brand_slug } = await params

  /** 將網址中的品牌 slug 轉回可讀字串。 */
  const brand = decodeURIComponent(brand_slug)

  return (
    /**
     * 本頁不自行組裝商品列表 JSX，
     * 而是把品牌條件交給 `CatalogBrowser`，
     * 由它統一處理 hero、篩選與商品卡片顯示。
     */
    <CatalogBrowser
      title={`品牌：${brand}`}
      intro="這一頁會將品牌名稱當成預設篩選條件，並透過 Django DRF 商品列表 API 取得資料。"
      initialFilters={{ brand }}
    />
  )
}

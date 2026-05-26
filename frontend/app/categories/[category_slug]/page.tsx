/**
 * 分類商品頁
 *
 * 功能：
 * - 依分類 slug 建立分類篩選條件
 * - 重用共用商品瀏覽元件顯示該分類商品
 *
 * 主要 API：
 * - GET `/api/v1/products/`
 */

import { CatalogBrowser } from '@/components/catalog-browser'

type CategoryPageProps = {
  /** `category_slug` 來自 `/categories/[category_slug]` 動態路由。 */
  params: Promise<{ category_slug: string }>
}

/**
 * 分類頁元件。
 *
 * params:
 * - `category_slug`: URL 中的分類 slug，會先解碼，再傳給商品列表作為初始篩選條件。
 */
export default async function CategoryPage({ params }: CategoryPageProps) {
  const { category_slug } = await params

  /** 將網址中的分類 slug 轉回可讀字串。 */
  const category = decodeURIComponent(category_slug)

  return (
    /**
     * 本頁不自行組裝商品列表 JSX，
     * 而是把分類條件交給 `CatalogBrowser`，
     * 由它統一負責篩選與列表呈現。
     */
    <CatalogBrowser
      title={`分類：${category}`}
      intro="這一頁會將分類名稱當成預設篩選條件，並透過 Django DRF 商品列表 API 取得資料。"
      initialFilters={{ category }}
    />
  )
}

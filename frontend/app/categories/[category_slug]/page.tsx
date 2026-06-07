/**
 * 分類商品頁。
 *
 * 功能：
 * - 依分類 slug 建立商品列表初始篩選條件
 * - 重用 `CatalogBrowser` 顯示該分類下的商品
 *
 * 來源：
 * - Next.js App Router 動態路由 `app/categories/[category_slug]`
 * - 商品列表資料流與 UI 來自 `@/components/catalog-browser`
 */

import { CatalogBrowser } from '@/components/catalog-browser'

type CategoryPageProps = {
  /** `category_slug` 由動態路由解析後以 Promise 形式提供。 */
  params: Promise<{ category_slug: string }>
}

/**
 * 分類頁元件。
 *
 * 用法：
 * - `/categories/tops` 會把 `tops` 傳給 `CatalogBrowser`
 * - `CatalogBrowser` 再用 `initialFilters.category` 呼叫商品列表 API
 *
 * 程式語法：
 * - 這裡使用 `async` 是因為 App Router 的 `params` 型別是 Promise
 * - 必須先 `await params` 才能取出 `category_slug`
 */
export default async function CategoryPage({ params }: CategoryPageProps) {
  const { category_slug } = await params

  return (
    <CatalogBrowser
      title="分類商品"
      intro="這一頁會把分類 slug 當成預設篩選條件，並透過 Django DRF 商品列表 API 載入對應商品。"
      initialFilters={{ category: category_slug }}
    />
  )
}

/**
 * 商品列表頁
 *
 * 功能：
 * - 顯示商品列表
 * - 提供搜尋、篩選、排序、分頁
 *
 * 主要 API：
 * - GET `/api/v1/products/`
 */

import { CatalogBrowser } from '@/components/catalog-browser'

/**
 * 商品列表頁元件。
 *
 * 畫面本身由 Next.js 呈現，實際商品資料則由 Django DRF 商品列表 API 提供。
 */
export default function ProductsPage() {
  /**
   * 商品總覽頁同樣交由 `CatalogBrowser` 統一處理：
   * - 篩選
   * - facet 選項
   * - 商品卡片
   * - 分頁
   */
  return <CatalogBrowser title="商品列表" intro="瀏覽所有商品，資料由 Next.js 呼叫 Django DRF 商品列表 API 取得。" />
}

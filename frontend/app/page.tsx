/**
 * 首頁
 *
 * 功能：
 * - 作為 Next.js 前端主入口頁
 * - 重用商品瀏覽元件顯示首頁可見商品
 *
 * 主要 API：
 * - GET `/api/v1/products/`
 */

import { CatalogBrowser } from '@/components/catalog-browser'

/**
 * Next.js 首頁元件。
 *
 * 這個頁面會重用共用的商品瀏覽元件，將首頁當成精簡版商品入口。
 * 商品資料本身仍由 Django DRF `/api/v1/products/` 提供。
 */
export default function HomePage() {
  /**
   * 首頁畫面本身不直接組複雜 JSX，
   * 而是把顯示責任交給 `CatalogBrowser`：
   * - hero 標題
   * - 商品篩選列
   * - 商品卡片列表
   * - 分頁切換
   */
  return <CatalogBrowser title="精選商品首頁" intro="這裡是 Next.js 的主要前台入口頁，會透過 Django DRF 商品 API 取得商品資料。" />
}

import { CatalogBrowser } from '@/components/catalog-browser'
import { HomeBannerCarousel } from '@/components/home-banner-carousel'

/**
 * 首頁是純 Server Component。
 *
 * 這裡只負責組首頁版型：
 * 1. 先顯示 Banner 輪播
 * 2. 再顯示可直接操作的商品總覽
 *
 * 來源：
 * - 這個檔案位於 `app/page.tsx`，屬於 Next.js App Router 的根首頁路由
 * - 沒有 `use client`，所以預設是 Server Component
 *
 * 為什麼保持 server component：
 * - 首頁本身不需要本地 state
 * - 只做版型組裝，真正抓資料與互動都下放到 client child component
 * - 這樣首頁檔案本身可以維持很薄，責任單純
 */
export default function HomePage() {
  return (
    <div className="stack">
      <HomeBannerCarousel />
      <CatalogBrowser
        title="商品列表"
        intro="瀏覽所有商品，資料由 Next.js 呼叫 Django DRF 商品列表 API 取得。"
      />
    </div>
  )
}

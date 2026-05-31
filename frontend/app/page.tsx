import { CatalogBrowser } from '@/components/catalog-browser'
import { HomeBannerCarousel } from '@/components/home-banner-carousel'

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

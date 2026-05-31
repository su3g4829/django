import { CatalogBrowser } from '@/components/catalog-browser'

type ProductsPageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

function pickSearchParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? '' : value ?? ''
}

function parsePositivePage(value: string) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

export default async function ProductsPage({ searchParams }: ProductsPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : {}

  return (
    <CatalogBrowser
      title="商品列表"
      intro="瀏覽所有商品，資料由 Next.js 呼叫 Django DRF 商品列表 API 取得。"
      initialFilters={{
        q: pickSearchParam(resolvedSearchParams.q),
        category: pickSearchParam(resolvedSearchParams.category),
        brand: pickSearchParam(resolvedSearchParams.brand),
        color: pickSearchParam(resolvedSearchParams.color),
        size: pickSearchParam(resolvedSearchParams.size),
        page: parsePositivePage(pickSearchParam(resolvedSearchParams.page)),
      }}
      syncUrl
    />
  )
}

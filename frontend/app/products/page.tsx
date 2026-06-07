import { CatalogBrowser } from '@/components/catalog-browser'

type ProductsPageProps = {
  /**
   * `searchParams`
   * 來源：Next.js App Router。
   *
   * 在 server page 中，query string 會以 Promise 形式傳進來；
   * 需要先 `await` 才能拿到真正的查詢物件。
   */
  searchParams?: Promise<Record<string, string | string[] | undefined>>
}

/**
 * Next.js App Router 會把 query string 以字串或陣列形式交進來。
 * 這個 helper 專門把它收斂成單一字串，避免下游元件到處判斷型別。
 *
 * 程式語法：
 * - `string | string[] | undefined` 是 TypeScript union type
 * - 表示這個值可能是單一字串、字串陣列，或根本不存在
 */
function pickSearchParam(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] ?? '' : value ?? ''
}

/**
 * 商品列表的頁碼只接受正整數。
 * 如果 URL 被手動改壞，就回退到第 1 頁。
 */
function parsePositivePage(value: string) {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1
}

/**
 * 商品總覽頁是 Server Component。
 *
 * 它的責任只有兩件事：
 * 1. 從 URL 取出初始篩選條件
 * 2. 把初始條件交給 `CatalogBrowser`，由 client component 接手互動
 *
 * 程式語法：
 * - `async function` 是因為這裡需要 `await searchParams`
 * - `searchParams ? await searchParams : {}` 代表：
 *   - 有提供 query 時就等它 resolve
 *   - 沒提供時退回空物件
 */
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

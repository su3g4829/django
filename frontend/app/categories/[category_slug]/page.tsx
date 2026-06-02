import { CatalogBrowser } from '@/components/catalog-browser'

type CategoryPageProps = {
  params: Promise<{ category_slug: string }>
}

export default async function CategoryPage({ params }: CategoryPageProps) {
  const { category_slug } = await params

  return (
    <CatalogBrowser
      title="分類商品"
      intro="依商品分類瀏覽目前可購買的商品。"
      initialFilters={{ category: category_slug }}
    />
  )
}

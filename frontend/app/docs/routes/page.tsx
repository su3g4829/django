'use client'

/**
 * 前端頁面與 Django DRF API 對照文件頁。
 *
 * 功能：
 * - 整理常用前端頁面會呼叫哪些 DRF API
 * - 讓開發時快速查「這個頁面資料從哪來」
 * - 方便前後端對照與除錯
 */

type RouteRow = {
  page: string
  drf: string
  note: string
}

type RouteGroup = {
  title: string
  rows: RouteRow[]
}

const routeGroups: RouteGroup[] = [
  {
    title: '商品與公開內容',
    rows: [
      { page: '/products', drf: 'GET /api/v1/products/', note: '商品列表與篩選' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/', note: '商品詳情' },
      { page: '/products/[slug]', drf: 'GET/POST /api/v1/products/:slug/reviews/', note: '商品評論列表與新增' },
      { page: '/products/[slug]', drf: 'GET/POST /api/v1/products/:slug/questions/', note: '商品問答列表與新增問題' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/price-compare/', note: '商品比價資料' },
      { page: '/products/[slug]', drf: 'POST /api/v1/products/:slug/price-compare/refresh/', note: '手動刷新比價資料' },
      { page: '/products/compare', drf: 'GET /api/v1/products/compare/', note: '比較清單' },
      { page: '/products/compare', drf: 'POST /api/v1/products/:slug/compare/', note: '切換比較狀態' },
      { page: '/brands/[brand_slug]', drf: 'GET /api/v1/products/?brand=...', note: '品牌商品頁' },
      { page: '/categories/[category_slug]', drf: 'GET /api/v1/products/?category=...', note: '分類商品頁' },
      { page: '/community', drf: 'GET/POST /api/v1/community/posts/', note: '社群文章列表與發文' },
      { page: '/community/[id]', drf: 'GET /api/v1/community/posts/:id/', note: '社群文章詳情' },
    ],
  },
  {
    title: '會員與交易流程',
    rows: [
      { page: '/login', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/login/', note: '登入' },
      { page: '/register', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/register/', note: '註冊' },
      { page: '/me/dashboard', drf: 'GET /api/v1/me/dashboard/', note: '會員中心摘要' },
      { page: '/me/profile', drf: 'GET/POST /api/v1/me/profile/', note: '會員資料讀寫' },
      { page: '/me/addresses', drf: 'GET/POST /api/v1/me/addresses/', note: '地址簿' },
      { page: '/me/invoice', drf: 'GET/POST /api/v1/me/invoice/', note: '發票資料' },
      { page: '/orders', drf: 'GET /api/v1/me/orders/', note: '買家訂單列表' },
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/', note: '買家訂單詳情' },
      { page: '/cart', drf: 'GET /api/v1/cart/', note: '購物車' },
      { page: '/cart', drf: 'POST /api/v1/cart/items/', note: '加入購物車' },
      { page: '/checkout', drf: 'GET /api/v1/checkout/preview/', note: '結帳預覽' },
      { page: '/checkout', drf: 'POST /api/v1/checkout/confirm/', note: '建立訂單' },
      { page: '/checkout', drf: 'POST /api/v1/checkout/logistics/store-map/prepare/', note: '超商選店 scaffold' },
      { page: '/checkout', drf: 'GET /api/v1/checkout/logistics/store-selection/?token=...', note: '查詢選店結果' },
    ],
  },
  {
    title: '藍新 Sandbox',
    rows: [
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/newebpay-payment/sandbox/', note: '查看 sandbox payment 狀態' },
      { page: '/orders/[id]', drf: 'POST /api/v1/me/orders/:id/newebpay-payment/sandbox/', note: '產生 sandbox payment payload' },
      { page: 'Callback', drf: 'POST /api/v1/integrations/newebpay/payment/sandbox/callback/', note: 'sandbox callback 回寫' },
    ],
  },
  {
    title: '賣家與管理後台',
    rows: [
      { page: '/me/products', drf: 'GET /api/v1/me/products/', note: '賣家商品列表' },
      { page: '/me/products/new', drf: 'POST /api/v1/me/products/', note: '新增商品' },
      { page: '/me/products/[slug]', drf: 'GET/PUT /api/v1/me/products/:slug/', note: '商品編輯' },
      { page: '/me/sales', drf: 'GET /api/v1/me/sales/', note: '賣家訂單列表' },
      { page: '/me/sales/[id]', drf: 'GET /api/v1/me/sales/:id/', note: '賣家訂單詳情' },
      { page: '/me/sales/report', drf: 'GET /api/v1/me/sales/report/', note: '賣家報表' },
      { page: '/staff/dashboard', drf: 'GET /api/v1/staff/dashboard/', note: '管理儀表板' },
      { page: '/staff/orders', drf: 'GET /api/v1/staff/orders/', note: '管理端訂單列表' },
      { page: '/staff/orders/[id]', drf: 'GET /api/v1/staff/orders/:id/', note: '管理端訂單詳情' },
      { page: '/staff/orders/[id]', drf: 'POST /api/v1/staff/orders/:id/service-review/', note: '售後審核' },
      { page: '/staff/reviews', drf: 'GET /api/v1/staff/reviews/', note: '快速審核頁' },
      { page: '/staff/users', drf: 'GET /api/v1/staff/users/', note: '會員管理' },
      { page: '/staff/integrations/newebpay/logistics/store-map/debug/', drf: 'GET /api/v1/staff/integrations/newebpay/logistics/store-map/debug/', note: '超商選店 debug' },
    ],
  },
  {
    title: '共用基礎層',
    rows: [
      { page: 'Layout / Header', drf: 'GET /api/v1/app/bootstrap/', note: '全站 header 與計數初始化' },
      { page: 'Proxy Route', drf: 'frontend/app/api/backend/[...path]/route.ts', note: 'Next.js 代理 Django API，統一處理 cookie 與 CSRF' },
    ],
  },
]

/**
 * 文件頁本身不呼叫後端，只是把靜態對照資料渲染成表格。
 */
export default function RouteDocsPage() {
  return (
    <div className="stack">
      <section className="hero">
        <h1>Next.js 頁面與 Django DRF API 對照</h1>
        <p className="muted">這頁用來快速查看目前前端頁面會對應到哪些 DRF API，方便追資料流與除錯。</p>
      </section>

      {routeGroups.map((group) => (
        <section className="card stack" key={group.title}>
          <h2>{group.title}</h2>
          <table className="table">
            <thead>
              <tr>
                <th>前端頁面</th>
                <th>DRF API</th>
                <th>用途說明</th>
              </tr>
            </thead>
            <tbody>
              {group.rows.map((row) => (
                <tr key={`${group.title}-${row.page}-${row.drf}`}>
                  <td>{row.page}</td>
                  <td>{row.drf}</td>
                  <td>{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  )
}

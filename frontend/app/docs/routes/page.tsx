'use client'

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
    title: '商品與內容',
    rows: [
      { page: '/products', drf: 'GET /api/v1/products/', note: '商品列表與篩選。' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/', note: '商品詳情頁。' },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/reviews/',
        note: '商品評論列表與新增評論。',
      },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/questions/',
        note: '商品問答列表與提問。',
      },
      {
        page: '/products/[slug]',
        drf: 'GET /api/v1/products/:slug/price-compare/',
        note: '價格比較資料。',
      },
      {
        page: '/products/[slug]',
        drf: 'POST /api/v1/products/:slug/price-compare/refresh/',
        note: '重新整理價格比較。',
      },
      { page: '/products/compare', drf: 'GET /api/v1/products/compare/', note: '商品比較清單。' },
      { page: '/products/compare', drf: 'POST /api/v1/products/:slug/compare/', note: '加入或移除比較清單。' },
      { page: '/brands/[brand_slug]', drf: 'GET /api/v1/products/?brand=...', note: '品牌商品頁。' },
      {
        page: '/categories/[category_slug]',
        drf: 'GET /api/v1/products/?category=...',
        note: '分類商品頁。',
      },
      { page: '/community', drf: 'GET/POST /api/v1/community/posts/', note: '社群文章列表與發文。' },
      { page: '/community/[id]', drf: 'GET /api/v1/community/posts/:id/', note: '社群文章詳情。' },
    ],
  },
  {
    title: '會員與購物流程',
    rows: [
      { page: '/login', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/login/', note: '登入流程。' },
      { page: '/register', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/register/', note: '註冊流程。' },
      { page: '/me/dashboard', drf: 'GET /api/v1/me/dashboard/', note: '會員中心首頁資料。' },
      { page: '/me/profile', drf: 'GET/POST /api/v1/me/profile/', note: '會員資料讀取與更新。' },
      { page: '/me/addresses', drf: 'GET/POST /api/v1/me/addresses/', note: '地址管理。' },
      { page: '/me/invoice', drf: 'GET/POST /api/v1/me/invoice/', note: '發票設定。' },
      { page: '/orders', drf: 'GET /api/v1/me/orders/', note: '買家訂單列表。' },
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/', note: '買家訂單詳情。' },
      { page: '/cart', drf: 'GET /api/v1/cart/', note: '購物車內容。' },
      { page: '/cart', drf: 'POST /api/v1/cart/items/', note: '加入購物車。' },
      { page: '/checkout', drf: 'GET /api/v1/checkout/preview/', note: '結帳預覽。' },
      { page: '/checkout', drf: 'POST /api/v1/checkout/confirm/', note: '建立訂單。' },
      {
        page: '/checkout',
        drf: 'POST /api/v1/checkout/logistics/store-map/prepare/',
        note: '建立藍新超商地圖選店表單。',
      },
      {
        page: '/checkout',
        drf: 'GET /api/v1/checkout/logistics/store-selection/?token=...',
        note: '讀取超商取貨門市選擇結果。',
      },
    ],
  },
  {
    title: '藍新支付 Sandbox',
    rows: [
      {
        page: '/orders/[id]',
        drf: 'GET /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '讀取 sandbox 付款資訊。',
      },
      {
        page: '/orders/[id]',
        drf: 'POST /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '建立 sandbox 付款表單 payload。',
      },
      {
        page: 'Callback',
        drf: 'POST /api/v1/integrations/newebpay/payment/sandbox/callback/',
        note: '接收 sandbox callback 並更新付款紀錄。',
      },
    ],
  },
  {
    title: '賣家與後台',
    rows: [
      { page: '/me/products', drf: 'GET /api/v1/me/products/', note: '賣家商品列表。' },
      { page: '/me/products/new', drf: 'POST /api/v1/me/products/', note: '建立商品。' },
      { page: '/me/products/[slug]', drf: 'GET/PUT /api/v1/me/products/:slug/', note: '商品編輯。' },
      { page: '/me/sales', drf: 'GET /api/v1/me/sales/', note: '賣家訂單列表。' },
      { page: '/me/sales/[id]', drf: 'GET /api/v1/me/sales/:id/', note: '賣家訂單詳情。' },
      { page: '/me/sales/report', drf: 'GET /api/v1/me/sales/report/', note: '賣家報表。' },
      { page: '/staff/dashboard', drf: 'GET /api/v1/staff/dashboard/', note: '後台首頁資料。' },
      { page: '/staff/orders', drf: 'GET /api/v1/staff/orders/', note: '後台訂單列表。' },
      { page: '/staff/orders/[id]', drf: 'GET /api/v1/staff/orders/:id/', note: '後台訂單詳情。' },
      {
        page: '/staff/orders/[id]',
        drf: 'POST /api/v1/staff/orders/:id/service-review/',
        note: '客服審核或處理紀錄。',
      },
      { page: '/staff/reviews', drf: 'GET /api/v1/staff/reviews/', note: '後台評論管理。' },
      { page: '/staff/users', drf: 'GET /api/v1/staff/users/', note: '使用者管理。' },
      {
        page: '/staff/integrations/newebpay/logistics/store-map/debug/',
        drf: 'GET /api/v1/staff/integrations/newebpay/logistics/store-map/debug/',
        note: '檢查藍新超商地圖送出 payload。',
      },
    ],
  },
  {
    title: '共用基礎設施',
    rows: [
      {
        page: 'Layout / Header',
        drf: 'GET /api/v1/app/bootstrap/',
        note: '載入全站 header、登入狀態與購物車數量。',
      },
      {
        page: 'Proxy Route',
        drf: 'frontend/app/api/backend/[...path]/route.ts',
        note: 'Next.js 代理 Django DRF，統一處理 cookie 與 CSRF header。',
      },
    ],
  },
]

export default function RouteDocsPage() {
  return (
    <div className="stack">
      <section className="hero">
        <h1>Next.js 頁面與 Django DRF API 對照</h1>
        <p className="muted">
          這頁整理前端主要頁面會對應到哪些 DRF API，方便開發時快速確認資料流與目前仍在使用的整合端點。
        </p>
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

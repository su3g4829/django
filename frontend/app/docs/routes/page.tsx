'use client'

/**
 * Next.js 頁面與 Django DRF API 對照文件頁。
 *
 * 功能：
 * - 列出主要前端路由各自依賴的 DRF API
 * - 協助分辨 buyer / seller / staff 與整合測試頁的資料流
 * - 額外標示 Next.js proxy route 的用途
 */

const routeGroups = [
  {
    title: '商品與內容前台',
    rows: [
      { page: '/products', drf: 'GET /api/v1/products/', note: '商品列表、搜尋、篩選、排序。' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/', note: '商品詳情主資料。' },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/reviews/',
        note: '評論列表與新增評論。',
      },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/questions/',
        note: '問答列表與新增問題。',
      },
      {
        page: '/products/[slug]',
        drf: 'GET /api/v1/products/:slug/price-compare/',
        note: '競品價格比較資料。',
      },
      {
        page: '/products/[slug]',
        drf: 'POST /api/v1/products/:slug/price-compare/refresh/',
        note: '模擬重新抓取競品價格。',
      },
      { page: '/products/compare', drf: 'GET /api/v1/products/compare/', note: '商品比較清單。' },
      { page: '/products/compare', drf: 'POST /api/v1/products/:slug/compare/', note: '加入/移除比較。' },
      { page: '/brands/[brand_slug]', drf: 'GET /api/v1/products/?brand=...', note: '品牌頁商品列表。' },
      {
        page: '/categories/[category_slug]',
        drf: 'GET /api/v1/products/?category=...',
        note: '分類頁商品列表。',
      },
      { page: '/community', drf: 'GET/POST /api/v1/community/posts/', note: '論壇文章列表與發文。' },
      { page: '/community/[id]', drf: 'GET /api/v1/community/posts/:id/', note: '單篇論壇文章明細。' },
    ],
  },
  {
    title: '買家與會員中心',
    rows: [
      { page: '/login', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/login/', note: '登入流程。' },
      { page: '/register', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/register/', note: '註冊流程。' },
      { page: '/me/dashboard', drf: 'GET /api/v1/me/dashboard/', note: '會員中心摘要。' },
      { page: '/me/profile', drf: 'GET/POST /api/v1/me/profile/', note: '個人資料。' },
      { page: '/me/addresses', drf: 'GET/POST /api/v1/me/addresses/', note: '地址簿。' },
      { page: '/me/invoice', drf: 'GET/POST /api/v1/me/invoice/', note: '發票資料。' },
      { page: '/orders', drf: 'GET /api/v1/me/orders/', note: '買家訂單列表。' },
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/', note: '買家訂單明細。' },
      { page: '/cart', drf: 'GET /api/v1/cart/', note: '購物車資料。' },
      { page: '/cart', drf: 'POST /api/v1/cart/items/', note: '加入購物車。' },
      { page: '/checkout', drf: 'GET /api/v1/checkout/preview/', note: '結帳預覽。' },
      { page: '/checkout', drf: 'POST /api/v1/checkout/confirm/', note: '建立訂單。' },
    ],
  },
  {
    title: '藍新 Sandbox 測試頁',
    rows: [
      {
        page: '/orders/[id]',
        drf: 'GET /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '讀取藍新支付 sandbox 設定摘要。',
      },
      {
        page: '/orders/[id]',
        drf: 'POST /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '建立藍新支付 sandbox form payload。',
      },
      {
        page: '/me/sales/[id]',
        drf: 'GET /api/v1/me/sales/:id/newebpay-logistics/sandbox/',
        note: '讀取藍新物流 sandbox 設定摘要。',
      },
      {
        page: '/me/sales/[id]',
        drf: 'POST /api/v1/me/sales/:id/newebpay-logistics/sandbox/',
        note: '建立藍新物流 sandbox scaffold payload。',
      },
      {
        page: 'Callback',
        drf: 'POST /api/v1/integrations/newebpay/payment/sandbox/callback/',
        note: '藍新支付 sandbox callback 收件端點。',
      },
      {
        page: 'Callback',
        drf: 'POST /api/v1/integrations/newebpay/logistics/sandbox/callback/',
        note: '藍新物流 sandbox callback 收件端點。',
      },
    ],
  },
  {
    title: '賣家與管理後台',
    rows: [
      { page: '/me/products', drf: 'GET /api/v1/me/products/', note: '賣家商品列表。' },
      { page: '/me/products/new', drf: 'POST /api/v1/me/products/', note: '新增商品。' },
      { page: '/me/products/[slug]', drf: 'GET/PUT /api/v1/me/products/:slug/', note: '編輯商品。' },
      { page: '/me/sales', drf: 'GET /api/v1/me/sales/', note: '賣家訂單列表。' },
      { page: '/me/sales/[id]', drf: 'GET /api/v1/me/sales/:id/', note: '賣家訂單明細。' },
      { page: '/me/sales/report', drf: 'GET /api/v1/me/sales/report/', note: '賣家銷售報表。' },
      { page: '/staff/dashboard', drf: 'GET /api/v1/staff/dashboard/', note: '管理後台摘要。' },
      { page: '/staff/orders', drf: 'GET /api/v1/staff/orders/', note: '管理者訂單列表。' },
      { page: '/staff/orders/[id]', drf: 'GET /api/v1/staff/orders/:id/', note: '管理者訂單明細。' },
      {
        page: '/staff/orders/[id]',
        drf: 'POST /api/v1/staff/orders/:id/service-review/',
        note: '售後申請審核。',
      },
      { page: '/staff/reviews', drf: 'GET /api/v1/staff/reviews/', note: '賣家申請與商品審核列表。' },
      { page: '/staff/users', drf: 'GET /api/v1/staff/users/', note: '會員列表。' },
    ],
  },
  {
    title: '基礎設施',
    rows: [
      { page: 'Layout / Header', drf: 'GET /api/v1/app/bootstrap/', note: '全站登入態、購物車、比較清單摘要。' },
      {
        page: 'Proxy Route',
        drf: 'frontend/app/api/backend/[...path]/route.ts',
        note: 'Next.js 代理 Django DRF，轉送 cookie 與 CSRF header。',
      },
    ],
  },
]

export default function RouteDocsPage() {
  return (
    <div className="stack">
      <section className="hero">
        <h1>Next.js 前端路由與 API 對照</h1>
        <p className="muted">
          這份文件整理目前主要前端頁面對應的 Django DRF canonical API，方便檢查資料流與測試責任分界。
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

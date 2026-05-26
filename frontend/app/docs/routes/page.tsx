/**
 * Next.js 頁面與 Django DRF API 對照文件頁。
 *
 * 這頁的用途是讓開發者快速辨識：
 * - 哪個前端頁面對應哪支 DRF API
 * - 某支 API 是讀取、寫入，或只是前端 proxy
 * - 前後端分離後，資料流實際如何串接
 */

const routeGroups = [
  {
    title: '商品與社群',
    rows: [
      { page: '/products', drf: 'GET /api/v1/products/', note: '商品列表、篩選、排序、分頁' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/', note: '商品詳情' },
      { page: '/products/[slug]', drf: 'GET/POST /api/v1/products/:slug/reviews/', note: '評論列表與新增評論' },
      { page: '/products/[slug]', drf: 'GET/POST /api/v1/products/:slug/questions/', note: '商品問答列表與發問' },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/price-compare/', note: '模擬外站比價資料' },
      { page: '/products/[slug]', drf: 'POST /api/v1/products/:slug/price-compare/refresh/', note: '模擬重新抓價' },
      { page: '/products/compare', drf: 'GET /api/v1/products/compare/', note: '商品比較清單' },
      { page: '/products/compare', drf: 'POST /api/v1/products/:slug/compare/', note: '加入 / 移除比較清單' },
      { page: '/brands/[brand_slug]', drf: 'GET /api/v1/products/?brand=...', note: '品牌商品列表' },
      { page: '/categories/[category_slug]', drf: 'GET /api/v1/products/?category=...', note: '分類商品列表' },
      { page: '/community', drf: 'GET/POST /api/v1/community/posts/', note: '社群文章列表與發文' },
      { page: '/community/[id]', drf: 'GET /api/v1/community/posts/:id/', note: '社群文章詳情' },
    ],
  },
  {
    title: '會員與購物流程',
    rows: [
      { page: '/login', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/login/', note: '登入' },
      { page: '/register', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/register/', note: '註冊' },
      { page: '/me/profile', drf: 'GET/POST /api/v1/me/profile/', note: '會員資料' },
      { page: '/me/addresses', drf: 'GET/POST /api/v1/me/addresses/', note: '地址簿' },
      { page: '/me/invoice', drf: 'GET/POST /api/v1/me/invoice/', note: '發票資料' },
      { page: '/orders', drf: 'GET /api/v1/me/orders/', note: '買家訂單列表' },
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/', note: '買家訂單詳情' },
      { page: '/cart', drf: 'GET /api/v1/cart/', note: '購物車內容' },
      { page: '/cart', drf: 'POST /api/v1/cart/items/', note: '加入購物車' },
      { page: '/checkout', drf: 'GET /api/v1/checkout/preview/', note: '結帳預覽' },
      { page: '/checkout', drf: 'POST /api/v1/checkout/confirm/', note: '建立訂單' },
    ],
  },
  {
    title: '賣家與管理後台',
    rows: [
      { page: '/me/products', drf: 'GET /api/v1/me/products/', note: '賣家商品列表' },
      { page: '/me/products/new', drf: 'POST /api/v1/me/products/', note: '新增商品' },
      { page: '/me/products/[slug]', drf: 'GET/PUT /api/v1/me/products/:slug/', note: '編輯商品' },
      { page: '/me/sales', drf: 'GET /api/v1/me/sales/', note: '賣家訂單列表' },
      { page: '/me/sales/[id]', drf: 'GET /api/v1/me/sales/:id/', note: '賣家訂單詳情' },
      { page: '/me/sales/report', drf: 'GET /api/v1/me/sales/report/', note: '賣家報表' },
      { page: '/staff/dashboard', drf: 'GET /api/v1/staff/dashboard/', note: '管理後台儀表板' },
      { page: '/staff/orders', drf: 'GET /api/v1/staff/orders/', note: '管理端訂單列表' },
      { page: '/staff/orders/[id]', drf: 'GET /api/v1/staff/orders/:id/', note: '管理端訂單詳情' },
      { page: '/staff/orders/[id]', drf: 'POST /api/v1/staff/orders/:id/service-review/', note: '售後申請審核' },
      { page: '/staff/reviews', drf: 'GET /api/v1/staff/reviews/', note: '賣家申請 / 商品審核台' },
      { page: '/staff/users', drf: 'GET /api/v1/staff/users/', note: '會員列表' },
    ],
  },
  {
    title: '共用前端基礎設施',
    rows: [
      { page: 'Layout / Header', drf: 'GET /api/v1/app/bootstrap/', note: '抓目前登入者與全站數量徽章' },
      { page: 'Proxy Route', drf: 'frontend/app/api/backend/[...path]/route.ts', note: 'Next.js 代理到 Django DRF，處理 cookie 與 CSRF' },
    ],
  },
]

export default function RouteDocsPage() {
  return (
    <div className="stack">
      <section className="hero">
        <h1>Next.js 頁面與 API 對照</h1>
        <p className="muted">
          這份文件列出目前主要 Next.js 頁面，實際會使用到哪些 Django DRF canonical API。
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
                <th>用途</th>
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

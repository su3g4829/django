'use client'

/**
 * Next.js ???Django DRF API 撠?辣?? *
 * ?嚗? * - ?銝餉??垢頝舐?靘陷??DRF API
 * - ??儘 buyer / seller / staff ??葫閰阡?????
 * - 憿?璅內 Next.js proxy route ??? */

const routeGroups = [
  {
    title: '???摰孵???,
    rows: [
      { page: '/products', drf: 'GET /api/v1/products/', note: '???”??撠祟?詻?摨? },
      { page: '/products/[slug]', drf: 'GET /api/v1/products/:slug/', note: '??閰單?銝餉??? },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/reviews/',
        note: '閰??”?憓?隢?,
      },
      {
        page: '/products/[slug]',
        drf: 'GET/POST /api/v1/products/:slug/questions/',
        note: '???”?憓?憿?,
      },
      {
        page: '/products/[slug]',
        drf: 'GET /api/v1/products/:slug/price-compare/',
        note: '蝡嗅??寞瘥?鞈???,
      },
      {
        page: '/products/[slug]',
        drf: 'POST /api/v1/products/:slug/price-compare/refresh/',
        note: '璅⊥???蝡嗅??寞??,
      },
      { page: '/products/compare', drf: 'GET /api/v1/products/compare/', note: '??瘥?皜?? },
      { page: '/products/compare', drf: 'POST /api/v1/products/:slug/compare/', note: '?/蝘駁瘥??? },
      { page: '/brands/[brand_slug]', drf: 'GET /api/v1/products/?brand=...', note: '??????銵具? },
      {
        page: '/categories/[category_slug]',
        drf: 'GET /api/v1/products/?category=...',
        note: '??????銵具?,
      },
      { page: '/community', drf: 'GET/POST /api/v1/community/posts/', note: '隢????”??? },
      { page: '/community/[id]', drf: 'GET /api/v1/community/posts/:id/', note: '?桃?隢????敦?? },
    ],
  },
  {
    title: '鞎瑕振???∩葉敹?,
    rows: [
      { page: '/login', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/login/', note: '?餃瘚??? },
      { page: '/register', drf: 'GET /api/v1/auth/csrf/ + POST /api/v1/auth/register/', note: '閮餃?瘚??? },
      { page: '/me/dashboard', drf: 'GET /api/v1/me/dashboard/', note: '?銝剖????? },
      { page: '/me/profile', drf: 'GET/POST /api/v1/me/profile/', note: '?犖鞈??? },
      { page: '/me/addresses', drf: 'GET/POST /api/v1/me/addresses/', note: '?啣?蝪踴? },
      { page: '/me/invoice', drf: 'GET/POST /api/v1/me/invoice/', note: '?潛巨鞈??? },
      { page: '/orders', drf: 'GET /api/v1/me/orders/', note: '鞎瑕振閮?”?? },
      { page: '/orders/[id]', drf: 'GET /api/v1/me/orders/:id/', note: '鞎瑕振閮?敦?? },
      { page: '/cart', drf: 'GET /api/v1/cart/', note: '鞈潛頠??? },
      { page: '/cart', drf: 'POST /api/v1/cart/items/', note: '?鞈潛頠? },
      { page: '/checkout', drf: 'GET /api/v1/checkout/preview/', note: '蝯董?汗?? },
      { page: '/checkout', drf: 'POST /api/v1/checkout/confirm/', note: '撱箇?閮?? },
    ],
  },
  {
    title: '? Sandbox 皜祈岫??,
    rows: [
      {
        page: '/orders/[id]',
        drf: 'GET /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '霈???唳隞?sandbox 閮剖?????,
      },
      {
        page: '/orders/[id]',
        drf: 'POST /api/v1/me/orders/:id/newebpay-payment/sandbox/',
        note: '撱箇???臭? sandbox form payload??,
      },
      {
        page: 'Callback',
        drf: 'POST /api/v1/integrations/newebpay/payment/sandbox/callback/',
        note: '??臭? sandbox callback ?嗡辣蝡舫???,
      },
    ],
  },
  {
    title: '鞈?振?恣????,
    rows: [
      { page: '/me/products', drf: 'GET /api/v1/me/products/', note: '鞈?振???”?? },
      { page: '/me/products/new', drf: 'POST /api/v1/me/products/', note: '?啣????? },
      { page: '/me/products/[slug]', drf: 'GET/PUT /api/v1/me/products/:slug/', note: '蝺刻摩???? },
      { page: '/me/sales', drf: 'GET /api/v1/me/sales/', note: '鞈?振閮?”?? },
      { page: '/me/sales/[id]', drf: 'GET /api/v1/me/sales/:id/', note: '鞈?振閮?敦?? },
      { page: '/me/sales/report', drf: 'GET /api/v1/me/sales/report/', note: '鞈?振?瑕?梯”?? },
      { page: '/staff/dashboard', drf: 'GET /api/v1/staff/dashboard/', note: '蝞∠?敺???? },
      { page: '/staff/orders', drf: 'GET /api/v1/staff/orders/', note: '蝞∠????桀?銵具? },
      { page: '/staff/orders/[id]', drf: 'GET /api/v1/staff/orders/:id/', note: '蝞∠????格?蝝啜? },
      {
        page: '/staff/orders/[id]',
        drf: 'POST /api/v1/staff/orders/:id/service-review/',
        note: '?桀??唾?撖拇??,
      },
      { page: '/staff/reviews', drf: 'GET /api/v1/staff/reviews/', note: '鞈?振?唾????祟?詨?銵具? },
      { page: '/staff/users', drf: 'GET /api/v1/staff/users/', note: '??”?? },
    ],
  },
  {
    title: '?箇?閮剜',
    rows: [
      { page: 'Layout / Header', drf: 'GET /api/v1/app/bootstrap/', note: '?函??餃?頃?抵???頛??格?閬? },
      {
        page: 'Proxy Route',
        drf: 'frontend/app/api/backend/[...path]/route.ts',
        note: 'Next.js 隞?? Django DRF嚗???cookie ??CSRF header??,
      },
    ],
  },
]

export default function RouteDocsPage() {
  return (
    <div className="stack">
      <section className="hero">
        <h1>Next.js ?垢頝舐??API 撠</h1>
        <p className="muted">
          ?遢?辣?渡??桀?銝餉??垢?撠???Django DRF canonical API嚗靘踵炎?亥????葫閰西痊隞餃???        </p>
      </section>

      {routeGroups.map((group) => (
        <section className="card stack" key={group.title}>
          <h2>{group.title}</h2>
          <table className="table">
            <thead>
              <tr>
                <th>?垢?</th>
                <th>DRF API</th>
                <th>?券牧??/th>
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

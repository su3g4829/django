# FRONTEND_API_SERVICE_MAP

本文件用來對照：

1. 前端頁面在哪裡
2. 該頁面控制網站哪一塊
3. 會呼叫哪些 Django DRF API
4. 後端主要落到哪些 service
5. 最後讀寫哪類 JSON 資料

---

## 1. 全站共用層

### `frontend/app/layout.tsx`
- 控制：
  - 全站共用 layout
  - header / 導覽 / 全站樣式外框
- 主要搭配元件：
  - `frontend/components/site-header.tsx`

### `frontend/components/site-header.tsx`
- 控制：
  - 頁首導覽
  - 目前登入者
  - 購物車數量
  - 比較清單數量
  - 登出
- API：
  - `GET /api/v1/app/bootstrap/`
  - `POST /api/v1/auth/logout/`
- 後端 service：
  - `auth_demo.py`
  - `cart.py`
  - `personalization.py`
- 資料來源：
  - `data/users.json`
  - `data/orders.json` / 購物車相關 JSON

### `frontend/app/api/backend/[...path]/route.ts`
- 控制：
  - Next.js 前端代理層
  - 將 `/api/backend/...` 轉發到 Django `/api/v1/...`
- 不直接控制商業功能
- 主要負責：
  - cookie 轉送
  - CSRF token
  - error normalization

---

## 2. 商品瀏覽與內容頁

### `frontend/app/page.tsx`
- 控制：
  - 首頁
  - 精選商品總覽入口
- 主要元件：
  - `frontend/components/catalog-browser.tsx`
- API：
  - `GET /api/v1/products/`
- 後端 service：
  - `recommendations.py`
  - 商品查詢相關 service / repository
- 資料來源：
  - `data/products.json`

### `frontend/app/products/page.tsx`
- 控制：
  - 商品總覽
- API：
  - `GET /api/v1/products/`
- 後端 service：
  - 商品列表查詢 service
- 資料來源：
  - `data/products.json`

### `frontend/app/brands/[brand_slug]/page.tsx`
- 控制：
  - 品牌商品頁
- API：
  - `GET /api/v1/products/?brand=...`
- 後端 service：
  - 商品列表查詢 service
- 資料來源：
  - `data/products.json`

### `frontend/app/categories/[category_slug]/page.tsx`
- 控制：
  - 分類商品頁
- API：
  - `GET /api/v1/products/?category=...`
- 後端 service：
  - 商品列表查詢 service
- 資料來源：
  - `data/products.json`

### `frontend/app/products/[slug]/page.tsx`
- 控制：
  - 商品詳情
  - 加入購物車
  - 收藏
  - 商品比較
  - 評論
  - 問答
  - 外站比價
- API：
  - `GET /api/v1/products/:slug/`
  - `POST /api/v1/cart/items/`
  - `POST /api/v1/products/:slug/favorite/`
  - `POST /api/v1/products/:slug/compare/`
  - `GET/POST /api/v1/products/:slug/reviews/`
  - `GET/POST /api/v1/products/:slug/questions/`
  - `POST /api/v1/products/:slug/questions/:questionId/answers/`
  - `GET /api/v1/products/:slug/recommendations/`
  - `GET /api/v1/products/:slug/price-compare/`
  - `POST /api/v1/products/:slug/price-compare/refresh/`
- 後端 service：
  - `cart.py`
  - `reviews.py`
  - `questions.py`
  - `recommendations.py`
  - `personalization.py`
  - `price_compare.py`
- 資料來源：
  - `data/products.json`
  - `data/reviews.json`
  - `data/questions.json`
  - `data/competitor_prices.json`

### `frontend/app/products/compare/page.tsx`
- 控制：
  - 商品比較頁
- API：
  - `GET /api/v1/products/compare/`
  - `POST /api/v1/products/:slug/compare/`
- 後端 service：
  - `personalization.py`
- 資料來源：
  - 比較清單相關 JSON / session 資料

### `frontend/app/community/page.tsx`
- 控制：
  - 社群文章列表
  - 發文
- API：
  - `GET /api/v1/community/posts/`
  - `POST /api/v1/community/posts/`
- 後端 service：
  - `community.py`
- 資料來源：
  - `data/community_posts.json`

### `frontend/app/community/[id]/page.tsx`
- 控制：
  - 單篇社群文章
  - 回覆
  - 投票
- API：
  - `GET /api/v1/community/posts/:id/`
  - `POST /api/v1/community/posts/:id/replies/`
  - `POST /api/v1/community/posts/:id/vote/`
- 後端 service：
  - `community.py`
- 資料來源：
  - `data/community_posts.json`

---

## 3. 認證與會員中心

### `frontend/app/login/page.tsx`
- 控制：
  - 登入頁
- API：
  - `GET /api/v1/auth/csrf/`
  - `POST /api/v1/auth/login/`
- 後端 service：
  - `auth_demo.py`
- 資料來源：
  - `data/users.json`

### `frontend/app/register/page.tsx`
- 控制：
  - 註冊頁
- API：
  - `GET /api/v1/auth/csrf/`
  - `POST /api/v1/auth/register/`
- 後端 service：
  - `auth_demo.py`
- 資料來源：
  - `data/users.json`

### `frontend/app/me/dashboard/page.tsx`
- 控制：
  - 會員 dashboard
  - 訂單 / 收藏 / 比較 / 基本摘要
- API：
  - `GET /api/v1/me/dashboard/`
- 後端 service：
  - `customer_center.py`
  - `personalization.py`
  - `orders.py`
- 資料來源：
  - `data/users.json`
  - `data/orders.json`

### `frontend/app/me/profile/page.tsx`
- 控制：
  - 個人資料編輯
- API：
  - `GET /api/v1/me/profile/`
  - `POST /api/v1/me/profile/`
- 後端 service：
  - `profile.py`
- 資料來源：
  - `data/users.json`

### `frontend/app/me/addresses/page.tsx`
- 控制：
  - 地址管理
- API：
  - `GET /api/v1/me/addresses/`
  - `POST /api/v1/me/addresses/`
  - `POST /api/v1/me/addresses/:id/default/`
  - `DELETE /api/v1/me/addresses/:id/`
- 後端 service：
  - `profile.py`
  - `customer_center.py`
- 資料來源：
  - `data/users.json`

### `frontend/app/me/invoice/page.tsx`
- 控制：
  - 發票設定
- API：
  - `GET /api/v1/me/invoice/`
  - `POST /api/v1/me/invoice/`
- 後端 service：
  - `profile.py`
  - `customer_center.py`
- 資料來源：
  - `data/users.json`

---

## 4. 購物車、checkout、買家訂單

### `frontend/app/cart/page.tsx`
- 控制：
  - 購物車內容
  - 改數量
  - 刪除項目
  - 套折扣碼
- API：
  - `GET /api/v1/cart/`
  - `PATCH /api/v1/cart/items/:itemKey/`
  - `DELETE /api/v1/cart/items/:itemKey/`
  - `POST /api/v1/cart/`
- 後端 service：
  - `cart.py`
- 資料來源：
  - 購物車 JSON / session 資料

### `frontend/app/checkout/page.tsx`
- 控制：
  - 結帳確認頁
  - 商品明細
  - 地址選擇
  - 配送方式
  - 付款方式
  - 發票摘要
  - 買家備註
  - 建立訂單
- API：
  - `GET /api/v1/checkout/preview/`
  - `POST /api/v1/checkout/confirm/`
  - 同時依流程讀：
    - `GET /api/v1/me/addresses/`
    - `GET /api/v1/me/invoice/`
- 後端 service：
  - `cart.py`
  - `customer_center.py`
  - `orders.py`
- 資料來源：
  - 購物車資料
  - `data/users.json`
  - `data/orders.json`

### `frontend/app/orders/page.tsx`
- 控制：
  - 買家訂單列表
- API：
  - `GET /api/v1/me/orders/`
- 後端 service：
  - `orders.py`
- 資料來源：
  - `data/orders.json`

### `frontend/app/orders/[id]/page.tsx`
- 控制：
  - 買家訂單詳情
  - 取消 / 退款申請
  - 藍新支付 sandbox 測試
  - 顯示支付測試紀錄
- API：
  - `GET /api/v1/me/orders/:id/`
  - `POST /api/v1/me/orders/:id/cancel-request/`
  - `POST /api/v1/me/orders/:id/refund-request/`
  - `GET /api/v1/me/orders/:id/newebpay-payment/`
  - `GET /api/v1/me/orders/:id/newebpay-payment/sandbox/`
  - `POST /api/v1/me/orders/:id/newebpay-payment/sandbox/`
- 後端 service：
  - `orders.py`
  - `newebpay_payment.py`
  - `newebpay_payment_real.py`
- 資料來源：
  - `data/orders.json`
  - `data/newebpay_payment_logs.json`

---

## 5. 賣家頁面

### `frontend/app/me/products/page.tsx`
- 控制：
  - 賣家商品列表
  - 封存 / 複製 / 刪除商品
- API：
  - `GET /api/v1/me/products/`
  - `POST /api/v1/me/products/:slug/archive/`
  - `POST /api/v1/me/products/:slug/duplicate/`
  - `DELETE /api/v1/me/products/:slug/`
- 後端 service：
  - `product_management.py`
- 資料來源：
  - `data/products.json`

### `frontend/app/me/products/new/page.tsx`
- 控制：
  - 新增商品
- API：
  - `POST /api/v1/me/products/`
- 後端 service：
  - `product_management.py`
- 資料來源：
  - `data/products.json`

### `frontend/app/me/products/[slug]/page.tsx`
- 控制：
  - 編輯商品
- API：
  - `GET /api/v1/me/products/:slug/`
  - `PUT /api/v1/me/products/:slug/`
- 後端 service：
  - `product_management.py`
- 資料來源：
  - `data/products.json`

### `frontend/app/me/sales/page.tsx`
- 控制：
  - 賣家訂單列表
- API：
  - `GET /api/v1/me/sales/`
- 後端 service：
  - `orders.py`
- 資料來源：
  - `data/orders.json`

### `frontend/app/me/sales/[id]/page.tsx`
- 控制：
  - 賣家訂單詳情
  - 出貨資訊
  - 藍新物流 sandbox 測試
  - 顯示物流測試紀錄
- API：
  - `GET /api/v1/me/sales/:id/`
  - `POST /api/v1/me/sales/:id/update/`
  - `GET /api/v1/me/sales/:id/newebpay-logistics/`
  - `GET /api/v1/me/sales/:id/newebpay-logistics/sandbox/`
  - `POST /api/v1/me/sales/:id/newebpay-logistics/sandbox/`
- 後端 service：
  - `orders.py`
  - `newebpay_logistics.py`
  - `newebpay_logistics_real.py`
- 資料來源：
  - `data/orders.json`
  - `data/newebpay_logistics_logs.json`

### `frontend/app/me/sales/report/page.tsx`
- 控制：
  - 賣家銷售報表
- API：
  - `GET /api/v1/me/sales/report/`
- 後端 service：
  - `orders.py`
  - `admin_portal.py`
- 資料來源：
  - `data/orders.json`

---

## 6. 管理端頁面

### `frontend/app/staff/dashboard/page.tsx`
- 控制：
  - 管理端摘要面板
- API：
  - `GET /api/v1/staff/dashboard/`
- 後端 service：
  - `admin_portal.py`
- 資料來源：
  - `data/orders.json`
  - `data/users.json`
  - 商品/評論/論壇資料

### `frontend/app/staff/orders/page.tsx`
- 控制：
  - 管理者訂單列表
- API：
  - `GET /api/v1/staff/orders/`
- 後端 service：
  - `admin_portal.py`
  - `orders.py`
- 資料來源：
  - `data/orders.json`

### `frontend/app/staff/orders/[id]/page.tsx`
- 控制：
  - 管理者訂單詳情
  - 售後申請審核
- API：
  - `GET /api/v1/staff/orders/:id/`
  - `POST /api/v1/staff/orders/:id/service-review/`
- 後端 service：
  - `admin_portal.py`
  - `orders.py`
- 資料來源：
  - `data/orders.json`

### `frontend/app/staff/reviews/page.tsx`
- 控制：
  - 商品上架管理 / 強制下架
  - 賣家申請審核
- API：
  - `GET /api/v1/staff/reviews/`
  - `POST /api/v1/staff/products/:slug/archive/`
  - `POST /api/v1/staff/seller-requests/:username/review/`
- 後端 service：
  - `admin_portal.py`
  - `auth_demo.py`
  - `product_management.py`
- 資料來源：
  - `data/products.json`
  - `data/users.json`

### `frontend/app/staff/users/page.tsx`
- 控制：
  - 會員列表
  - 會員狀態調整
- API：
  - `GET /api/v1/staff/users/`
  - `POST /api/v1/staff/users/:username/status/`
- 後端 service：
  - `admin_portal.py`
- 資料來源：
  - `data/users.json`

---

## 7. 文件與對照頁

### `frontend/app/docs/routes/page.tsx`
- 控制：
  - 前端可讀 API / 路由文件頁
- 用途：
  - 對照前端頁面與 DRF API

---

## 8. 本機測站建議順序

建議你後續在 VS Code / 本機瀏覽器這樣測：

1. 註冊會員
2. 登入
3. 建地址
4. 建發票資訊
5. 建商品
6. 瀏覽商品列表 / 商品頁
7. 加入購物車
8. 驗證 header cart badge 是否同步
9. 走 checkout
10. 建立訂單
11. 看買家訂單頁
12. 看賣家訂單頁
13. 最後再回 Render 測藍新支付 / 物流 sandbox

---

## 9. 目前仍屬 Scaffold / 測試中的區塊

以下功能已可測，但仍不是完整正式商用版：

- 藍新支付：
  - 已有 sandbox payload / callback / return 流程
  - 仍偏測試架構
- 藍新物流：
  - 已有 seller-side sandbox scaffold
  - checkout 的超商選店仍是手動欄位 scaffold
- 資料層：
  - 仍是 `data/*.json`
  - 非正式資料庫

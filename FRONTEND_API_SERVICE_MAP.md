# FRONTEND_API_SERVICE_MAP

本文件用來對照：

1. 前端頁面在哪裡
2. 該頁面控制哪一段功能
3. 呼叫哪些 API
4. 後端落到哪些 service
5. 目前資料最後存到哪裡

## 1. 共用層

### `frontend/app/layout.tsx`

- 負責全站 layout
- 載入 header 與全站樣式

### `frontend/components/site-header.tsx`

- 顯示登入者、購物車數量、收藏數量、比較數量
- 提供登出

API：

- `GET /api/v1/app/bootstrap/`
- `POST /api/v1/auth/logout/`

後端：

- `myapp/services/auth_demo.py`
- `myapp/services/cart.py`
- `myapp/services/personalization.py`

資料來源：

- session
- `data/users.json`

### `frontend/app/api/backend/[...path]/route.ts`

- Next.js API proxy
- 將 `/api/backend/*` 轉到 Django `/api/v1/*`

### `frontend/app/backend-assets/[...path]/route.ts`

- 靜態資產 proxy
- 主要給前端安全讀取後端資產路徑

## 2. 公開商品與內容頁

| 頁面 | 作用 | API | 後端 service | 目前資料來源 |
| --- | --- | --- | --- | --- |
| `frontend/app/page.tsx` | 首頁、商品瀏覽入口 | `GET /products/`, `GET /banners/` | `product_management.py`, `recommendations.py`, `admin_portal.py` | `products.json`, `banners.json` |
| `frontend/app/products/page.tsx` | 商品總覽 | `GET /products/` | `product_management.py` | `products.json` |
| `frontend/app/brands/[brand_slug]/page.tsx` | 品牌商品頁 | `GET /products/?brand=...` | `product_management.py` | `products.json` |
| `frontend/app/categories/[category_slug]/page.tsx` | 分類商品頁 | `GET /products/?category=...` | `product_management.py` | `products.json` |
| `frontend/app/products/[slug]/page.tsx` | 商品詳情、收藏、比較、評論、問答、比價、加入購物車 | `GET /products/:slug/`, `POST /cart/items/`, `POST /products/:slug/favorite/`, `POST /products/:slug/compare/`, `GET/POST /products/:slug/reviews/`, `GET/POST /products/:slug/questions/`, `POST /products/:slug/questions/:questionId/answers/`, `GET /products/:slug/recommendations/`, `GET /products/:slug/price-compare/`, `POST /products/:slug/price-compare/refresh/` | `product_management.py`, `cart.py`, `personalization.py`, `reviews.py`, `questions.py`, `recommendations.py`, `price_compare.py` | `products.json`, `reviews.json`, `questions.json`, `recommendations.json`, `competitor_prices.json`, session |
| `frontend/app/products/compare/page.tsx` | 商品比較 | `GET /products/compare/`, `POST /products/:slug/compare/` | `personalization.py`, `product_management.py` | session, `products.json` |
| `frontend/app/community/page.tsx` | 社群列表與發文 | `GET /community/posts/`, `POST /community/posts/` | `community.py` | `posts.json` |
| `frontend/app/community/[id]/page.tsx` | 貼文詳情、回覆、投票、編輯、刪除 | `GET /community/posts/:id/`, `POST /community/posts/:id/replies/`, `POST /community/posts/:id/vote/`, `PATCH /community/posts/:id/`, `DELETE /community/posts/:id/` | `community.py` | `posts.json` |
| `frontend/app/docs/routes/page.tsx` | 前端可讀路由 / API 文件頁 | 無直接業務 API | `myapp/api/route_registry.py` 資料供應 | repo 文件資料 |

## 3. 認證與會員中心

| 頁面 | 作用 | API | 後端 service | 目前資料來源 |
| --- | --- | --- | --- | --- |
| `frontend/app/login/page.tsx` | 登入 | `GET /auth/csrf/`, `POST /auth/login/` | `auth_demo.py` | `users.json`, session |
| `frontend/app/register/page.tsx` | 註冊 | `GET /auth/csrf/`, `POST /auth/register/` | `auth_demo.py` | `users.json` |
| `frontend/app/me/page.tsx` | 會員中心入口 | `GET /me/` | `auth_demo.py` | session |
| `frontend/app/me/dashboard/page.tsx` | 個人 dashboard | `GET /me/dashboard/` | `profile.py`, `orders.py`, `personalization.py` | `users.json`, `orders.json`, `products.json`, session |
| `frontend/app/me/profile/page.tsx` | 個人資料、賣家申請 | `GET /me/profile/`, `POST /me/profile/`, `POST /me/seller-request/` | `profile.py`, `auth_demo.py` | `users.json` |
| `frontend/app/me/addresses/page.tsx` | 地址管理 | `GET /me/addresses/`, `POST /me/addresses/`, `POST /me/addresses/:id/default/`, `DELETE /me/addresses/:id/` | `customer_center.py`, `profile.py` | `users.json` |
| `frontend/app/me/invoice/page.tsx` | 發票設定 | `GET /me/invoice/`, `POST /me/invoice/` | `customer_center.py`, `profile.py` | `users.json` |
| `frontend/app/me/shipping-rules/page.tsx` | 賣家運費規則 | `GET /me/shipping-rules/`, `POST /me/shipping-rules/` | `auth_demo.py` | `users.json` |
| `frontend/app/me/promotions/page.tsx` | banner 申請 | `GET /me/banner-applications/`, `POST /me/banner-applications/` | `admin_portal.py` | `banners.json` |

## 4. 購物車、checkout、買家訂單

| 頁面 | 作用 | API | 後端 service | 目前資料來源 |
| --- | --- | --- | --- | --- |
| `frontend/app/cart/page.tsx` | 購物車內容、數量調整、刪除、折扣碼 | `GET /cart/`, `PATCH /cart/items/:itemKey/`, `DELETE /cart/items/:itemKey/`, `POST /cart/` | `cart.py`, `orders.py` | session, `products.json` |
| `frontend/app/checkout/page.tsx` | 結帳預覽、選地址、選配送、建單 | `GET /checkout/preview/`, `POST /checkout/confirm/`, `GET /me/addresses/`, `GET /me/invoice/` | `orders.py`, `customer_center.py`, `cart.py` | session, `users.json`, `orders.json` |
| `frontend/app/orders/page.tsx` | 買家訂單列表 | `GET /me/orders/` | `orders.py` | `orders.json` |
| `frontend/app/orders/[id]/page.tsx` | 買家訂單詳情、付款資訊、完成訂單、正式付款入口 | `GET /me/orders/:id/`, `GET /me/orders/:id/newebpay-payment/`, `POST /me/orders/:id/newebpay-payment/sandbox/`, `POST /me/orders/:id/complete/`, `POST /me/orders/:id/cancel-request/`, `POST /me/orders/:id/refund-request/` | `orders.py`, `newebpay_payment_real.py` | `orders.json`, `newebpay_payment_logs.json` |

補充：

- 買家訂單頁現在不再保留一般使用者可操作的 debug 表單
- 正式付款入口仍會建立藍新 sandbox payload

## 5. 賣家頁

| 頁面 | 作用 | API | 後端 service | 目前資料來源 |
| --- | --- | --- | --- | --- |
| `frontend/app/me/products/page.tsx` | 賣家商品列表、封存、複製、刪除 | `GET /me/products/`, `POST /me/products/:slug/archive/`, `POST /me/products/:slug/duplicate/`, `DELETE /me/products/:slug/` | `product_management.py` | `products.json` |
| `frontend/app/me/products/new/page.tsx` | 新增商品 | `POST /me/products/` | `product_management.py` | `products.json` |
| `frontend/app/me/products/[slug]/page.tsx` | 編輯商品 | `GET /me/products/:slug/`, `PUT /me/products/:slug/` | `product_management.py` | `products.json` |
| `frontend/app/me/sales/page.tsx` | 賣家訂單列表 | `GET /me/sales/` | `orders.py` | `orders.json` |
| `frontend/app/me/sales/[id]/page.tsx` | 賣家訂單詳情、出貨狀態更新 | `GET /me/sales/:id/`, `POST /me/sales/:id/update/` | `orders.py` | `orders.json` |
| `frontend/app/me/sales/report/page.tsx` | 銷售報表 | `GET /me/sales/report/` | `orders.py`, `admin_portal.py` | `orders.json` |

補充：

- 賣家訂單頁現在顯示的是訂單快照與出貨狀態，不再保留舊 seller logistics sandbox 面板

## 6. staff / admin 頁

| 頁面 | 作用 | API | 後端 service | 目前資料來源 |
| --- | --- | --- | --- | --- |
| `frontend/app/staff/dashboard/page.tsx` | 管理摘要 | `GET /staff/dashboard/` | `admin_portal.py` | `users.json`, `products.json`, `orders.json`, `reviews.json`, `questions.json`, `posts.json` |
| `frontend/app/staff/orders/page.tsx` | 管理端訂單列表 | `GET /staff/orders/` | `admin_portal.py`, `orders.py` | `orders.json` |
| `frontend/app/staff/orders/[id]/page.tsx` | 管理端訂單詳情、售後審核、payment debug | `GET /staff/orders/:id/`, `GET /staff/orders/:id/payment-debug/`, `POST /staff/orders/:id/service-review/` | `admin_portal.py`, `orders.py`, `newebpay_payment_real.py` | `orders.json`, `newebpay_payment_logs.json` |
| `frontend/app/staff/products/page.tsx` | 商品審核、上架、封存、刪除 | `GET /staff/products/`, `POST /staff/products/:slug/publish/`, `POST /staff/products/:slug/archive/`, `DELETE /staff/products/:slug/` | `admin_portal.py`, `product_management.py` | `products.json` |
| `frontend/app/staff/reviews/page.tsx` | 賣家申請與商品審核摘要 | `GET /staff/reviews/`, `POST /staff/seller-requests/:username/review/`, `POST /staff/products/:slug/archive/` | `admin_portal.py`, `auth_demo.py`, `product_management.py` | `users.json`, `products.json` |
| `frontend/app/staff/users/page.tsx` | 會員管理 | `GET /staff/users/`, `POST /staff/users/:username/status/` | `admin_portal.py` | `users.json` |
| `frontend/app/staff/banners/page.tsx` | banner 建立、編輯、審核、排序、刪除 | `GET /staff/banners/`, `POST /staff/banners/`, `PATCH /staff/banners/:id/`, `POST /staff/banners/:id/review/`, `POST /staff/banners/reorder/`, `DELETE /staff/banners/:id/` | `admin_portal.py` | `banners.json` |
| `frontend/app/staff/content/reviews/page.tsx` | 評論內容管理 | `GET /staff/content/reviews/`, `DELETE /staff/content/reviews/:id/` | `admin_portal.py`, `reviews.py` | `reviews.json` |
| `frontend/app/staff/content/questions/page.tsx` | 問答內容管理 | `GET /staff/content/questions/`, `DELETE /staff/content/questions/:id/` | `admin_portal.py`, `questions.py` | `questions.json` |
| `frontend/app/staff/content/posts/page.tsx` | 社群貼文管理 | `GET /staff/content/posts/`, `DELETE /staff/content/posts/:id/` | `admin_portal.py`, `community.py` | `posts.json` |

## 7. 前端功能對應的資料實體

以後換成資料庫時，前端大致會對應到這些實體：

| 前端功能 | 目前來源 | 未來核心資料表 |
| --- | --- | --- |
| 登入 / 註冊 / 會員資料 | `users.json`, session | `users`, `user_addresses`, `user_invoice_profiles`, `seller_requests`, `user_shipping_rules` |
| 商品瀏覽 / 商品詳情 | `products.json` | `products`, `product_images`, `product_variants`, `brands`, `categories`, `product_tags` |
| 購物車 | session | `carts`, `cart_items` 或 server-side session |
| 收藏 / 比較 / 最近瀏覽 | session | `user_favorites`, `compare_items`, `recent_views` 或維持 session |
| 訂單 | `orders.json` | `orders`, `order_items`, `order_service_requests`, `shipment_events` |
| 支付 | `newebpay_payment_logs.json` | `payment_transactions`, `payment_callback_logs` |
| 評論 | `reviews.json` | `product_reviews` |
| 問答 | `questions.json` | `product_questions`, `product_question_answers` |
| 社群 | `posts.json` | `community_posts`, `community_replies`, `community_votes` |
| banner | `banners.json` | `banners`, `banner_applications` |
| 比價 | `competitor_prices.json` | `competitor_sites`, `competitor_products` |

## 8. session 與隱私補充

### session 目前控制的不是只有登入

目前實際還包含：

- cart
- favorite
- compare
- recent view

因此資料庫化時，不能只做 `users` / `orders` / `products`，否則會員體驗會斷層。

### 評論 / 問答 / 社群目前的匿名規則

目前做法是：

- 寫入時保留真實 `author`, `author_username`, `author_user_id`
- 對外 API 顯示時再經過 `privacy.py` 匿名化
- staff / admin 仍保留看真實作者的能力

這代表資料庫化時應保留：

- 內部關聯用 `author_user_id`
- 對外匿名規則在 service / serializer 層處理

不要把「匿名後顯示名稱」直接當唯一儲存值。

## 9. 目前要特別注意的遺漏點

- `cart`, `favorite_products`, `compare_products`, `recent_products` 都還在 signed-cookie session
- logout 目前只清 guest bucket 與 `demo_user`，不是清空所有使用者 bucket
- 買家訂單與賣家訂單頁看的應是同一張訂單資料，只是 serializer 視角不同
- payment debug 目前已集中到 staff 訂單頁
- NewebPay callback / query 還不能視為正式完成，資料表設計時仍要保留 event log

## 10. 相關文件

- 專案整體結構：`PROJECT_STRUCTURE.md`
- 資料庫草稿：`DATABASE_SCHEMA_DRAFT.md`
- 前後端邊界：`FRONTEND_BACKEND_SPLIT.md`

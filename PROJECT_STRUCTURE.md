# PROJECT_STRUCTURE

本文件整理目前專案的實際結構，目的是讓後續「JSON prototype 轉正式資料庫」有一致基準。

## 1. 架構總覽

目前專案是三層式原型：

- `frontend/`
  - Next.js 15 + React 19 + TypeScript
  - 負責所有主要頁面、互動 UI、前端 API proxy
- `myapp/`
  - Django 6 + Django REST Framework
  - 負責 session、權限、API、商業邏輯、JSON 資料存取
- `data/`
  - JSON-backed persistence
  - 目前真正的資料來源，不是資料庫

目前可視為：

- 前端頁面層：`frontend/app/`
- 前端共用元件與型別：`frontend/components/`、`frontend/lib/`
- 後端 API 層：`myapp/api/`
- 後端商業邏輯層：`myapp/services/`
- 後端資料讀寫層：`myapp/repositories/local_store.py`
- 真實資料：`data/*.json`

## 2. 使用套件與模組

### Python 端

| 套件 | 版本 | 目前用途 |
| --- | --- | --- |
| `Django` | `6.0.3` | 專案設定、middleware、session、URL routing |
| `djangorestframework` | `3.17.1` | API endpoint、serializer、permission |
| `drf-spectacular` | `0.29.0` | OpenAPI schema、Swagger UI、ReDoc |
| `pycryptodome` | `>=3.20,<4` | 藍新支付加解密與簽章 |

### Node / 前端

| 套件 | 版本 | 目前用途 |
| --- | --- | --- |
| `next` | `^15.0.0` | App Router、SSR、前端 route handler |
| `react` / `react-dom` | `^19.0.0` | 頁面與元件互動 |
| `typescript` | `^5.0.0` | 型別檢查 |
| `@tiptap/*` | `^3.23.6` | 社群貼文編輯器 |
| `dompurify` | `^3.4.7` | HTML 內容清理 |
| `openai` | `^6.39.0` | 根目錄獨立腳本用途，不屬於主站執行流程 |

## 3. 主要資料夾分工

| 路徑 | 作用 |
| --- | --- |
| `store/` | Django settings、WSGI、根 URLConf |
| `myapp/` | 後端主應用，含 API、service、repository、middleware、tests |
| `frontend/` | Next.js 主站前端 |
| `data/` | JSON 原型資料來源 |
| `templates/` | Django 後端文件頁模板，不是主要前端 |
| `static/` | 靜態檔與上傳檔來源 |
| `staticfiles/` | `collectstatic` 產物 |
| `media/` | 媒體檔輸出位置 |
| `var/` | cache、log 等執行期輸出 |
| `.vscode/` | 本機開發設定 |

## 4. `store/`：後端設定層

### `store/settings.py`

負責：

- Django app / middleware 載入
- CSRF / cookie / host 設定
- session engine
- OpenAPI 設定
- cache / logging / health check 基礎設定

目前重要設定：

- `SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"`
- `DATABASES` 仍是 Django 預設 SQLite，但主要業務資料沒有走 ORM

### `store/urls.py`

負責：

- `/api/v1/` 分派到 `myapp.api.urls`
- `/admin/`
- 舊 Django HTML / redirect routes

### `store/wsgi.py`

負責 WSGI 啟動入口。

## 5. `myapp/`：後端主應用

### `myapp/api/`

這層是 DRF API facade，負責 request / response，不直接碰 JSON 檔。

| 檔案 | 作用 |
| --- | --- |
| `urls.py` | canonical API 路由 |
| `views.py` | endpoint 行為、權限、service orchestration |
| `serializers.py` | request 驗證、response shape |
| `permissions.py` | demo session 權限控制 |
| `route_registry.py` | 前端 docs 頁用的 API 路由說明 |
| `html_write_registry.py` | 舊 HTML write migration 文件資料 |

### `myapp/services/`

這層是商業邏輯核心。

| 模組 | 主要責任 |
| --- | --- |
| `auth_demo.py` | 註冊、登入、角色、賣家申請、帳號狀態 |
| `cart.py` | session 購物車 |
| `personalization.py` | 收藏、比較、最近瀏覽 |
| `orders.py` | checkout、建單、買家/賣家訂單流程 |
| `customer_center.py` | 地址、發票、會員中心整合 |
| `profile.py` | 個人資料、dashboard |
| `product_management.py` | 商品列表、商品建立/編輯、賣家與管理端商品管理 |
| `reviews.py` | 商品評論 |
| `questions.py` | 商品問答與回答 |
| `community.py` | 社群貼文、回覆、投票、圖片上傳 |
| `recommendations.py` | 推薦商品資料 |
| `price_compare.py` | mock 比價資料 |
| `admin_portal.py` | 管理端 dashboard、訂單、用戶、內容審核 |
| `privacy.py` | 公開名稱匿名化 |
| `newebpay_payment_real.py` | 藍新支付整合與 payment debug |
| `newebpay_logistics_real.py` | checkout store map / 超商選店整合 |

### `myapp/repositories/`

| 檔案 | 作用 |
| --- | --- |
| `local_store.py` | 唯一 JSON 讀寫入口，含快取、資料正規化 |

### 其他重要檔案

| 檔案 | 作用 |
| --- | --- |
| `views.py` | 非 DRF 的 Django views、redirect、docs、匯出 |
| `urls.py` | Django 非 API 路由 |
| `middleware.py` | request context、rate limit |
| `context_processors.py` | Django template context |
| `tests.py` | 後端測試 |
| `models.py` | 目前幾乎未使用，尚未建立正式 ORM model |

## 6. `frontend/`：Next.js 主站

### 6.1 App Router 頁面

#### 公開頁

| 路由 | 檔案 | 作用 |
| --- | --- | --- |
| `/` | `frontend/app/page.tsx` | 首頁、商品瀏覽入口 |
| `/products` | `frontend/app/products/page.tsx` | 商品總覽 |
| `/products/[slug]` | `frontend/app/products/[slug]/page.tsx` | 商品詳情、評論、問答、比價、加入購物車 |
| `/products/compare` | `frontend/app/products/compare/page.tsx` | 商品比較 |
| `/brands/[brand_slug]` | `frontend/app/brands/[brand_slug]/page.tsx` | 品牌頁 |
| `/categories/[category_slug]` | `frontend/app/categories/[category_slug]/page.tsx` | 分類頁 |
| `/community` | `frontend/app/community/page.tsx` | 社群列表與發文 |
| `/community/[id]` | `frontend/app/community/[id]/page.tsx` | 社群詳情、回覆、投票 |
| `/login` | `frontend/app/login/page.tsx` | 登入 |
| `/register` | `frontend/app/register/page.tsx` | 註冊 |
| `/docs/routes` | `frontend/app/docs/routes/page.tsx` | 路由與 API 說明頁 |

#### 買家 / 會員頁

| 路由 | 檔案 | 作用 |
| --- | --- | --- |
| `/cart` | `frontend/app/cart/page.tsx` | 購物車 |
| `/checkout` | `frontend/app/checkout/page.tsx` | checkout 預覽與建單 |
| `/orders` | `frontend/app/orders/page.tsx` | 買家訂單列表 |
| `/orders/[id]` | `frontend/app/orders/[id]/page.tsx` | 買家訂單詳情、付款資訊、完成訂單 |
| `/me` | `frontend/app/me/page.tsx` | 會員中心入口 |
| `/me/dashboard` | `frontend/app/me/dashboard/page.tsx` | 個人 dashboard |
| `/me/profile` | `frontend/app/me/profile/page.tsx` | 個人資料 |
| `/me/addresses` | `frontend/app/me/addresses/page.tsx` | 地址管理 |
| `/me/invoice` | `frontend/app/me/invoice/page.tsx` | 發票設定 |

#### 賣家頁

| 路由 | 檔案 | 作用 |
| --- | --- | --- |
| `/me/products` | `frontend/app/me/products/page.tsx` | 賣家商品列表 |
| `/me/products/new` | `frontend/app/me/products/new/page.tsx` | 建立商品 |
| `/me/products/[slug]` | `frontend/app/me/products/[slug]/page.tsx` | 編輯商品 |
| `/me/sales` | `frontend/app/me/sales/page.tsx` | 賣家訂單列表 |
| `/me/sales/[id]` | `frontend/app/me/sales/[id]/page.tsx` | 賣家訂單詳情與出貨狀態 |
| `/me/sales/report` | `frontend/app/me/sales/report/page.tsx` | 銷售報表 |
| `/me/promotions` | `frontend/app/me/promotions/page.tsx` | banner 申請 |
| `/me/shipping-rules` | `frontend/app/me/shipping-rules/page.tsx` | 賣家運費規則 |

#### staff / admin 頁

| 路由 | 檔案 | 作用 |
| --- | --- | --- |
| `/staff/dashboard` | `frontend/app/staff/dashboard/page.tsx` | 管理摘要 |
| `/staff/orders` | `frontend/app/staff/orders/page.tsx` | 管理端訂單列表 |
| `/staff/orders/[id]` | `frontend/app/staff/orders/[id]/page.tsx` | 管理端訂單詳情與 payment debug |
| `/staff/products` | `frontend/app/staff/products/page.tsx` | 商品審核 / 上下架 / 刪除 |
| `/staff/reviews` | `frontend/app/staff/reviews/page.tsx` | 賣家申請與商品審核摘要 |
| `/staff/users` | `frontend/app/staff/users/page.tsx` | 會員管理 |
| `/staff/banners` | `frontend/app/staff/banners/page.tsx` | banner 管理 |
| `/staff/content/reviews` | `frontend/app/staff/content/reviews/page.tsx` | 評論內容管理 |
| `/staff/content/questions` | `frontend/app/staff/content/questions/page.tsx` | 問答內容管理 |
| `/staff/content/posts` | `frontend/app/staff/content/posts/page.tsx` | 社群貼文管理 |

### 6.2 前端共用層

| 路徑 | 作用 |
| --- | --- |
| `frontend/components/site-header.tsx` | 導覽列、登入狀態、購物車/收藏/比較計數、登出 |
| `frontend/components/catalog-browser.tsx` | 商品篩選與清單瀏覽 |
| `frontend/components/home-banner-carousel.tsx` | 首頁 banner 輪播 |
| `frontend/lib/api.ts` | API helper、CSRF、proxy request |
| `frontend/lib/types.ts` | 前端型別定義 |
| `frontend/lib/session-drafts.ts` | 前端 `sessionStorage` 草稿狀態 |
| `frontend/lib/community-editor.ts` | Tiptap editor 與圖片上傳 |
| `frontend/app/api/backend/[...path]/route.ts` | `/api/backend/*` 代理到 Django `/api/v1/*` |
| `frontend/app/backend-assets/[...path]/route.ts` | 靜態資產 proxy |

## 7. `data/`：目前真實資料來源

目前存在的 JSON 檔案：

| 檔案 | 作用 |
| --- | --- |
| `users.json` | 會員、地址、發票、shipping rules |
| `products.json` | 商品、圖片、variant、審核狀態 |
| `orders.json` | 訂單、訂單明細、配送/付款摘要 |
| `reviews.json` | 商品評論 |
| `questions.json` | 商品問答與回答 |
| `posts.json` | 社群貼文與回覆 |
| `banners.json` | 首頁 banner 與申請資料 |
| `recommendations.json` | 推薦商品資料 |
| `competitor_prices.json` | 比價 mock 資料 |
| `newebpay_payment_logs.json` | 藍新支付 debug / callback / query 紀錄 |

注意：

- 目前沒有正式資料庫 migration
- `myapp/models.py` 不是真實資料來源
- 開始建 DB 時，應以 `data/*.json` 現況與 `service` 規則為主

## 8. 目前 canonical API 分組

`myapp/api/urls.py` 現在的 API 分組如下：

- auth / app bootstrap
- member center
- buyer orders
- seller orders
- seller products
- cart / checkout
- NewebPay payment / store map integrations
- staff / admin
- product browse / review / question / compare / recommendation / price compare
- community

實際完整路由請看：

- `myapp/api/urls.py`
- `frontend/app/docs/routes/page.tsx`

## 9. request flow

### 商品詳情頁

1. 使用者打開 `frontend/app/products/[slug]/page.tsx`
2. 頁面透過 `frontend/lib/api.ts` 呼叫 `/api/backend/products/:slug/`
3. Next.js proxy 轉給 Django `/api/v1/products/:slug/`
4. `myapp/api/views.py` 進入對應 API view
5. API view 呼叫 `myapp/services/*`
6. service 透過 `myapp/repositories/local_store.py` 讀取 `data/*.json`
7. JSON response 回到前端 render

### checkout 建立訂單

1. 使用者在 `/checkout` 頁面確認地址、配送、付款、發票
2. 前端呼叫 `/api/backend/checkout/confirm/`
3. Django API 進入 `CheckoutConfirmApi`
4. `orders.py` 建立訂單並清除當前使用者購物車
5. 寫回 `data/orders.json`
6. 前端跳轉到 `/orders/[id]`

## 10. session、暫存與個人化狀態

目前專案不是純 stateless API，以下狀態仍在 session 或瀏覽器暫存內：

### Django signed-cookie session

目前 key：

- `demo_user`
- `cart`
- `favorite_products`
- `compare_products`
- `recent_products`

目前行為：

- cart / favorite / compare / recent 都以 username bucket 隔離
- 未登入使用 `__guest__`
- 登入時會把 guest bucket 合併進目前帳號 bucket
- 登出時會清掉 guest bucket，並移除 `demo_user`

重要注意：

- 目前 logout 不會抹除已登入帳號 bucket 的歷史狀態
- 這是為了同一瀏覽器重新登入時恢復 cart / favorite / compare / recent
- 如果未來改成正式 DB 或 Redis session，要重新決定這是不是期望行為

### 瀏覽器 `sessionStorage`

前端還有草稿型暫存：

- `frontend/lib/session-drafts.ts`
- 由 `site-header.tsx` 在登出時清除

這類資料不在 Django session，也不會寫進 JSON。

## 11. 隱私與匿名規則

### 目前已做對的部分

- `reviews.py` 公開輸出時會匿名化作者名稱
- `questions.py` 公開輸出時會匿名化提問者與回答者名稱
- `community.py` 公開輸出時會匿名化作者與回覆者名稱
- 匿名規則集中在 `myapp/services/privacy.py`

### 目前實際儲存方式

資料層仍保留：

- `author`
- `author_username`
- `author_user_id`

也就是：

- 公開 API 用匿名名稱
- staff / admin 仍能看到原始作者資料
- 開始做 DB 時應保留 `author_user_id` 作為內部關聯，不要用匿名字串當主資料

## 12. 功能盤點與資料庫化前注意事項

### 已有完整主流程的區塊

- 註冊 / 登入 / 登出
- 商品瀏覽 / 商品詳情
- 評論 / 問答 / 社群
- 購物車 / checkout / 建立訂單
- 賣家商品管理
- 賣家訂單與出貨狀態
- staff 商品、用戶、內容、banner 管理

### 仍屬 prototype 或需要明確遷移策略的區塊

- 所有持久化仍是 JSON，不適合正式交易量
- session 採 signed cookies，資料量放大後會遇到 cookie size 問題
- NewebPay 已能導流與記錄 debug，但 callback / query 仍在整合中
- Django ORM model 尚未落地

### 建 DB 前一定要先定義的規則

- 購物車是否要改成資料庫持久化
- 收藏 / 比較 / 最近瀏覽是否要改成資料庫持久化
- logout 是否應清掉所有個人化資料，或只清登入狀態
- 評論 / 問答 / 社群對外是否一律匿名
- staff / admin 是否保留真實作者欄位
- 訂單與商品是否保留 snapshot 欄位，避免日後資料回推失真

## 13. 建 DB 時建議優先閱讀的檔案

- `myapp/repositories/local_store.py`
- `myapp/services/auth_demo.py`
- `myapp/services/cart.py`
- `myapp/services/personalization.py`
- `myapp/services/orders.py`
- `myapp/services/product_management.py`
- `myapp/services/reviews.py`
- `myapp/services/questions.py`
- `myapp/services/community.py`
- `myapp/services/admin_portal.py`
- `myapp/api/urls.py`
- `frontend/lib/types.ts`

## 14. 現階段結論

目前這個專案不是「只有前端頁面待接資料庫」，而是：

- 已有可跑的商城、買家、賣家、staff 流程
- 但資料層仍是 prototype
- 下一步正式建立資料庫時，要一起決定：
  - session 與個人化資料是否落 DB
  - 匿名規則的資料模型
  - 訂單 / 付款 / 出貨 snapshot 與 event log 結構

資料表草稿請接著看 `DATABASE_SCHEMA_DRAFT.md`。

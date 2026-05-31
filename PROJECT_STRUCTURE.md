# PROJECT_STRUCTURE

本文件整理目前專案的實際分工，重點回答三件事：

1. 每個主要套件在哪裡使用
2. 每個資料夾控制網站的哪一塊
3. 前端頁面與後端 API 分別負責什麼

---

## 1. 專案整體架構

目前專案採用：

- `Next.js + React + TypeScript`
  - 作為主要使用者前端
  - 位置：`frontend/`
- `Django + Django REST Framework`
  - 作為後端 API、session auth、管理/API 文件入口
  - 位置：`store/`、`myapp/`
- `JSON 檔案`
  - 作為目前的資料來源
  - 位置：`data/`

換句話說：

- **前端頁面顯示** 主要在 `frontend/`
- **後端商業邏輯與 API** 主要在 `myapp/`
- **設定與 Django 啟動入口** 在 `store/`
- **資料讀寫** 目前透過 `data/*.json`，不是資料庫

---

## 2. 套件使用位置

### Python / Django 端

#### `Django`
- 安裝來源：`requirements.txt`
- 使用位置：
  - `store/settings.py`
  - `store/urls.py`
  - `myapp/urls.py`
  - `myapp/views.py`
  - `myapp/ops_views.py`
- 作用：
  - 啟動後端網站
  - 提供 URL routing
  - 提供 middleware / settings / session / admin

#### `djangorestframework`
- 安裝來源：`requirements.txt`
- 使用位置：
  - `myapp/api/views.py`
  - `myapp/api/serializers.py`
  - `myapp/api/permissions.py`
  - `myapp/api/urls.py`
- 作用：
  - 建立 JSON API
  - 驗證 request payload
  - 做登入、購物車、訂單、商品、管理端 API

#### `drf-spectacular`
- 安裝來源：`requirements.txt`
- 使用位置：
  - `myapp/api/urls.py`
- 作用：
  - 產生 OpenAPI schema
  - 提供 Swagger UI / ReDoc

#### `pycryptodome`
- 安裝來源：`requirements.txt`
- 使用位置：
  - `myapp/services/newebpay_payment_real.py`
- 作用：
  - 藍新支付 sandbox/正式串接所需的 AES 加解密與簽章驗證

### Node / Next.js 端

#### `next`
- 安裝來源：`frontend/package.json`
- 使用位置：
  - `frontend/app/`
  - `frontend/next.config.mjs`
- 作用：
  - 前端路由系統
  - App Router
  - SSR / 靜態頁產生 / route handler

#### `react`
- 安裝來源：`frontend/package.json`
- 使用位置：
  - `frontend/app/**/*.tsx`
  - `frontend/components/*.tsx`
- 作用：
  - 畫面元件
  - state / event handler / client-side interaction

#### `typescript`
- 安裝來源：`frontend/package.json`
- 使用位置：
  - `frontend/app/**/*.ts(x)`
  - `frontend/components/*.tsx`
  - `frontend/lib/*.ts`
  - `frontend/tsconfig.json`
- 作用：
  - 型別檢查
  - API payload / 前端資料結構型別定義

#### `openai`
- 安裝來源：根目錄 `package.json`
- 目前用途：
  - 專案根目錄的獨立測試腳本用途
  - 不屬於 `frontend/` 主前端執行流程

---

## 3. 最上層資料夾用途

| 路徑 | 類型 | 作用 |
| --- | --- | --- |
| `store/` | Django 專案設定 | Django settings、WSGI、根 URLConf |
| `myapp/` | Django 主應用 | API、services、repository、後端邏輯 |
| `frontend/` | Next.js 前端 | 主要網站頁面、前端元件、前端 API proxy |
| `data/` | 本地資料層 | JSON 模擬資料來源 |
| `templates/` | Django 模板 | 目前只保留 docs / 基底模板，不是主要前端 |
| `static/` | 靜態資產來源 | Django 靜態檔來源資料夾 |
| `staticfiles/` | collectstatic 產物 | Django 收集後的靜態檔輸出 |
| `media/` | 媒體檔 | 上傳或測試媒體檔位置 |
| `.vscode/` | 編輯器設定 | VS Code launch/settings |
| `.venv/` | Python 虛擬環境 | 本機 Python 套件環境 |
| `node_modules/` | 根目錄 Node 套件 | 根目錄腳本用途套件，不是 Next.js 主前端依賴 |
| `frontend/node_modules/` | 前端依賴 | Next.js 前端真正使用的 npm 套件 |
| `frontend/.next/` | 前端建置產物 | Next.js build/dev 自動產生，通常不手改 |
| `var/` | 可變資料 | 開發期輸出或暫存用途 |

---

## 4. `store/`：Django 專案設定層

### `store/settings.py`
- 控制：
  - Django 基本設定
  - installed apps
  - middleware
  - allowed hosts / csrf trusted origins
  - 前端網址環境變數
- 和網站的關係：
  - 決定後端能不能正常啟動
  - 決定 Render / 本機環境如何連線

### `store/urls.py`
- 控制：
  - 根 URL 分派
- 目前分派給：
  - `/api/v1/` → `myapp.api.urls`
  - `/` → `myapp.urls`
  - `/admin/` → Django admin

### `store/wsgi.py`
- 控制：
  - Gunicorn / Render 啟動 Django 時的 WSGI 入口

---

## 5. `myapp/`：後端主應用

`myapp/` 是目前後端核心。

### `myapp/api/`

這層是 **DRF API 層**。

#### `myapp/api/urls.py`
- 控制：
  - 所有 canonical API 路由
- 例子：
  - `/api/v1/auth/...`
  - `/api/v1/products/...`
  - `/api/v1/cart/...`
  - `/api/v1/checkout/...`
  - `/api/v1/me/...`
  - `/api/v1/staff/...`
  - `/api/v1/integrations/newebpay/...`

#### `myapp/api/views.py`
- 控制：
  - API endpoint 的 request / response 行為
- 作用：
  - 接收前端請求
  - 驗證權限
  - 呼叫 service
  - 回傳 JSON

#### `myapp/api/serializers.py`
- 控制：
  - API 輸入/輸出格式驗證
- 作用：
  - 驗證登入、註冊、地址、發票、checkout、藍新 payload 等欄位

#### `myapp/api/permissions.py`
- 控制：
  - 哪些 API 只能登入者、賣家、管理者使用

#### `myapp/api/route_registry.py`
- 控制：
  - API 文件分類資料
- 作用：
  - 提供 docs 頁面顯示 API 群組與說明

#### `myapp/api/html_write_registry.py`
- 控制：
  - 舊 HTML 寫入/遷移說明紀錄資料

### `myapp/services/`

這層是 **商業邏輯層**。  
API 不直接碰 JSON 檔，而是先呼叫 services。

主要服務檔案：

- `auth_demo.py`
  - 登入、註冊、角色、seller request
- `cart.py`
  - 購物車邏輯
- `orders.py`
  - 結帳、建立訂單、訂單查詢、訂單更新
- `customer_center.py`
  - 買家端 checkout / 地址 / 發票相關整合
- `product_management.py`
  - 賣家商品建立、編輯、封存、複製
- `reviews.py`
  - 商品評論
- `questions.py`
  - 商品問答
- `community.py`
  - 論壇文章 / 回覆 / 投票
- `recommendations.py`
  - 推薦商品資料
- `personalization.py`
  - 收藏 / 比較 / 個人化狀態
- `profile.py`
  - 會員資料
- `admin_portal.py`
  - 管理端 dashboard / users / orders / review
- `price_compare.py`
  - 外站比價 mock crawler / compare data
- `newebpay_payment.py`
  - 藍新支付 mock
- `newebpay_payment_real.py`
  - 藍新支付 sandbox / 正式串接骨架
- `newebpay_logistics.py`
  - 藍新物流 mock
- `newebpay_logistics_real.py`
  - 藍新物流 sandbox / 正式串接骨架

### `myapp/repositories/`

這層是 **資料讀寫層**。

#### `myapp/repositories/local_store.py`
- 控制：
  - `data/*.json` 的讀寫
- 作用：
  - products / users / orders / reviews / community / payment logs / logistics logs

### `myapp/views.py`
- 控制：
  - 非 DRF 的 Django views
- 目前主要用途：
  - Next.js 前端轉址
  - docs 頁面
  - CSV 匯出

### `myapp/urls.py`
- 控制：
  - Django 這層的 HTML/legacy URL
- 目前主要用途：
  - 將舊 Django 頁面 URL 轉向 Next.js 對應頁面
  - 提供 docs / health / CSV / legacy API alias

### `myapp/ops_views.py`
- 控制：
  - `/health/live/`
  - `/health/ready/`
  - no-db infrastructure docs 頁

### `myapp/tests.py`
- 控制：
  - 後端測試

### `myapp/models.py`
- 目前狀態：
  - 非 ORM 主路徑
- 說明：
  - 專案目前仍以 JSON 為主，尚未正式導入資料庫模型

---

## 6. `frontend/`：主要使用者前端

這是目前網站的主要畫面層。

### `frontend/app/`

這是 Next.js App Router 頁面入口。

#### 共用入口

- `frontend/app/layout.tsx`
  - 全站 layout
  - 包含 header / 共用外框
- `frontend/app/globals.css`
  - 全站樣式
- `frontend/app/page.tsx`
  - 首頁
- `frontend/app/api/backend/[...path]/route.ts`
  - 前端 proxy route
  - 作用：把前端 `/api/backend/...` 代理到 Django `/api/v1/...`

#### 商品 / 內容瀏覽

- `frontend/app/products/page.tsx`
  - 商品總覽頁
- `frontend/app/products/[slug]/page.tsx`
  - 商品詳情頁
  - 控制商品資料、評論、問答、加入購物車、比價區塊
- `frontend/app/products/compare/page.tsx`
  - 商品比較頁
- `frontend/app/brands/[brand_slug]/page.tsx`
  - 品牌商品頁
- `frontend/app/categories/[category_slug]/page.tsx`
  - 分類商品頁
- `frontend/app/community/page.tsx`
  - 社群文章列表
- `frontend/app/community/[id]/page.tsx`
  - 社群文章詳情

#### 認證 / 會員

- `frontend/app/login/page.tsx`
  - 登入頁
- `frontend/app/register/page.tsx`
  - 註冊頁
- `frontend/app/me/page.tsx`
  - 會員中心入口轉向頁
- `frontend/app/me/dashboard/page.tsx`
  - 會員首頁 / dashboard
- `frontend/app/me/profile/page.tsx`
  - 會員資料頁
- `frontend/app/me/addresses/page.tsx`
  - 地址管理頁
- `frontend/app/me/invoice/page.tsx`
  - 發票設定頁

#### 購物 / 訂單

- `frontend/app/cart/page.tsx`
  - 購物車頁
- `frontend/app/checkout/page.tsx`
  - checkout 頁
  - 控制：
    - 商品明細
    - 地址選擇
    - 配送方式
    - 付款方式
    - 發票摘要
    - 備註
- `frontend/app/orders/page.tsx`
  - 買家訂單列表
- `frontend/app/orders/[id]/page.tsx`
  - 買家訂單詳情
  - 包含藍新支付 sandbox 測試區塊

#### 賣家

- `frontend/app/me/products/page.tsx`
  - 賣家商品列表
- `frontend/app/me/products/new/page.tsx`
  - 建立商品頁
- `frontend/app/me/products/[slug]/page.tsx`
  - 編輯商品頁
- `frontend/app/me/sales/page.tsx`
  - 賣家訂單列表
- `frontend/app/me/sales/[id]/page.tsx`
  - 賣家訂單詳情
  - 包含藍新物流 sandbox 測試區塊
- `frontend/app/me/sales/report/page.tsx`
  - 賣家銷售報表

#### 管理端

- `frontend/app/staff/dashboard/page.tsx`
  - 管理端 dashboard
- `frontend/app/staff/orders/page.tsx`
  - 管理端訂單列表
- `frontend/app/staff/orders/[id]/page.tsx`
  - 管理端訂單詳情
- `frontend/app/staff/reviews/page.tsx`
  - 管理端賣家申請審核 / 商品強制下架頁
- `frontend/app/staff/users/page.tsx`
  - 管理端會員管理

#### 文件

- `frontend/app/docs/routes/page.tsx`
  - 前端可讀的路由 / API 文件頁

### `frontend/components/`

這層是可重用前端元件。

- `site-header.tsx`
  - 全站導覽列
  - 顯示登入狀態、購物車 badge、收藏/比較數量
- `catalog-browser.tsx`
  - 商品瀏覽與篩選區塊
- `product-card.tsx`
  - 商品卡片

### `frontend/lib/`

這層是前端工具與型別。

- `api.ts`
  - 前端統一 API 呼叫 helper
  - 處理 proxy path、CSRF、cookie、錯誤格式化
- `types.ts`
  - 前端使用的 TypeScript 型別
  - 對應 Django DRF 回傳 payload

### `frontend/docs/`
- 前端或生成產物說明文件

### `frontend/next.config.mjs`
- 控制：
  - Next.js build 設定
  - `/index -> /` redirect
  - output tracing root

### `frontend/tsconfig.json`
- 控制：
  - TypeScript 編譯規則

### `frontend/README.md`
- 控制：
  - 前端啟動說明

---

## 7. `data/`：目前的資料來源

目前沒有正式資料庫，主要資料存在 `data/*.json`。

常見資料：

- `products.json`
  - 商品資料
- `users.json`
  - 會員資料
- `orders.json`
  - 訂單資料
- `reviews.json`
  - 評論資料
- `questions.json`
  - 問答資料
- `community_posts.json`
  - 社群文章
- `competitor_prices.json`
  - 比價 mock 資料
- `newebpay_payment_logs.json`
  - 藍新支付測試紀錄
- `newebpay_logistics_logs.json`
  - 藍新物流測試紀錄

這代表：

- 本機流程驗證很方便
- 但 Render / 正式環境下不適合當長期交易資料儲存

---

## 8. `templates/`：目前保留的 Django 模板

目前 `templates/` 不再負責主要前端頁面。

保留用途：

- `templates/base.html`
  - Django docs / 後端頁面的基底模板
- `templates/docs/api_route_record.html`
  - API 路由文件頁
- `templates/docs/html_write_migration.html`
  - HTML write migration 說明頁
- `templates/docs/no_db_infrastructure.html`
  - 無資料庫架構說明頁

也就是：

- **主要使用者前端不在這裡**
- 使用者前端目前在 `frontend/app/`

---

## 9. 哪些資料夾通常不要手改

以下路徑大多屬於產物或環境，不應直接當主開發位置：

- `.venv/`
- `node_modules/`
- `frontend/node_modules/`
- `frontend/.next/`
- `staticfiles/`
- `__pycache__/`
- `tsconfig.tsbuildinfo`

---

## 10. 請求流向

### 例：前端商品頁

1. 使用者打開 `frontend/app/products/[slug]/page.tsx`
2. 頁面呼叫 `frontend/lib/api.ts`
3. 請求送到 `frontend/app/api/backend/[...path]/route.ts`
4. proxy 轉發到 Django `/api/v1/products/<slug>/`
5. Django `myapp/api/views.py` 收到請求
6. API view 呼叫 `myapp/services/...`
7. service 透過 `myapp/repositories/local_store.py` 讀 `data/*.json`
8. 資料回傳到前端頁面 render

### 例：checkout 建立訂單

1. 使用者在 `frontend/app/checkout/page.tsx` 確認資料
2. 前端送出到 `/api/backend/checkout/confirm/`
3. Django `/api/v1/checkout/confirm/` 收到請求
4. `CheckoutConfirmApi` 呼叫 `orders.py` / `customer_center.py`
5. 訂單資料寫入 `data/orders.json`
6. 前端跳轉到訂單頁 `frontend/app/orders/[id]/page.tsx`

---

## 11. 目前最重要的開發位置

如果你後續要繼續看網站功能，優先看這幾個位置：

- **前端頁面**
  - `frontend/app/`
- **前端共用元件**
  - `frontend/components/`
- **前端 API helper / 型別**
  - `frontend/lib/`
- **後端 API**
  - `myapp/api/views.py`
  - `myapp/api/serializers.py`
  - `myapp/api/urls.py`
- **後端商業邏輯**
  - `myapp/services/`
- **資料來源**
  - `data/*.json`

---

## 12. 現階段架構結論

目前專案已經是：

- `Next.js` 作為主要網站前端
- `Django + DRF` 作為主要後端 API
- `JSON data files` 作為目前資料來源

所以你之後看網站時，可以用這個簡單判斷：

- **看畫面/UI** → `frontend/`
- **看 API / session / checkout / 藍新** → `myapp/api` + `myapp/services`
- **看設定 / Render / host / CSRF** → `store/settings.py`
- **看目前實際資料** → `data/`

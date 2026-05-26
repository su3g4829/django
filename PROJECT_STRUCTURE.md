# 專案資料夾與功能總覽

本文件用來快速辨認這個專案中：

- 哪些資料夾屬於 Django / DRF / Next.js / Node.js
- 哪些是前端、後端、資料層、產物目錄
- 每個資料夾主要控制哪一塊功能
- 畫面是由哪一層呈現

---

## 1. 專案整體架構

這個專案目前是 **雙前端入口 + 單後端 API** 的結構：

- **Django 模板站**
  - 由 Django 直接 render HTML
  - 主要模板放在 `templates/`
- **Next.js 獨立前端**
  - 放在 `frontend/`
  - 透過 DRF API 吃資料
- **Django + DRF 後端**
  - 放在 `store/` 與 `myapp/`
  - 負責頁面 view、API、商業邏輯、JSON 資料讀寫
- **本地 JSON 資料層**
  - 放在 `data/`
  - 目前尚未改成正式資料庫

---

## 2. 最上層資料夾對照

| 路徑 | 技術/套件歸屬 | 前端/後端 | 主要用途 |
|---|---|---|---|
| `.venv/` | Python 虛擬環境 | 後端執行環境 | Django、DRF、OpenAI Python SDK 等套件安裝位置 |
| `.vscode/` | VS Code | 開發工具 | Debug、Python interpreter、工作區設定 |
| `data/` | 專案自訂資料層 | 後端資料來源 | 本地 JSON 資料，例如商品、會員、評論、訂單 |
| `frontend/` | Next.js / React / TypeScript | 前端 | 獨立前端 SPA/SSR 入口 |
| `media/` | Django 媒體檔案 | 前後端共用資源 | 使用者上傳檔、商品圖片等 |
| `myapp/` | Django app | 後端 | 專案主要業務邏輯、views、services、api |
| `node_modules/` | Node.js 套件安裝目錄 | 前端執行環境 | Next.js、React 等 npm 套件實體檔案 |
| `static/` | Django static source | 前端靜態資源 | 專案原始靜態資源 |
| `staticfiles/` | Django collectstatic 輸出 | 部署產物 | 正式部署時彙整的 static 檔案 |
| `store/` | Django project | 後端 | 專案設定、URL 入口、WSGI/ASGI、工具腳本 |
| `templates/` | Django Templates | 前端（模板站） | Django server-side render 的 HTML 頁面 |
| `var/` | 營運/執行產物 | 後端營運 | log、cache 等運行時資料 |
| `manage.py` | Django | 後端 | Django 管理命令入口 |
| `requirements.txt` | pip | 後端依賴清單 | Python 套件版本 |
| `package.json` | npm | 前端依賴清單 | 根目錄 Node 套件描述（非主要前端來源） |
| `package-lock.json` | npm | 前端依賴鎖定 | Node 套件版本鎖定 |
| `db.sqlite3` | Django/SQLite | 後端 | 目前保留的 SQLite 檔；主要業務資料仍以 JSON 為主 |

---

## 3. Django 後端：`store/`

`store/` 是 **Django project 設定層**，不是主要業務邏輯層。

### 主要檔案

| 路徑 | 屬於哪個技術 | 功能 |
|---|---|---|
| `store/settings.py` | Django | 全域設定：INSTALLED_APPS、middleware、templates、static、DRF、logging、security |
| `store/urls.py` | Django | 全站 URL 根入口，把路由分派到 `myapp.urls` |
| `store/wsgi.py` | Django WSGI | 傳統 Python Web Server 入口 |
| `store/asgi.py` | Django ASGI | 非同步/ASGI 入口 |
| `store/store_image.py` | Python + OpenAI SDK | 測試 OpenAI Images API 的獨立腳本 |
| `store/store_image.js` | Node.js + OpenAI SDK | 若用 Node.js 測試圖片生成，可放這類腳本 |

### 這層控制什麼

- Django 啟動時先讀 `store/settings.py`
- 全站網址先進 `store/urls.py`
- 這一層不負責商業規則本身

---

## 4. Django 主應用：`myapp/`

`myapp/` 是 **專案主要業務 app**。  
如果要找「電商流程、會員、賣家、後台、API」，大多都在這裡。

### `myapp/` 重要檔案

| 路徑 | 屬於哪個技術 | 前/後端 | 功能 |
|---|---|---|---|
| `myapp/views.py` | Django view | 後端 -> 模板前端 | Django 模板站頁面控制器 |
| `myapp/urls.py` | Django URLconf | 後端 | 定義 Django 模板站路由 |
| `myapp/middleware.py` | Django middleware | 後端 | request id、rate limit、request context |
| `myapp/context_processors.py` | Django Templates | 後端 -> 模板前端 | 把購物車摘要等資料注入模板 |
| `myapp/tests.py` | Django test | 後端 | 專案測試 |
| `myapp/ops_views.py` | Django view | 後端 | health check、營運檢查頁 |

### `myapp/services/`

這層是 **商業邏輯層**。  
不直接管 HTML，不直接管資料檔案細節，重點是「功能規則」。

| 路徑 | 功能 |
|---|---|
| `myapp/services/auth_demo.py` | 仿 auth 會員登入、註冊、角色、狀態管理 |
| `myapp/services/cart.py` | 購物車邏輯、金額計算 |
| `myapp/services/orders.py` | 訂單、買家/賣家履約、售後、報表 |
| `myapp/services/product_management.py` | 商品 CRUD、圖片、審核、變體、庫存 |
| `myapp/services/reviews.py` | 商品評論 |
| `myapp/services/questions.py` | 商品問答 Q&A |
| `myapp/services/recommendations.py` | 推薦商品 |
| `myapp/services/community.py` | 論壇文章、回覆、投票 |
| `myapp/services/customer_center.py` | 地址簿、發票資料 |
| `myapp/services/profile.py` | 我的內容 / dashboard 聚合 |
| `myapp/services/admin_portal.py` | 平台管理後台摘要資料 |

### `myapp/repositories/`

這層是 **資料存取層**。

| 路徑 | 功能 |
|---|---|
| `myapp/repositories/local_store.py` | 讀寫 `data/*.json`，目前等同簡易資料庫 |

這層控制：
- 商品 JSON
- 會員 JSON
- 訂單 JSON
- 評論 / 問答 / 論壇 JSON

如果之後改 ORM / PostgreSQL，這層通常是第一個重構點。

### `myapp/api/`

這層是 **DRF API 層**。

| 路徑 | 屬於哪個技術 | 功能 |
|---|---|---|
| `myapp/api/views.py` | DRF `APIView` | 定義 `/api/v1/...` API 行為 |
| `myapp/api/serializers.py` | DRF Serializer | 驗證 request / 組裝 response |
| `myapp/api/permissions.py` | DRF Permission | API 權限判斷 |
| `myapp/api/urls.py` | DRF URLconf | API 路由入口 |
| `myapp/api/route_registry.py` | 專案文件 | 紀錄 canonical API 路由 |
| `myapp/api/html_write_registry.py` | 專案文件 | 紀錄舊 HTML write route 被 DRF 取代的映射 |

---

## 5. 本地資料：`data/`

這是目前專案的 **JSON 資料來源**。

| 檔案 | 功能 |
|---|---|
| `data/products.json` | 商品資料 |
| `data/users.json` | 會員/賣家/管理員資料 |
| `data/orders.json` | 訂單資料 |
| `data/reviews.json` | 商品評論 |
| `data/questions.json` | 商品問答 |
| `data/posts.json` | 社群論壇文章 |
| `data/recommendations.json` | 推薦關聯資料 |

### 這層屬於什麼

- 屬於專案自訂資料層
- **不是 Django 內建功能**
- **不是 Node.js 功能**
- 目前是為了「不接資料庫」而做的暫時結構

---

## 6. Django 模板前端：`templates/`

這是 **Django server-side render** 的前端頁面。  
使用 Django Template 語法，例如：

- `{% extends "base.html" %}`
- `{% block content %}`
- `{{ product.name }}`

### 主要資料夾

| 路徑 | 前端呈現區塊 | 主要頁面功能 |
|---|---|---|
| `templates/base.html` | 全站共用版型 | header、footer、Bootstrap、共用 JS |
| `templates/home.html` | 首頁 | Hero、精選商品、分類、品牌、社群 |
| `templates/auth/` | 會員頁 | 登入、註冊 |
| `templates/products/` | 商品前台 | 列表、詳情、表單、比較頁 |
| `templates/cart/` | 購物流程 | 購物車 |
| `templates/checkout/` | 購物流程 | 結帳預覽、完成頁 |
| `templates/orders/` | 買家中心 | 訂單列表、訂單明細 |
| `templates/community/` | 社群論壇 | 列表、文章詳情 |
| `templates/me/` | 會員中心 | dashboard、地址、發票、個資、我的商品 |
| `templates/seller/` | 賣家中心 | 賣家訂單、賣家報表 |
| `templates/staff/` | 管理後台 | dashboard、訂單審核、會員管理、商品/賣家審核 |
| `templates/docs/` | 文件頁 | API 路由總覽、遷移紀錄、no-DB 基礎設施說明 |

### 這層屬於什麼

- 屬於 **Django 本身的模板功能**
- 前端會由 Django 在伺服器端先 render 成 HTML 再送給瀏覽器

---

## 7. Next.js 前端：`frontend/`

`frontend/` 是 **獨立前端專案**。  
技術組成：

- `next`
- `react`
- `react-dom`
- `typescript`

這一層主要目的：
- 不走 Django 模板 render
- 直接呼叫 Django DRF API
- 做前後端分離的前端入口

### 主要檔案與資料夾

| 路徑 | 屬於哪個技術 | 前/後端 | 功能 |
|---|---|---|---|
| `frontend/package.json` | npm / Next.js | 前端 | 前端依賴與 scripts |
| `frontend/README.md` | 文件 | 前端說明 | 前端啟動與使用說明 |
| `frontend/app/` | Next.js App Router | 前端 | 各頁面路由 |
| `frontend/components/` | React 元件 | 前端 | 共用 UI 元件 |
| `frontend/lib/` | TS 工具層 | 前端 | API client、型別定義 |
| `frontend/.env.example` | Next.js 環境變數範本 | 前端 | 範例環境設定 |
| `frontend/.next/` | Next.js build/dev 產物 | 前端產物 | 自動生成，不手改 |

### `frontend/app/` 頁面分區

| 路徑 | 呈現頁面 | 主要用途 |
|---|---|---|
| `frontend/app/page.tsx` | Next.js 首頁 | 前端首頁 |
| `frontend/app/login/` | 登入頁 | 會員登入 |
| `frontend/app/register/` | 註冊頁 | 會員註冊 |
| `frontend/app/products/[slug]/` | 商品詳情頁 | 商品、評論、問答、加入購物車 |
| `frontend/app/cart/` | 購物車頁 | 購物車內容、更新、錯誤提示 |
| `frontend/app/checkout/` | 結帳頁 | 結帳前檢查 |
| `frontend/app/orders/` | 訂單頁 | 買家訂單列表與明細 |
| `frontend/app/me/` | 會員中心 | profile、addresses、invoice、dashboard、products、sales |
| `frontend/app/staff/` | 管理中心 | dashboard、orders、reviews、users |
| `frontend/app/docs/routes/` | 文件頁 | 前端頁面對應的 API 路由說明 |
| `frontend/app/api/backend/[...path]/route.ts` | Next.js server route | 把前端請求 proxy 到 Django API |

### 這層如何呈現

- 使用 React component render 畫面
- 在瀏覽器端或 Next server side 取 API 資料
- 再渲染成頁面

### 它和 Django 模板站的差別

| 類型 | Django 模板站 | Next.js 前端 |
|---|---|---|
| 畫面產生 | Django server render HTML | React / Next render |
| API 使用 | 可直接由 Django view 帶資料 | 透過 `/api/v1/...` 抓資料 |
| 適合用途 | 快速頁面、後台模板 | 前後端分離、互動式前端 |

---

## 8. `frontend/.next/` 與 `node_modules/` 是什麼

這兩個目錄很常讓人混淆，但都不是主要業務程式碼。

### `frontend/.next/`

- 屬於 **Next.js 自動生成產物**
- 來源於：
  - `next dev`
  - `next build`
- 包含：
  - route manifest
  - chunk
  - polyfill
  - server reference manifest

**重點：不要手動維護這裡的程式碼。**

### `node_modules/`

- 屬於 **npm 安裝的第三方套件實體目錄**
- 例如：
  - `next`
  - `react`
  - `react-dom`
- **不是你自己專案的業務邏輯**

---

## 9. 套件與資料夾的關係

### Python / Django / DRF

| 套件 | 在哪裡用到 | 功能 |
|---|---|---|
| `Django` | `store/`, `myapp/`, `templates/` | Web framework、URL、view、template、middleware、static |
| `djangorestframework` | `myapp/api/` | API view、serializer、permission |
| `drf-spectacular` | `store/settings.py`, API docs routes | OpenAPI schema、Swagger UI、ReDoc |
| `openai` | `store/store_image.py` | 呼叫 OpenAI Images API |

### Node.js / Next.js / React

| 套件 | 在哪裡用到 | 功能 |
|---|---|---|
| `next` | `frontend/app/`、`frontend/.next/` | Next.js 路由、SSR/CSR、server route |
| `react` | `frontend/app/`, `frontend/components/` | UI component |
| `react-dom` | Next.js runtime | React DOM render |
| `typescript` | `frontend/**/*.ts`, `frontend/**/*.tsx` | 型別檢查與前端程式碼結構化 |

---

## 10. 一個請求大概怎麼流動

### A. Django 模板頁面

1. 瀏覽器打開 `/products/acme-mug/`
2. `store/urls.py` -> `myapp/urls.py`
3. `myapp/views.py` 的頁面 view 執行
4. `myapp/services/*` 取業務資料
5. `myapp/repositories/local_store.py` 讀 `data/*.json`
6. Django render `templates/products/detail.html`
7. HTML 回到瀏覽器

### B. Next.js 前端頁面

1. 瀏覽器打開 `frontend` 的某個頁面
2. Next.js page component 執行
3. `frontend/lib/api.ts` 呼叫 API
4. Next proxy route / 直接打 Django `/api/v1/...`
5. `myapp/api/views.py` + serializer 處理
6. service / repository 取資料
7. JSON 回前端
8. React render 畫面

---

## 11. 目前最該編輯哪裡

| 想改的東西 | 優先看哪裡 |
|---|---|
| Django 全站設定 | `store/settings.py` |
| Django 頁面路由 | `myapp/urls.py` |
| Django 模板頁面邏輯 | `myapp/views.py` |
| API 行為 | `myapp/api/views.py` |
| API 輸入/輸出格式 | `myapp/api/serializers.py` |
| 商業邏輯 | `myapp/services/` |
| 本地 JSON 讀寫 | `myapp/repositories/local_store.py` |
| Django HTML 畫面 | `templates/` |
| Next.js 畫面 | `frontend/app/` |
| Next.js 共用元件 | `frontend/components/` |
| Next.js API client / 型別 | `frontend/lib/` |
| OpenAI 圖片測試 | `store/store_image.py` |

---

## 12. 哪些資料夾通常不要手改

| 路徑 | 原因 |
|---|---|
| `.venv/` | 套件安裝環境，不手動改內容 |
| `node_modules/` | npm 套件安裝目錄，不手動改內容 |
| `frontend/.next/` | Next.js 自動產物，每次 build/dev 可能覆蓋 |
| `staticfiles/` | collectstatic 產物，通常不直接編輯 |
| `__pycache__/` | Python 編譯快取，不需要手改 |

---

## 13. 一句話辨認法

- `store/`：Django 專案設定層
- `myapp/`：主要後端業務邏輯
- `templates/`：Django 模板前端
- `frontend/`：Next.js 獨立前端
- `data/`：目前的 JSON 資料來源
- `media/`：上傳檔 / 商品圖
- `.next/`、`node_modules/`：自動產物 / 套件，不是主要業務程式碼


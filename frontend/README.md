# Next.js Frontend

這個資料夾是獨立前端，使用 `Next.js` 呼叫 Django DRF API。

## 作用

- 提供前後端分離的前端頁面。
- 透過 Next.js route handler 代理到 Django，沿用目前的 `session` / `CSRF` 流程。
- 在還沒切 ORM、還沒改正式 `django.contrib.auth` 之前，先用既有 DRF API 完成前端串接。

## 目前頁面

- `/` 商品首頁
- `/login` 登入
- `/register` 註冊
- `/products/[slug]` 商品詳情
- `/cart` 購物車
- `/checkout` 結帳
- `/orders` 我的訂單
- `/orders/[id]` 訂單明細
- `/me/dashboard` 會員中心
- `/me/profile` 會員資料
- `/me/addresses` 地址簿
- `/me/invoice` 發票資料
- `/me/products` 賣家商品管理
- `/me/sales` 賣家訂單
- `/me/sales/report` 賣家報表
- `/staff/dashboard` 管理儀表板
- `/staff/orders` 平台訂單管理
- `/staff/users` 會員管理
- `/staff/reviews` 審核台
- `/docs/routes` 前端路由文件

## API 代理方式

Next.js 不是直接打外部 API 網址，而是先走自己的 proxy：

- Next route: `app/api/backend/[...path]/route.ts`
- Django origin: `DJANGO_API_ORIGIN`
- Django API base: `${DJANGO_API_ORIGIN}/api/v1/`

這樣做的目的：

- 保留 cookie
- 保留 session
- 保留 CSRF 流程
- 避免前端每支 API 都自己處理跨來源細節

## 安裝

先確認本機已安裝：

- Node.js LTS
- npm

可用以下指令確認版本：

```bash
node -v
npm -v
```

安裝依賴：

```bash
npm install
```

## 環境變數

1. 複製 `.env.example`
2. 另存成 `.env.local`

範例：

```env
DJANGO_API_ORIGIN=http://127.0.0.1:8000
```

## 啟動方式

### 1. 先啟動 Django 後端

在專案根目錄：

```bash
.\.venv\Scripts\python.exe manage.py runserver
```

### 2. 再啟動 Next.js 前端

在 `frontend/` 資料夾：

```bash
npm run dev
```

預設前端會跑在：

- `http://localhost:3000`

後端預設會跑在：

- `http://127.0.0.1:8000`

## 常用指令

```bash
npm run dev
npm run build
npm run start
npm run lint
```

## 補充

- 目前前端是接既有 DRF API，不是直接讀 Django template。
- 後端資料仍是 JSON-backed prototype，不是 ORM / DB 版。
- 若之後切 ORM，只要 API contract 維持穩定，前端可以少量調整。

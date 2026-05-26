# Next.js 產生的 JS / Manifest 檔案說明

這份文件用來說明 `frontend/.next/` 內常見的自動產物。

## 先講結論

- `frontend/.next/` 是 **Next.js 建置輸出目錄**
- 這裡面的 `.js`、`.json` 大多不是你手寫的商業邏輯
- 它們通常屬於：
  - `next`
  - `react`
  - Next.js 打包流程內建的 runtime / polyfill / manifest
- **不要把長期註解直接寫進 `.next` 產物**
  - 因為每次 `npm run dev`、`npm run build` 都可能覆蓋

真正應該長期閱讀與維護的是：

- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`

---

## 你目前看到的檔案

### `frontend/.next/static/development/_ssgManifest.js`

- **所屬套件**：`next`
- **用途**：記錄哪些頁面屬於 SSG（Static Site Generation）相關清單
- **你目前看到的內容**：
  - `self.__SSG_MANIFEST = new Set(...)`
- **代表什麼**
  - 這是 Next.js 前端 runtime 在瀏覽器端使用的 manifest
  - 若某些頁面是靜態生成，Next.js 會用它追蹤
- **目前這個專案的狀態**
  - 內容很小，表示目前沒有大量靜態頁面需要特殊註記

---

### `frontend/.next/static/development/_buildManifest.js`

- **所屬套件**：`next`
- **用途**：前端路由與 chunk 載入對照表
- **你目前看到的內容**：
  - `self.__BUILD_MANIFEST = ...`
  - `sortedPages`
  - `rewrites`
- **代表什麼**
  - Next.js 會用它決定：
    - 某個頁面要載哪些 JS chunk
    - 前端切頁時要抓哪些資源
    - rewrites / route 資訊
- **目前這個專案的狀態**
  - 開發模式內容通常比較精簡

---

### `frontend/.next/static/chunks/polyfills.js`

- **所屬套件**：
  - 主要是 `next`
  - 內含 browser polyfill 與其相依 runtime
  - 常可看到 `core-js` 風格內容、`fetch` polyfill、ES 功能補丁
- **用途**：補齊舊環境缺少的 JavaScript / Web API 能力
- **你目前看到的內容特徵**
  - 大量壓縮過的程式
  - `Array.from`、`Promise`、`fetch`、`Object.assign` 等 polyfill
- **代表什麼**
  - 不是你專案自己寫了一大包商業邏輯
  - 是 Next.js 為了瀏覽器相容性打進來的基礎 runtime
- **你應該怎麼看**
  - 如果只是想知道「頁面功能怎麼做」，通常不需要讀這個檔案

---

### `frontend/.next/server/server-reference-manifest.json`

- **所屬套件**：`next`（App Router / React Server Components 機制）
- **用途**：記錄 server references / server actions / RSC 相關資訊
- **你目前看到的內容**
  - `node`
  - `edge`
  - `encryptionKey`
- **代表什麼**
  - 這是 Next.js server 端在執行 App Router 時的 metadata
  - 用來追蹤哪些 server-side reference 可以被前端或 server runtime 使用
- **目前這個專案的狀態**
  - 幾乎是空的，表示你現在沒有大量 server actions 配置

---

### `frontend/.next/server/server-reference-manifest.js`

- **所屬套件**：`next`
- **用途**：把 server reference manifest 轉成 JS 形式給 runtime 使用
- **你目前看到的內容**
  - `self.__RSC_SERVER_MANIFEST = "..."`
- **代表什麼**
  - 本質上和 `.json` 那份是同一類資訊
  - 只是提供給不同載入流程使用

---

## 它們和你專案原始碼的對應關係

### 1. `.next/static/...`

通常對應：

- `frontend/app/` 內的頁面
- `frontend/components/` 內的元件
- `frontend/lib/` 內的工具函式

也就是說：

- 你改 `frontend/app/page.tsx`
- Next.js 重新編譯
- 然後輸出新的 `.next/static/...` JS

### 2. `.next/server/...`

通常對應：

- App Router
- Route handlers
- Server Components
- 伺服器端 manifest / metadata

你這個專案特別相關的來源包含：

- `frontend/app/api/backend/[...path]/route.ts`
- `frontend/app/layout.tsx`
- `frontend/app/**/page.tsx`

---

## 這些檔案是不是「某個 npm 套件的原始碼」？

不完全是。

比較準確的說法是：

- 它們是 **Next.js 建置後產生的輸出**
- 裡面會混合：
  - 你的應用程式碼
  - `next` runtime
  - `react` runtime
  - polyfills
  - build manifest

所以你看到一個 `.js` 檔，不一定能直接說它「只屬於某一個套件」。

但可以這樣理解：

- `_ssgManifest.js` → 幾乎就是 `next`
- `_buildManifest.js` → 幾乎就是 `next`
- `polyfills.js` → `next` 打包進來的 polyfill/runtime
- `server-reference-manifest.*` → `next` 的 App Router / RSC metadata

---

## 開發時該看哪裡，不該看哪裡

### 優先看

- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`

### 通常不用直接改

- `frontend/.next/static/...`
- `frontend/.next/server/...`

---

## 你目前這個前端真正手寫的核心來源

例如：

- `frontend/app/page.tsx`
  - 商品首頁
- `frontend/app/products/[slug]/page.tsx`
  - 商品詳情、評論、問答、加入購物車
- `frontend/app/cart/page.tsx`
  - 購物車
- `frontend/app/orders/page.tsx`
  - 訂單列表
- `frontend/components/site-header.tsx`
  - 共用導覽列
- `frontend/lib/api.ts`
  - 封裝 fetch、CSRF、proxy 呼叫
- `frontend/lib/types.ts`
  - 前端型別定義

---

## 建議做法

如果你未來再看到 `.next` 裡的新 JS 檔：

1. 先看檔名是不是 manifest / chunk / polyfills
2. 若是，就先判斷它是 **Next.js 建置產物**
3. 再回頭找對應的 `frontend/app` 或 `frontend/components` 原始碼

不要反過來從 `.next` 追功能，成本很高。

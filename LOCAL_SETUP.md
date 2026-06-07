# Local Setup

這份文件是給「換一台電腦、重新 clone 專案」時使用的本機啟動指南。

這個專案不是純靜態網站，不能只靠 VS Code `Go Live` 預覽。  
你需要同時啟動：

- Django 後端
- Next.js 前端

## 1. 需求

本機請先安裝：

- `git`
- `Python`
- `Node.js`
- `VS Code`

建議先確認版本：

```powershell
python --version
node -v
npm -v
git --version
```

## 2. Clone 專案

```powershell
git clone <你的-repo-url>
cd store
```

## 3. 建立 Python 虛擬環境

```powershell
..\Scripts\Activate.ps1
pip install -r requirements.txt
```

後端依賴目前來自 [requirements.txt](/c:/dvds/store/requirements.txt)。

## 4. 安裝前端套件

```powershell
cd frontend
npm install
cd ..
```

前端 scripts 來自 [frontend/package.json](/c:/dvds/store/frontend/package.json)。

## 5. 補本機環境檔

以下檔案不會進 git，因為 [.gitignore](/c:/dvds/store/.gitignore) 有排除：

- `store/.env`
- `frontend/.env.local`
- `db.sqlite3`
- `../Scripts/` (parent Python virtual environment)

所以換機後需要自己建立。

### 5.1 前端環境檔

先從範例複製：

```powershell
Copy-Item frontend\.env.example frontend\.env.local
```

再確認 [frontend/.env.local](/c:/dvds/store/frontend/.env.local) 內容至少有：

```env
DJANGO_API_ORIGIN=http://127.0.0.1:8000
```

用途：

- Next.js route handler 會透過這個值 proxy 到 Django

### 5.2 Django 環境檔

建立 `store/.env`。

範例：

```env
DJANGO_DEBUG=1
DJANGO_SECRET_KEY=django-insecure-local-dev-key
STORE_FRONTEND_ORIGIN=http://localhost:3000
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,testserver
```

如果你要測藍新金流，再另外補上你實際使用的藍新相關環境變數。

注意：

- Django settings 目前讀的是 `store/.env`
- 不是根目錄的 `django.env`

設定來源可參考 [store/settings.py](/c:/dvds/store/store/settings.py)。

## 6. 初始化 Django

雖然這個專案主要業務資料很多仍是 `data/*.json`，但 Django 本身仍有 SQLite 設定。  
首次在新電腦啟動時，先跑：

```powershell
..\Scripts\python.exe manage.py migrate
```

這會建立 Django 自己需要的基本資料表。

## 7. 啟動後端

```powershell
..\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

後端網址：

- `http://127.0.0.1:8000`
- API base: `http://127.0.0.1:8000/api/v1/`

## 8. 啟動前端

另開一個終端機：

```powershell
cd frontend
npm run dev
```

前端網址：

- `http://localhost:3000`

## 9. 本機啟動後怎麼看

常用頁面：

- 首頁：`http://localhost:3000`
- 商品總覽：`http://localhost:3000/products`
- 購物車：`http://localhost:3000/cart`
- 結帳：`http://localhost:3000/checkout`
- 買家訂單：`http://localhost:3000/orders`
- 賣家訂單：`http://localhost:3000/me/sales`
- staff 後台：`http://localhost:3000/staff/dashboard`

## 10. 這個專案目前的資料來源

要注意目前並不是所有資料都走 Django ORM。

目前主要資料來源包含：

- `data/*.json`
- Django signed cookie session
- 本機 SQLite 只提供 Django 基礎功能

也就是說：

- clone 下來後，`data/` 內的 JSON 會一起帶過來
- session 狀態不會跟著 git 移動
- SQLite 若被 `.gitignore` 排除，就要在新機重新建立

## 11. 不能只用 Go Live 的原因

`Go Live` 比較適合：

- 純 HTML
- 純 CSS
- 純前端靜態頁

這個 repo 不適合只靠 `Go Live`，因為它有：

- Django API
- session
- CSRF
- Next.js route handler
- 前後端 proxy

所以正確做法一定是：

1. 跑 Django
2. 跑 Next.js
3. 用瀏覽器打開 `localhost:3000`

## 12. 最短流程

如果只是要在新電腦快速跑起來，最短流程如下：

```powershell
git clone <你的-repo-url>
cd store
..\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item frontend\.env.example frontend\.env.local
```

手動建立 `store/.env` 後繼續：

```powershell
..\Scripts\python.exe manage.py migrate
..\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

另開終端：

```powershell
cd frontend
npm install
npm run dev
```

## 13. 如果啟動失敗，先檢查

1. `store/.env` 是否存在
2. `frontend/.env.local` 是否存在
3. `DJANGO_API_ORIGIN` 是否指向 `http://127.0.0.1:8000`
4. Django 是否真的跑在 `8000`
5. 前端是否真的跑在 `3000`
6. 套件是否已安裝完成

## 14. 補充

如果你之後要讓其他人更容易 clone 使用，建議再補：

- `store/.env.example`
- 更乾淨的 `frontend/README.md`
- JSON 資料初始化說明

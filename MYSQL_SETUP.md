# MySQL Setup

這份文件整理：

- 在本機用 MySQL Workbench 建立 `store` 專案資料庫
- Django 之後要怎麼接到 MySQL
- 如果換電腦，要怎麼把資料庫搬過去並正常啟動

注意：

- `MySQL Workbench` 是圖形化管理工具，不是資料庫本體。
- 你必須先有 `MySQL Server`，Workbench 才能連線。
- 目前專案還在資料表規劃階段，這份文件先提供建庫與連線流程，不代表現在就要立刻切換正式資料來源。

## 1. 先確認你有可連線的 MySQL Server

如果 Workbench 已經能打開像 `Local instance MySQL93` 這種連線，而且左邊能看到 `SCHEMAS`，代表：

- MySQL Server 已經安裝
- Workbench 已經成功連到資料庫

如果還沒確認，也可以在 PowerShell 檢查：

```powershell
mysql --version
```

或到 Windows 服務確認是否有類似：

- `MySQL80`
- `MySQL93`

## 2. 在 Workbench 建立連線

如果首頁已經有現成連線，例如：

- `Local instance MySQL93`

直接點進去即可。

如果沒有：

1. 打開 MySQL Workbench。
2. 在 `MySQL Connections` 區塊按 `+`。
3. 輸入：
   - `Connection Name`: `local-mysql`
   - `Connection Method`: `Standard (TCP/IP)`
   - `Hostname`: `127.0.0.1`
   - `Port`: `3306`
   - `Username`: 例如 `root`
4. 按 `Test Connection`。
5. 成功後儲存。

## 3. 建立專案資料庫 `store_db`

進入連線後：

1. 點中間的 SQL 編輯區，例如 `Query 1`
2. 貼上：

```sql
CREATE DATABASE store_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. 按上方閃電圖示執行
4. 左邊 `SCHEMAS` 按右鍵選 `Refresh All`
5. 確認出現 `store_db`

如果你之後要在同一個 SQL 視窗繼續操作，可以先切進這個資料庫：

```sql
USE store_db;
```

## 4. 建議建立專案專用帳號

不要長期讓 Django 用 `root` 直接連資料庫，建議另外建立：

```sql
CREATE USER 'store_user'@'localhost' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON store_db.* TO 'store_user'@'localhost';
FLUSH PRIVILEGES;
```

請把：

- `your_password_here`

換成你自己的密碼。

如果你之後 Django 不是跑在同一台機器，而是別台主機連這台 MySQL，授權主機要另外調整，不能只用 `localhost`。

## 5. Django 之後切到 MySQL 需要什麼

目前專案預設還是 SQLite。之後真的要切到 MySQL，至少需要這幾項：

### 5.1 安裝 Python MySQL driver

先啟用虛擬環境，再裝：

```powershell
.\.venv\Scripts\python.exe -m pip install mysqlclient
```

如果 Windows 上 `mysqlclient` 裝不起來，才考慮 `PyMySQL`。

### 5.2 在 `store/.env` 放連線資訊

可以先規劃成這樣：

```env
MYSQL_DATABASE=store_db
MYSQL_USER=store_user
MYSQL_PASSWORD=your_password_here
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

### 5.3 Django settings 之後要改的方向

目前 [store/settings.py](/c:/dvds/store/store/settings.py) 還是：

- `django.db.backends.sqlite3`

之後切換時會改成類似：

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE", "store_db"),
        "USER": os.getenv("MYSQL_USER", "store_user"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}
```

注意：

- 這是切換方向
- 現在先不要直接改，等資料表規劃與 migration 方案穩定後再動

## 6. 真的切到 MySQL 時的基本流程

當你確定要啟用 MySQL 時，流程通常是：

1. 建好 `store_db`
2. 建好 `store_user`
3. 安裝 `mysqlclient`
4. 修改 `store/.env`
5. 修改 `store/settings.py`
6. 執行 migration

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

7. 啟動 Django

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## 7. 換電腦時怎麼搬資料庫

這要分成兩種情況。

### 7.1 如果新電腦直接連同一台舊資料庫

例如：

- MySQL 還是裝在原本那台主機
- 新電腦只是拿來跑前端 / Django 程式

那你不用搬資料庫內容，只要：

1. 新電腦 clone 專案
2. 安裝 Python / Node / 套件
3. 設定 `store/.env`
4. 把 `MYSQL_HOST` 指到原本那台資料庫主機
5. 確認 MySQL 帳號權限允許遠端連線

這種情況搬的是「程式」，不是「資料庫」。

### 7.2 如果新電腦也要有一份自己的本機 MySQL

這種情況就要做資料庫匯出 / 匯入。

#### 匯出方式 A：用 Workbench

舊電腦：

1. 打開 Workbench
2. 進入 `Server`
3. 選 `Data Export`
4. 勾選 `store_db`
5. 選：
   - `Export to Self-Contained File`
6. 匯出成例如：
   - `store_db_dump.sql`

#### 匯入方式 A：用 Workbench

新電腦：

1. 先安裝 MySQL Server 與 Workbench
2. 建立連線
3. 先建立空白 `store_db`，或讓 dump 自己建
4. 進入 `Server`
5. 選 `Data Import`
6. 選 `Import from Self-Contained File`
7. 指向 `store_db_dump.sql`
8. 選目標 schema
9. 執行匯入

#### 匯出方式 B：用 `mysqldump`

舊電腦：

```powershell
mysqldump -u store_user -p --databases store_db > store_db_dump.sql
```

輸入密碼後會匯出整份 SQL。

#### 匯入方式 B：用 `mysql`

新電腦：

```powershell
mysql -u store_user -p store_db < store_db_dump.sql
```

## 8. 換電腦後讓專案正常開啟

新電腦需要同時完成兩件事：

- 程式 clone 與安裝
- 資料庫可連線

### 8.1 程式端

照 [LOCAL_SETUP.md](/c:/dvds/store/LOCAL_SETUP.md)：

1. clone repo
2. 建立 `.venv`
3. 安裝 `requirements.txt`
4. `frontend` 執行 `npm install`
5. 建立：
   - `store/.env`
   - `frontend/.env.local`

### 8.2 資料庫端

你要確保：

- `store_db` 已存在
- `store_user` 可登入
- `MYSQL_HOST / PORT / USER / PASSWORD / DATABASE` 正確

### 8.3 啟動順序

1. 先確認 MySQL Server 有啟動
2. 再啟動 Django
3. 再啟動 Next.js

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

另開一個終端：

```powershell
cd frontend
npm run dev
```

## 9. 你目前這個專案最建議的做法

以現在專案狀態，我建議：

1. 先把 MySQL 建好
2. 先把這份文件留著
3. 先不要急著把 Django 從 SQLite 切到 MySQL
4. 先把 `models.py` / migration 規劃收斂
5. 再一次做：
   - driver 安裝
   - settings 切換
   - migration
   - JSON 資料搬遷

這樣比較不會變成：

- 資料庫先建了
- 但模型還在改
- migration 一直反覆重來

## 10. 常見問題

### Q1. Workbench 顯示版本警告能不能繼續？

可以。

如果只是：

- 建資料庫
- 跑 SQL
- 看 schema

通常按 `Continue Anyway` 就行。

### Q2. 我只裝 Workbench，沒裝 MySQL Server 可以嗎？

不行。

Workbench 只是管理工具，真正儲存資料的是 MySQL Server。

### Q3. 新電腦 clone 下來就會有資料庫嗎？

不會。

Git 只會帶程式碼與 repo 內的檔案，不會自動帶你本機 MySQL 裡的資料。

如果要帶過去，要嘛：

- 匯出 / 匯入資料庫
- 要嘛新電腦直接連原本那台資料庫主機

### Q4. 現在這個專案能只靠 Workbench 就完成切換嗎？

不能。

還需要：

- Django settings 調整
- Python MySQL driver
- `.env` 設定
- migration 與資料搬遷策略

# MySQL Setup

這份文件只處理「本地 MySQL 環境先建好」這件事。

目前專案還沒有正式切換成 ORM + MySQL 讀寫，所以請把這份文件理解成：

1. 先建立本地可用的 `store_db`
2. 先建立 Django 之後要用的 `store_user`
3. 先確認 Workbench 與帳號能正常連線
4. 先把 `.env` 範本準備好

先不要做的事：

- 不要刪 `data/*.json`
- 不要立刻把 Django `DATABASES` 切到 MySQL
- 不要立刻跑 migration

## 1. 前提

你需要先安裝：

- MySQL Server
- MySQL Workbench

注意：

- Workbench 只是 GUI 工具，不是資料庫本身
- 真正提供資料庫服務的是 MySQL Server

## 2. 建立本地資料庫

在 MySQL Workbench 連進你的本機 MySQL 後，執行：

```sql
CREATE DATABASE store_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

建好後，左側 `SCHEMAS` 應該會看到：

- `store_db`

## 3. 建立 Django 專用帳號

不要讓 Django 長期直接用 root。

在 Workbench 執行：

```sql
CREATE USER 'store_user'@'localhost' IDENTIFIED BY 'your_password_here';
GRANT ALL PRIVILEGES ON store_db.* TO 'store_user'@'localhost';
FLUSH PRIVILEGES;
```

把 `your_password_here` 換成你自己的密碼。

## 4. 確認帳號已建立

可用以下 SQL 檢查：

```sql
SELECT user, host
FROM mysql.user
WHERE user = 'store_user';
```

如果成功，應該會看到：

```text
store_user    localhost
```

也可以再查權限：

```sql
SHOW GRANTS FOR 'store_user'@'localhost';
```

## 5. 在 Workbench 建第二個測試連線

建議另外建立一個「專門模擬 Django 之後會用的帳號」的連線。

設定值：

- `Connection Name`: `store_db_local`
- `Connection Method`: `Standard (TCP/IP)`
- `Hostname`: `127.0.0.1`
- `Port`: `3306`
- `Username`: `store_user`
- `Default Schema`: `store_db`

如果 `Test Connection` 顯示成功，代表這組帳號之後可供 Django 使用。

## 6. Django 之後會用到的本地連線資訊

本地模式下，Django 之後會用：

```env
MYSQL_DATABASE=store_db
MYSQL_USER=store_user
MYSQL_PASSWORD=your_password_here
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

重點：

- `127.0.0.1` 代表資料庫只給「這台電腦上的 Django」使用
- 別台電腦或 Render 不會直接連到這個 `127.0.0.1`

## 7. store/.env.example 要補的欄位

專案裡建議至少準備這些 MySQL 欄位：

```env
MYSQL_DATABASE=store_db
MYSQL_USER=store_user
MYSQL_PASSWORD=
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

## 8. Django 切 MySQL 前的最小修改清單

這一段先規劃，不要現在就執行。

### 8.1 安裝 Python MySQL driver

建議：

```powershell
..\Scripts\python.exe -m pip install mysqlclient
```

如果 Windows 編譯有問題，再考慮 `PyMySQL`。

### 8.2 修改 `store/settings.py`

目前專案還在用 SQLite：

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
```

之後切換時，預計會改成：

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

### 8.3 第一波 migration 不要一次全上

建議先落地核心表：

- `users`
- `categories`
- `products`
- `product_variants`
- `orders`
- `order_items`
- `payment_transactions`
- `payment_callback_logs`

## 9. 如果之後要換電腦

如果你走的是「每台電腦各自本機 MySQL」：

1. 新電腦安裝 MySQL Server
2. 建 `store_db`
3. 建 `store_user`
4. 設定對應 `.env`
5. 之後再視需要匯入 seed 或 dump

這種模式最穩，但資料不會自動同步。

## 10. 如果之後要搬資料

完整 MySQL dump 不建議常態 push 到 git。

比較好的分法：

- git 內：
  - schema
  - migration
  - 小型 seed / fixture
  - setup 文件

- git 外：
  - 完整 `.sql` dump
  - 真實測試資料
  - 大量動態內容

## 11. 目前階段結論

你現在可以做的是：

1. 建好 `store_db`
2. 建好 `store_user`
3. 確認 Workbench 能連
4. 準備好 `.env` 範本

你現在不要做的是：

1. 刪 JSON
2. 強行切 Django 到 MySQL
3. 直接跑正式 migration

先把本地 MySQL 環境準備好，再進下一步最穩。

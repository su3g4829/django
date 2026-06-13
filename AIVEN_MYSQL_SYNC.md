# Aiven MySQL 同步流程

這份文件整理兩個方向：

1. 本地 MySQL 上傳到 Aiven MySQL
2. Aiven MySQL 下載回本地 MySQL

適用環境以 Windows + PowerShell 為主。

## 先決條件

- 本機已安裝 MySQL Client，至少有 `mysqldump.exe` 與 `mysql.exe`
- 已取得 Aiven MySQL 連線資訊：
  - Host
  - Port
  - Database name
  - User
  - Password
- 已下載 Aiven CA certificate，例如：
  - `C:\secrets\aiven-ca.pem`

## Windows PowerShell 重要注意

先把 MySQL `bin` 加到目前 PowerShell 視窗的 `PATH`：

```powershell
$env:Path += ";C:\Program Files\MySQL\MySQL Server 8.0\bin"
```

確認可用：

```powershell
mysqldump --version
mysql --version
```

重點：

- 匯出 dump 時，不要在 PowerShell 直接用 `mysqldump ... > file.sql`
- PowerShell 的 `>` 可能把檔案存成 UTF-16
- MySQL 匯入 UTF-16 dump 時，常見錯誤是：
  - `ERROR 1064 (42000) at line 1`
- Windows 下建議改用 `cmd /c "mysqldump ... > file.sql"`
- 不要混用 bash 風格的 `\"`
- 不要用單引號包整串 `cmd /c` 命令

## 一. 本地 MySQL 上傳到 Aiven MySQL

### Step 1. 匯出本地 dump

以下示範把本地 `store_db` 匯出成 `C:\Users\User\local_dump.sql`：

```powershell
cmd /c "mysqldump --default-character-set=utf8mb4 --single-transaction --set-gtid-purged=OFF -u root -p store_db > C:\Users\User\local_dump.sql"
```

執行後會要求你輸入本地 MySQL `root` 密碼。

### Step 2. 確認 Aiven 服務有啟動

在 Aiven 後台確認：

- `Service status` 不是 `Powered off`
- Host / Port / User / Database name 都正確

如果 Aiven 是 `Powered off`，通常會出現：

- `Got error: 2005: Unknown MySQL server host ...`

### Step 3. 把本地 dump 匯入 Aiven

PowerShell 不能直接用 `<` 做這類匯入，所以改用 `cmd /c`：

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 -h YOUR_AIVEN_HOST -P YOUR_AIVEN_PORT -u YOUR_AIVEN_USER -p --ssl-ca=C:\secrets\aiven-ca.pem YOUR_AIVEN_DB < C:\Users\User\local_dump.sql"
```

如果你的 Aiven 需要更嚴格的 SSL 驗證，可改成：

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 -h YOUR_AIVEN_HOST -P YOUR_AIVEN_PORT -u YOUR_AIVEN_USER -p --ssl-mode=VERIFY_CA --ssl-ca=C:\secrets\aiven-ca.pem YOUR_AIVEN_DB < C:\Users\User\local_dump.sql"
```

### Step 4. 驗證 Aiven 是否匯入成功

```powershell
mysql -h YOUR_AIVEN_HOST -P YOUR_AIVEN_PORT -u YOUR_AIVEN_USER -p --ssl-ca="C:\secrets\aiven-ca.pem" -D YOUR_AIVEN_DB -e "SHOW TABLES;"
```

也可以直接檢查筆數：

```powershell
mysql -h YOUR_AIVEN_HOST -P YOUR_AIVEN_PORT -u YOUR_AIVEN_USER -p --ssl-ca="C:\secrets\aiven-ca.pem" -D YOUR_AIVEN_DB -e "SELECT COUNT(*) AS products_count FROM products;"
```

## 二. Aiven MySQL 下載回本地 MySQL

### Step 1. 從 Aiven 匯出 dump

```powershell
cmd /c "mysqldump --default-character-set=utf8mb4 --single-transaction --set-gtid-purged=OFF -h YOUR_AIVEN_HOST -P YOUR_AIVEN_PORT -u YOUR_AIVEN_USER -p --ssl-ca=C:\secrets\aiven-ca.pem YOUR_AIVEN_DB > C:\Users\User\aiven_dump.sql"
```

### Step 2. 先備份本地資料庫

```powershell
cmd /c "mysqldump --default-character-set=utf8mb4 --single-transaction --set-gtid-purged=OFF -u root -p store_db > C:\Users\User\store_db_backup_before_restore.sql"
```

### Step 3. 建立匯入用資料庫

建議不要直接覆蓋現有本地資料庫，可以先建立一個新資料庫，例如 `store_db_aiven`：

```powershell
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS store_db_aiven CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### Step 4. 匯入 Aiven dump 到本地

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 -u root -p store_db_aiven < C:\Users\User\aiven_dump.sql"
```

### Step 5. 驗證本地匯入結果

```powershell
mysql -u root -p -D store_db_aiven -e "SHOW TABLES;"
```

檢查主要資料表筆數：

```powershell
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS users_count FROM users;"
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS products_count FROM products;"
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS orders_count FROM orders;"
```

如果 Django 要改讀這份本地資料庫，`store/.env` 可以設成：

```env
STORE_DB_BACKEND=mysql
MYSQL_DATABASE=store_db_aiven
MYSQL_USER=store_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

然後可用 ORM 快速驗證：

```powershell
..\Scripts\python.exe manage.py shell -c "from myapp.models import AppUser, Product, Order, Banner; print('users=', AppUser.objects.count(), 'products=', Product.objects.count(), 'orders=', Order.objects.count(), 'banners=', Banner.objects.count())"
```

## 三. 常見錯誤

### 1. `mysqldump : 無法辨識 ...`

原因：

- MySQL Client 沒安裝
- `mysqldump.exe` 不在 `PATH`

處理：

```powershell
$env:Path += ";C:\Program Files\MySQL\MySQL Server 8.0\bin"
mysqldump --version
mysql --version
```

### 2. `Got error: 2005: Unknown MySQL server host`

原因：

- Host 打錯
- DNS 暫時解析不到
- Aiven 服務處於 `Powered off`

處理：

- 重新核對 Aiven Host
- 確認服務狀態是 `Running`

### 3. `Got error: 2026: SSL connection error`

原因：

- `--ssl-ca` 路徑錯誤
- CA certificate 內容或檔案不對

處理：

```powershell
--ssl-ca="C:\secrets\aiven-ca.pem"
```

### 4. PowerShell 出現 `'<' 運算子保留供未來使用`

原因：

- PowerShell 不支援像 `cmd` 那樣直接用 `< file.sql`

處理：

```powershell
cmd /c "mysql ... < C:\Users\User\aiven_dump.sql"
```

### 5. `ASCII '\0' appeared in the statement`

原因：

- SQL dump 內含 binary 內容
- 匯入時沒加 `--binary-mode=1`

處理：

```powershell
cmd /c "mysql --binary-mode=1 -u root -p store_db_aiven < C:\Users\User\aiven_dump.sql"
```

### 6. `ERROR 1064 (42000) at line 1`

最常見原因：

- dump 檔案被 PowerShell `>` 存成 UTF-16
- 檔案編碼被破壞

判斷方式：

- 用十六進位看檔頭，如果開頭是 `FF FE`，通常就是 UTF-16

處理：

- 不要直接在 PowerShell 用 `mysqldump ... > file.sql`
- 重新用 `cmd /c "mysqldump ... > file.sql"` 匯出
- 匯出時保留：

```powershell
--default-character-set=utf8mb4
```

### 7. 匯入後中文亂碼

原因通常是：

1. 匯出不是 `utf8mb4`
2. 匯入 client 編碼不一致
3. 目標資料庫不是 `utf8mb4`

處理：

- 匯出與匯入都使用 `--default-character-set=utf8mb4`
- 目標資料庫建立時指定：

```powershell
mysql -u root -p -e "CREATE DATABASE store_db_aiven CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

## 四. 建議順序

如果你的目標是把本地修正後的資料同步到雲端：

1. 本地先確認資料正確
2. 備份本地資料庫
3. 匯出本地 dump
4. 匯入 Aiven
5. 驗證 Aiven 資料是否正確
6. 再進行 Django / Render 部署

如果你的目標是把線上資料拉回本地：

1. 從 Aiven 匯出 dump
2. 備份本地資料庫
3. 匯入新資料庫
4. 驗證後再切 Django 連線

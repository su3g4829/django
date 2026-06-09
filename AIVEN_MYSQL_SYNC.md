# Aiven MySQL 同步流程

這份文件整理兩個完整方向：

1. 本地 MySQL 上傳到 Aiven MySQL
2. Aiven MySQL 下載回本地 MySQL

適用環境以 Windows + PowerShell 為主，並補上你前面遇到的常見錯誤。

## 使用前提

- 本機已安裝 MySQL Client 工具，至少要有 `mysqldump` 與 `mysql`
- 已取得 Aiven MySQL 的連線資訊
  - Host
  - Port
  - Database name
  - User
  - Password
- 已從 Aiven 下載 CA certificate，並存成實體檔案，例如：
  - `C:\secrets\aiven-ca.pem`

## 先確認工具可用

在 PowerShell 執行：

```powershell
Get-Command mysqldump
Get-Command mysql
```

如果找不到，代表 MySQL Client 沒裝好，或 MySQL 的 `bin` 目錄沒有加到 PATH。

常見安裝路徑：

```text
C:\Program Files\MySQL\MySQL Server 8.0\bin
```

如果你不想改 PATH，也可以直接用完整路徑：

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" --version
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" --version
```

## 重要原則

- 匯入前先備份
- 正式同步時，盡量讓來源與目標都用 `utf8mb4`
- 不要把 `.sql` dump、`.pem` 憑證、密碼寫進 Git
- 如果你要做的是「完整同步」，目標資料庫最好先清空或重建，避免舊資料殘留

---

## 一、本地 MySQL 上傳到 Aiven MySQL

### Step 1：先從本地匯出 SQL dump

以下示範把本地 `store_db` 匯出成 `local_dump.sql`：

```powershell
mysqldump `
  --default-character-set=utf8mb4 `
  --single-transaction `
  --set-gtid-purged=OFF `
  -u root `
  -p `
  store_db > C:\Users\User\local_dump.sql
```

如果 `mysqldump` 不在 PATH，改用完整路徑：

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" `
  --default-character-set=utf8mb4 `
  --single-transaction `
  --set-gtid-purged=OFF `
  -u root `
  -p `
  store_db > C:\Users\User\local_dump.sql
```

### Step 2：確認 Aiven 服務是可連線狀態

到 Aiven 後台確認：

- `Service status` 不是 `Powered off`
- Host / Port / User / Database name 正確

如果 Aiven 是 `Powered off`，你即使用正確 host 也可能連不上。

### Step 3：把 dump 匯入 Aiven

PowerShell 不能直接用 `<` 做這種 MySQL 匯入，所以請改用 `cmd /c`。

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 ^
  -h YOUR_AIVEN_HOST ^
  -P YOUR_AIVEN_PORT ^
  -u YOUR_AIVEN_USER ^
  -p ^
  --ssl-ca=C:\secrets\aiven-ca.pem ^
  YOUR_AIVEN_DB < C:\Users\User\local_dump.sql"
```

實際範例格式：

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 ^
  -h mysql-xxxx.aivencloud.com ^
  -P 24254 ^
  -u avnadmin ^
  -p ^
  --ssl-ca=C:\secrets\aiven-ca.pem ^
  defaultdb < C:\Users\User\local_dump.sql"
```

### Step 4：驗證 Aiven 是否真的有資料

```powershell
mysql `
  -h YOUR_AIVEN_HOST `
  -P YOUR_AIVEN_PORT `
  -u YOUR_AIVEN_USER `
  -p `
  --ssl-ca="C:\secrets\aiven-ca.pem" `
  -D YOUR_AIVEN_DB `
  -e "SHOW TABLES;"
```

再查幾個關鍵表：

```powershell
mysql `
  -h YOUR_AIVEN_HOST `
  -P YOUR_AIVEN_PORT `
  -u YOUR_AIVEN_USER `
  -p `
  --ssl-ca="C:\secrets\aiven-ca.pem" `
  -D YOUR_AIVEN_DB `
  -e "SELECT COUNT(*) AS products_count FROM products;"
```

---

## 二、Aiven MySQL 下載回本地 MySQL

### Step 1：先從 Aiven 匯出 dump

```powershell
mysqldump `
  --default-character-set=utf8mb4 `
  --single-transaction `
  --set-gtid-purged=OFF `
  -h YOUR_AIVEN_HOST `
  -P YOUR_AIVEN_PORT `
  -u YOUR_AIVEN_USER `
  -p `
  --ssl-ca="C:\secrets\aiven-ca.pem" `
  YOUR_AIVEN_DB > C:\Users\User\aiven_dump.sql
```

如果你的 MySQL Client 對 `--ssl-mode=VERIFY_CA` 有相容性問題，可以先只用 `--ssl-ca`。

### Step 2：先備份本地資料庫

不要直接覆蓋現有本地資料庫，先備份：

```powershell
mysqldump `
  --default-character-set=utf8mb4 `
  --single-transaction `
  --set-gtid-purged=OFF `
  -u root `
  -p `
  store_db > C:\Users\User\store_db_backup_before_restore.sql
```

### Step 3：建立同步用資料庫，或清空原本資料庫

比較安全的做法是先匯入到另一個資料庫，例如：

```powershell
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS store_db_aiven CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

如果你確定要直接覆蓋原本本地資料庫，先自行確認沒有要保留的舊資料。

### Step 4：把 Aiven dump 匯入本地

```powershell
cmd /c "mysql --default-character-set=utf8mb4 --binary-mode=1 -u root -p store_db_aiven < C:\Users\User\aiven_dump.sql"
```

### Step 5：驗證匯入結果

先看表有沒有進來：

```powershell
mysql -u root -p -D store_db_aiven -e "SHOW TABLES;"
```

再看幾個重點筆數：

```powershell
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS users_count FROM users;"
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS products_count FROM products;"
mysql -u root -p -D store_db_aiven -e "SELECT COUNT(*) AS orders_count FROM orders;"
```

如果你要驗證 Django 是否有成功連到同步後的資料庫，改好 `store/.env` 後可執行：

```powershell
..\Scripts\python.exe manage.py shell -c "from myapp.models import AppUser, Product, Order, Banner; print('users=', AppUser.objects.count(), 'products=', Product.objects.count(), 'orders=', Order.objects.count(), 'banners=', Banner.objects.count())"
```

---

## 三、把同步後的本地資料庫接回 Django

`store/.env` 應該指向你要使用的本地資料庫，例如：

```env
STORE_DB_BACKEND=mysql
MYSQL_DATABASE=store_db_aiven
MYSQL_USER=store_user
MYSQL_PASSWORD=your_password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

修改後重新啟動 Django：

```powershell
..\Scripts\python.exe manage.py runserver
```

---

## 四、常見錯誤與處理方式

### 1. `mysqldump : 無法辨識...`

原因：

- MySQL Client 沒安裝
- `mysqldump.exe` 不在 PATH

處理：

- 安裝 MySQL Server 或 MySQL Shell / Client
- 或直接用完整路徑執行 `mysqldump.exe`

### 2. `Got error: 2005: Unknown MySQL server host`

原因：

- Host 打錯
- DNS 還沒解析到
- Aiven 服務已關閉

處理：

- 重新比對 Aiven 的 Host
- 確認不是多打空白或少字
- 到 Aiven 後台確認 `Service status` 不是 `Powered off`

### 3. `Got error: 2026: SSL connection error`

原因：

- `--ssl-ca` 指到不存在的路徑
- 你把 `C:\path\to\ca.pem` 當成真的路徑，卻沒有換成自己的檔案
- 憑證檔內容不完整

處理：

- 先從 Aiven 下載 CA certificate
- 存成實體檔，例如 `C:\secrets\aiven-ca.pem`
- 指令改成：

```powershell
--ssl-ca="C:\secrets\aiven-ca.pem"
```

注意：

- `C:\path\to\ca.pem` 只是範例字串，不是把憑證內容直接貼進指令

### 4. PowerShell 出現 `'<' 運算子保留供未來使用`

原因：

- PowerShell 不支援像 cmd 那樣的 `< file.sql` 匯入語法

處理：

- 改用：

```powershell
cmd /c "mysql ... < C:\Users\User\aiven_dump.sql"
```

### 5. `ASCII '\0' appeared in the statement`

原因：

- 匯入的 SQL 內含 binary 資料
- `mysql` 匯入時沒有開 `--binary-mode=1`

處理：

```powershell
cmd /c "mysql --binary-mode=1 -u root -p store_db_aiven < C:\Users\User\aiven_dump.sql"
```

### 6. `ERROR 1064 ... near '?-' at line 1`

原因：

- dump 檔案編碼被破壞
- 檔案開啟後又另存成錯誤編碼
- 原本匯出時就不是用 `utf8mb4`

處理：

- 重新從來源資料庫匯出
- 匯出時強制加上：

```powershell
--default-character-set=utf8mb4
```

- 不要用記事本亂開再另存

### 7. 中文內容變亂碼

原因通常有兩種：

1. 匯出時就已經錯
2. 匯入時 client 編碼不一致

建議做法：

- 匯出與匯入都明確指定 `utf8mb4`
- 本地資料庫建立時也用 `utf8mb4`

例如：

```powershell
mysql -u root -p -e "CREATE DATABASE store_db_aiven CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

---

## 五、建議的安全同步順序

如果你要做正式同步，建議固定照這個順序：

1. 先備份來源資料庫
2. 先備份目標資料庫
3. 匯出來源 dump
4. 在測試用資料庫先匯入驗證
5. 檢查表數、筆數、中文內容、圖片路徑
6. 確定沒問題後，再覆蓋正式目標資料庫
7. 最後用 Django 查 ORM 筆數做驗證

---

## 六、這個專案的實務建議

對你這個 Django 專案，目前比較合理的用法是：

- 正式遠端資料：Aiven MySQL
- 本地開發資料：本地 MySQL
- 需要同步測試資料時：
  - 從 Aiven dump 下來
  - 匯入本地測試庫
  - 修改 `store/.env` 指向該本地測試庫

不要把同步流程做成：

- 平常直接讓本地 Django 連正式 Aiven 當主要開發庫

這樣風險太高，容易把測試資料寫進正式資料庫。

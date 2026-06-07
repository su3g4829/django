# DB Migration Plan

這份文件是給目前這個專案從 **JSON prototype** 過渡到 **Django ORM + MySQL** 的執行順序規劃。

這份文件只做規劃，不代表現在就應該執行：

- 不代表現在要刪 `data/*.json`
- 不代表現在要直接改 `DATABASES`
- 不代表現在要一次把全部 service 改成 ORM

目標是先把最重要、最不容易出錯的主線整理出來：

1. 第一波 migration 先建哪些表
2. 哪幾支 service 先從 JSON 改讀 ORM
3. 哪些功能要延後，不要一開始全碰

## 1. 現況判斷

目前專案狀態：

- API / service / frontend 已經有完整主流程
- 主要持久化來源仍是 `data/*.json`
- `models.py` 已經收斂到「可以作為正式 DB 草案」的程度
- 但 runtime 還沒有切到 ORM

所以過渡策略要遵守：

- 先建核心表
- 先切核心交易流程
- 次要體驗型資料後補

## 2. 第一波 migration 的目標

第一波只做「最小可交易核心」。

換句話說，要能支撐：

1. 使用者
2. 分類
3. 商品
4. 訂單
5. 金流記錄

第一波做完，不要求：

- 收藏
- 比較
- 最近瀏覽
- 社群
- Banner
- 比價
- 推薦

這些都可以留到第二波或第三波。

## 3. 第一波建表清單

### 3.1 使用者與基礎設定

先建：

- `users`
- `user_addresses`
- `user_invoice_profiles`
- `user_shipping_rules`
- `seller_requests`

原因：

- checkout / order / seller center 都依賴這些資料
- 地址、發票、運費規則是訂單 snapshot 的上游

### 3.2 商品主資料

先建：

- `brands`
- `categories`
- `products`
- `product_images`
- `product_variants`
- `tags`
- `product_tag_relations`

原因：

- 商品總覽
- 商品頁
- 賣家新增商品
- 分類主表
- 變體與庫存

都靠這批表。

### 3.3 訂單與履約

先建：

- `orders`
- `order_items`
- `order_service_requests`
- `shipment_events`

原因：

- 訂單流程本身是主線
- 目前買家 / 賣家 / 管理端訂單都已存在
- 這批表是從 JSON 切 DB 時最有價值的一段

### 3.4 金流

先建：

- `payment_transactions`
- `payment_callback_logs`

原因：

- 這批資料不只影響功能，也影響除錯
- 付款流程若沒有完整 transaction / callback log，很快就會失控

## 4. 第一波先不要建或先不要切的區塊

以下可以先保留 schema，但不要當成第一波 runtime 切換目標：

- `carts`
- `cart_items`
- `user_favorites`
- `compare_items`
- `recent_views`
- `product_reviews`
- `product_questions`
- `product_question_answers`
- `community_posts`
- `community_replies`
- `community_votes`
- `banners`
- `media_assets`
- `admin_audit_logs`
- `competitor_sites`
- `competitor_products`
- `product_recommendations`

原因不是它們不重要，而是：

- 這些功能不會阻塞你先跑通主交易流程
- 先切它們只會把 migration 範圍放大
- 容易在第一波就把 JSON / session / ORM 混得更亂

## 5. Service 切換順序

### Phase A：基礎使用者與商品

先改這幾支：

1. `myapp/services/auth_demo.py`
2. `myapp/services/customer_center.py`
3. `myapp/services/product_management.py`

原因：

- 使用者和商品是所有流程的地基
- 不先切這三支，後面的訂單和金流切 DB 只會更痛

切法建議：

- 先保留原介面
- 讓 service 內部從 `local_store.py` 改讀 ORM repository
- 不要一開始改 API contract

### Phase B：訂單與交易主線

第二批改：

1. `myapp/services/orders.py`
2. `myapp/services/newebpay_payment_real.py`

原因：

- 訂單與付款交易要建立在已 ORM 化的使用者 / 商品之上
- 這時才有意義把 `orders`、`order_items`、`payment_transactions` 接上 DB

切法建議：

- 先讓 `create_order_from_cart()` 落 DB
- 再讓訂單查詢改讀 DB
- 再讓支付記錄與 callback log 改讀寫 DB

### Phase C：購物車與個人化

第三批再改：

1. `myapp/services/cart.py`
2. `myapp/services/personalization.py`

原因：

- 這兩支有 session / guest bucket / user bucket 混合邏輯
- 不適合在第一波就一併切

### Phase D：內容與營運

最後再改：

1. `myapp/services/reviews.py`
2. `myapp/services/questions.py`
3. `myapp/services/community.py`
4. `myapp/services/banner.py`
5. `myapp/services/recommendations.py`
6. `myapp/services/price_compare.py`

## 6. 建議的實際順序

最實際的執行順序建議如下：

1. 收斂 `models.py`
2. 確認 MySQL 可連
3. 安裝 MySQL driver
4. 改 `store/settings.py` 支援 MySQL（先不啟用）
5. 建第一波 migration
6. 在本機 MySQL 跑 migration
7. 建最小 seed 資料
8. 先改 `auth_demo.py` / `customer_center.py` / `product_management.py`
9. 確認商品與會員流程正常
10. 再改 `orders.py` / `newebpay_payment_real.py`
11. 確認訂單與金流記錄改走 DB
12. 最後才考慮購物車、收藏、比較、社群

## 7. 第一波最小 seed 資料

即使你不搬 JSON，第一波也至少要準備：

### 使用者

- 1 個 admin
- 1 個 seller
- 1 個 buyer

### 分類

- `tops`
- `pants`

### 品牌

- 1~2 筆測試品牌

### 商品

- 3~5 筆測試商品
- 至少 1 筆有 variant
- 至少 1 筆無 variant

### 會員附屬資料

- seller 的 shipping rules
- buyer 的 address
- buyer 的 invoice profile

這樣才足夠驗：

- 商品總覽
- 商品詳情
- checkout
- 建單
- 賣家訂單頁

## 8. 風險點

### 8.1 不要太早刪 JSON

在 service 還沒切 ORM 前，刪掉 `data/*.json` 只會讓系統直接壞掉。

### 8.2 不要一次切全部 service

這個專案現在的風險不是 schema，而是：

- API、service、session、JSON 已經互相有很多依賴

所以一定要分波次。

### 8.3 金流資料一定要保留 log

`payment_transactions` 和 `payment_callback_logs` 不要省掉。

哪怕 NewebPay 還沒完全穩，這兩張表仍然應該是第一波。

### 8.4 先接受「功能暫時雙軌」

過渡期很可能出現：

- 一部分功能還讀 JSON
- 一部分功能已經讀 DB

這是正常的，但要有明確切換順序，不要同一功能雙寫太久。

## 9. 現階段最建議的下一步

如果你現在要進下一步，我建議順序是：

1. 先不要動 migration
2. 先把 `store/settings.py` 改成「支援 MySQL 但先不啟用」
3. 再盤點第一波 migration 實際要包含哪些 model
4. 再決定 seed 資料要怎麼建立

## 10. 結論

現在最穩的切法不是「先把所有表建完」，而是：

- **先建最小可交易核心**
- **先切使用者 / 商品 / 訂單 / 金流**
- **其他功能延後**

只要這條主線先穩下來，後面的收藏、社群、推薦、比價都只是擴充，不會卡死整個專案。

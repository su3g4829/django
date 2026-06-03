# DATABASE_SCHEMA_DRAFT

本文件是目前專案從 `data/*.json` 遷移到正式資料庫的草稿基準。

目標不是照 JSON 原封不動落表，而是：

1. 保留目前已存在的業務流程
2. 把 session / snapshot / 匿名規則一起納入設計
3. 讓後續 Django ORM migration 有明確落地順序

## 1. 設計原則

### 1.1 以 `user_id` 當內部關聯主鍵

目前 JSON 很多地方同時存：

- `author`
- `author_username`
- `author_user_id`

正式資料庫應以：

- `users.id`

作為唯一內部關聯，其他顯示名稱只作 snapshot 或快取用途。

### 1.2 訂單、訂單明細、內容資料保留 snapshot

下列資料在交易完成後不能只靠即時關聯回推：

- 訂單上的買家名稱、email、地址、發票資料
- 訂單明細上的商品名稱、variant 名稱、SKU、單價
- 評論 / 問答 / 社群發文當下的顯示名稱

原因：

- 商品會改名
- 使用者會改 display name
- 賣家可能停權或刪檔

所以資料表應同時保留：

- `ForeignKey`
- 必要 snapshot 欄位

### 1.3 匿名是讀取規則，不是儲存規則

目前公開頁面會把：

- 評論作者
- 問答作者
- 社群作者

做匿名化。

正式資料庫建議：

- 內部存 `author_user_id`
- 視需要保留 `author_display_name_snapshot`
- 對外匿名在 service / serializer 層處理

### 1.4 session 資料要明確決策

目前以下功能還在 signed-cookie session：

- cart
- favorites
- compare
- recent views

開始建 DB 前要先決定：

- 這些是否改成資料庫持久化
- 或仍維持 session / Redis 型暫存

本草稿提供兩種都可行的表結構，但不代表一定全部都要建。

## 2. 目前 JSON 對應的未來實體

| 現有 JSON / 狀態 | 未來實體 |
| --- | --- |
| `users.json` | `users`, `user_addresses`, `user_invoice_profiles`, `user_shipping_rules`, `seller_requests` |
| `products.json` | `products`, `product_images`, `product_variants`, `brands`, `categories`, `product_tags` |
| `orders.json` | `orders`, `order_items`, `order_service_requests`, `shipment_events` |
| `reviews.json` | `product_reviews` |
| `questions.json` | `product_questions`, `product_question_answers` |
| `posts.json` | `community_posts`, `community_replies`, `community_votes` |
| `banners.json` | `banners`, `banner_applications` |
| `competitor_prices.json` | `competitor_sites`, `competitor_products` |
| `newebpay_payment_logs.json` | `payment_transactions`, `payment_callback_logs` |
| session cart | `carts`, `cart_items` 或 server-side session |
| session favorites / compare / recent | `user_favorites`, `compare_items`, `recent_views` 或 server-side session |

## 3. 核心帳號與會員資料

### 3.1 `users`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `username` | `CharField(unique=True)` | 登入帳號 |
| `password_hash` | `CharField` | Django password hash |
| `display_name` | `CharField` | 顯示名稱 |
| `email` | `EmailField(blank=True)` | email |
| `role` | `CharField` | `member` / `seller` / `admin` |
| `account_status` | `CharField` | `active` / `suspended` |
| `seller_request_status` | `CharField(blank=True)` | 保留在 `users` 做目前狀態快取；真正的申請歷程與審核記錄仍以 `seller_requests` 為主 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `last_login_at` | `DateTimeField(null=True)` | 最後登入時間 |
| `seller_requested_at` | `DateTimeField(null=True)` | 目前 JSON 已有，正式化後可改由 `seller_requests.created_at` 取代 |
| `seller_reviewed_at` | `DateTimeField(null=True)` | 同上 |
| `account_status_updated_at` | `DateTimeField(null=True)` | 帳號狀態最後更新時間 |

### 3.2 `user_addresses`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 所屬會員 |
| `label` | `CharField` | 地址標籤 |
| `recipient` | `CharField` | 收件人 |
| `phone` | `CharField` | 電話 |
| `postal_code` | `CharField(blank=True)` | 郵遞區號 |
| `city` | `CharField` | 縣市 |
| `district` | `CharField` | 區域 |
| `address_line` | `CharField` | 詳細地址 |
| `is_default` | `BooleanField(default=False)` | 是否預設 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

建議 constraint：

- `UniqueConstraint(fields=["user"], condition=Q(is_default=True), name="unique_default_address_per_user")`

### 3.3 `user_invoice_profiles`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `OneToOneField(users)` | 所屬會員 |
| `invoice_type` | `CharField` | `personal` / `company` |
| `carrier_code` | `CharField(blank=True)` | 載具碼 |
| `company_name` | `CharField(blank=True)` | 公司名稱 |
| `tax_id` | `CharField(blank=True)` | 統編 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 3.4 `user_shipping_rules`

目前每個會員 JSON 都帶 seller shipping rules。正式 DB 建議拆表。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `OneToOneField(users)` | 所屬賣家 |
| `home_delivery_enabled` | `BooleanField(default=True)` | 是否開啟宅配 |
| `home_delivery_fee` | `DecimalField(max_digits=10, decimal_places=2)` | 宅配運費 |
| `convenience_store_enabled` | `BooleanField(default=True)` | 是否開啟超商取貨 |
| `convenience_store_fee` | `DecimalField(max_digits=10, decimal_places=2)` | 超商運費 |
| `free_shipping_threshold` | `DecimalField(max_digits=10, decimal_places=2)` | 免運門檻 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 3.5 `seller_requests`

建議保留成獨立歷史表，不只存在 `users` 上。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 申請者 |
| `is_current` | `BooleanField(default=True)` | 是否為這位會員目前生效中的最新申請紀錄 |
| `status` | `CharField` | `pending` / `approved` / `rejected` |
| `note` | `TextField(blank=True)` | 審核備註 |
| `created_at` | `DateTimeField` | 申請時間 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |
| `reviewed_by` | `ForeignKey(users, null=True, related_name="+")` | 審核人 |

建議 constraint：
- MySQL 若不支援條件式唯一約束，先由 service 確保同一個 user 只有一筆 `is_current=True`

## 4. 商品與目錄

### 4.1 `brands`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `slug` | `SlugField(unique=True)` | 品牌 slug |
| `name` | `CharField(unique=True)` | 品牌名稱 |
| `description` | `TextField(blank=True)` | 品牌說明 |
| `logo_path` | `CharField(blank=True)` | logo 路徑 |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 4.2 `categories`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `parent` | `ForeignKey("self", null=True, blank=True)` | 父分類 |
| `slug` | `SlugField(unique=True)` | 分類 slug |
| `name` | `CharField` | 分類名稱 |
| `description` | `TextField(blank=True)` | 說明 |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 4.3 `products`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `owner` | `ForeignKey(users)` | 商品擁有者 / 賣家 |
| `slug` | `SlugField(unique=True)` | 商品 slug |
| `name` | `CharField` | 商品名稱 |
| `brand` | `ForeignKey(brands, null=True, blank=True)` | 品牌 |
| `category` | `ForeignKey(categories, null=True, blank=True)` | 分類 |
| `price` | `DecimalField(max_digits=10, decimal_places=2)` | 主售價 |
| `compare_at_price` | `DecimalField(max_digits=10, decimal_places=2, null=True)` | 原價 / 劃線價 |
| `stock` | `IntegerField(null=True)` | 單一 SKU 商品可直接使用 |
| `specs_json` | `JSONField(default=dict)` | 規格摘要 |
| `status` | `CharField` | `draft` / `pending` / `active` / `rejected` / `archived` |
| `review_note` | `TextField(blank=True)` | 審核備註 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |
| `owner_username_snapshot` | `CharField` | 賣家 username snapshot |
| `owner_display_name_snapshot` | `CharField` | 賣家 display_name snapshot |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 4.4 `product_images`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `image_path` | `CharField` | 圖片路徑 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |

### 4.5 `product_variants`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `external_variant_id` | `CharField(blank=True)` | 現有 JSON `id` 仍可保留作外部 key |
| `name` | `CharField` | variant 名稱 |
| `sku` | `CharField(blank=True, db_index=True)` | SKU；先允許空白，避免舊資料或單純規格商品在匯入時被唯一限制卡住 |
| `price` | `DecimalField(max_digits=10, decimal_places=2)` | variant 售價 |
| `compare_at_price` | `DecimalField(max_digits=10, decimal_places=2, null=True)` | variant 原價 |
| `stock` | `IntegerField` | variant 庫存 |
| `attributes_json` | `JSONField(default=dict)` | size / color 等屬性 |
| `image_index` | `PositiveIntegerField(null=True)` | 對應圖片 index |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 4.6 `tags` / `product_tag_relations`

`products.tags` 與 `posts.tags` 都可逐步正規化。

`tags`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `slug` | `SlugField(unique=True)` | tag slug |
| `name` | `CharField(unique=True)` | tag 名稱 |
| `created_at` | `DateTimeField` | 建立時間 |

`product_tag_relations`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 商品 |
| `tag` | `ForeignKey(tags)` | tag |

建議 constraint：

- `UniqueConstraint(fields=["product", "tag"])`

## 5. 購物車與個人化

這一區必須先決策是否入 DB。

### 選項 A：保留 session / Redis

適合：

- prototype
- 不要求跨裝置同步

不需要建立以下資料表。

### 選項 B：改成資料庫持久化

適合：

- 跨裝置購物車同步
- 收藏 / 最近瀏覽持久化
- 降低 signed-cookie session 負擔

### 5.1 `carts`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `OneToOneField(users)` | 所屬會員 |
| `coupon_code` | `CharField(blank=True)` | 折扣碼 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 5.2 `cart_items`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `cart` | `ForeignKey(carts)` | 所屬購物車 |
| `product` | `ForeignKey(products)` | 商品 |
| `product_variant` | `ForeignKey(product_variants, null=True)` | variant |
| `item_key` | `CharField` | 對應目前 cart service 的唯一鍵，例如 `slug` 或 `slug__variant-id` |
| `quantity` | `PositiveIntegerField` | 數量 |
| `unit_price_snapshot` | `DecimalField(max_digits=10, decimal_places=2)` | 加入當下價格 |
| `product_name_snapshot` | `CharField` | 商品名稱 snapshot |
| `variant_name_snapshot` | `CharField(blank=True)` | variant 名稱 snapshot |
| `sku_snapshot` | `CharField(blank=True)` | SKU snapshot |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

建議 constraint：
- `UniqueConstraint(fields=["cart", "item_key"])`

### 5.3 `user_favorites`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 所屬會員 |
| `product` | `ForeignKey(products)` | 收藏商品 |
| `created_at` | `DateTimeField` | 建立時間 |

建議 constraint：

- `UniqueConstraint(fields=["user", "product"])`

### 5.4 `compare_items`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 所屬會員 |
| `session_key` | `CharField(blank=True)` | 訪客模式下對應的 session bucket |
| `bucket_key` | `CharField` | 穩定的 owner key，例如 `user:123` 或 `session:abcxyz` |
| `product` | `ForeignKey(products)` | 比較商品 |
| `created_at` | `DateTimeField` | 建立時間 |

建議 constraint：
- `UniqueConstraint(fields=["bucket_key", "product"])`

### 5.5 `recent_views`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 所屬會員 |
| `product` | `ForeignKey(products)` | 最近瀏覽商品 |
| `viewed_at` | `DateTimeField` | 瀏覽時間 |

## 6. 訂單、出貨、售後

### 6.1 `orders`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `buyer` | `ForeignKey(users)` | 買家 |
| `status` | `CharField` | `confirmed` / `cancelled` / `refunded` |
| `shipping_method` | `CharField` | `home_delivery` / `convenience_store` |
| `payment_method` | `CharField` | 先存通用值，之後可由支付回傳更新 |
| `payment_status` | `CharField` | `pending` / `paid` / `failed` / `refunded` |
| `payment_trade_no` | `CharField(blank=True)` | 藍新交易序號 |
| `payment_completed_at` | `DateTimeField(null=True)` | 付款完成時間 |
| `pickup_store_brand` | `CharField(blank=True)` | 超商品牌 |
| `pickup_store_code` | `CharField(blank=True)` | 超商店號 |
| `pickup_store_name` | `CharField(blank=True)` | 超商門市 |
| `pickup_store_address` | `CharField(blank=True)` | 超商門市地址 |
| `buyer_note` | `TextField(blank=True)` | 買家備註 |
| `coupon_code` | `CharField(blank=True)` | 折扣碼 |
| `subtotal_amount` | `DecimalField(max_digits=10, decimal_places=2)` | 商品小計 |
| `shipping_amount` | `DecimalField(max_digits=10, decimal_places=2)` | 運費 |
| `discount_amount` | `DecimalField(max_digits=10, decimal_places=2)` | 折扣 |
| `total_amount` | `DecimalField(max_digits=10, decimal_places=2)` | 總額 |
| `buyer_username_snapshot` | `CharField` | 買家 username snapshot |
| `buyer_display_name_snapshot` | `CharField` | 買家 display name snapshot |
| `buyer_email_snapshot` | `EmailField(blank=True)` | 買家 email snapshot |
| `shipping_address_snapshot` | `JSONField(default=dict)` | 地址 snapshot |
| `invoice_profile_snapshot` | `JSONField(default=dict)` | 發票 snapshot |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 6.2 `order_items`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 所屬訂單 |
| `product` | `ForeignKey(products, null=True)` | 商品 |
| `product_variant` | `ForeignKey(product_variants, null=True)` | variant |
| `seller` | `ForeignKey(users, null=True)` | 賣家 |
| `product_name_snapshot` | `CharField` | 商品名稱 snapshot |
| `display_name_snapshot` | `CharField` | 顯示名稱 snapshot |
| `slug_snapshot` | `CharField` | slug snapshot |
| `variant_name_snapshot` | `CharField(blank=True)` | variant 名稱 snapshot |
| `sku_snapshot` | `CharField(blank=True)` | SKU snapshot |
| `unit_price` | `DecimalField(max_digits=10, decimal_places=2)` | 單價 snapshot |
| `quantity` | `PositiveIntegerField` | 數量 |
| `line_total` | `DecimalField(max_digits=10, decimal_places=2)` | 小計 |
| `seller_username_snapshot` | `CharField` | 賣家 username snapshot |
| `seller_display_name_snapshot` | `CharField` | 賣家 display name snapshot |
| `seller_status` | `CharField` | `pending_shipment` / `shipped` / `completed` |
| `shipping_note` | `TextField(blank=True)` | 出貨備註 |
| `tracking_number` | `CharField(blank=True)` | 物流單號 |
| `shipped_at` | `DateTimeField(null=True)` | 出貨時間 |
| `completed_at` | `DateTimeField(null=True)` | 完成時間 |

### 6.3 `order_service_requests`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 所屬訂單 |
| `request_type` | `CharField` | `cancel` / `refund` |
| `status` | `CharField` | `pending` / `approved` / `rejected` |
| `reason` | `TextField` | 原因 |
| `note` | `TextField(blank=True)` | 審核備註 |
| `created_at` | `DateTimeField` | 申請時間 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |
| `reviewed_by` | `ForeignKey(users, null=True, related_name="+")` | 審核人 |

### 6.4 `shipment_events`

如果要保留出貨歷史，不應只靠 `order_items` 單一狀態欄位。

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `order_item` | `ForeignKey(order_items)` | 所屬訂單明細 |
| `event_type` | `CharField` | `created` / `shipped` / `in_transit` / `delivered` / `completed` |
| `message` | `TextField(blank=True)` | 說明 |
| `tracking_number` | `CharField(blank=True)` | 當時物流單號 |
| `created_at` | `DateTimeField` | 事件時間 |
| `created_by` | `ForeignKey(users, null=True, related_name="+")` | 建立人 |

## 7. 支付與金流 callback

這一區必建，因為即使正式 payment status 仍留在 `orders`，也需要保留支付事件原始資料。

### 7.1 `payment_transactions`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 所屬訂單 |
| `buyer` | `ForeignKey(users)` | 買家 |
| `provider` | `CharField` | 例如 `newebpay` |
| `mode` | `CharField` | `sandbox` / `production` |
| `merchant_order_no` | `CharField(unique=True)` | 商店訂單編號 |
| `trade_no` | `CharField(blank=True)` | 藍新交易序號 |
| `payment_type` | `CharField(blank=True)` | `WEBATM` / `VACC` / `CVS` 等 |
| `status` | `CharField` | `pending` / `paid` / `failed` / `refunded` |
| `amount` | `DecimalField(max_digits=10, decimal_places=2)` | 交易金額 |
| `currency` | `CharField(default="TWD")` | 幣別 |
| `gateway_url` | `URLField(blank=True)` | gateway URL |
| `notify_url` | `URLField(blank=True)` | callback URL |
| `return_url` | `URLField(blank=True)` | return URL |
| `client_back_url` | `URLField(blank=True)` | client back URL |
| `prepared_payload_json` | `JSONField(default=dict)` | 送出前 payload |
| `query_response_json` | `JSONField(default=dict)` | 最後一次 query 結果 |
| `note` | `TextField(blank=True)` | 備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `paid_at` | `DateTimeField(null=True)` | 付款時間 |

### 7.2 `payment_callback_logs`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `payment_transaction` | `ForeignKey(payment_transactions)` | 所屬支付交易 |
| `source` | `CharField` | `callback` / `return` / `query` |
| `http_status` | `PositiveIntegerField(null=True)` | 若為 query 可記錄 HTTP status |
| `result_status` | `CharField(blank=True)` | 藍新 payload 狀態 |
| `result_message` | `TextField(blank=True)` | 訊息 |
| `payload_json` | `JSONField(default=dict)` | 原始 payload |
| `created_at` | `DateTimeField` | 建立時間 |

用途：

- 保留原始證據
- 可區分資料是來自 callback、return、還是 query
- 後續 debug 不必依賴單一摘要欄位

## 8. 評論、問答、社群與匿名

### 8.1 `product_reviews`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 商品 |
| `author` | `ForeignKey(users)` | 作者 |
| `author_display_name_snapshot` | `CharField` | 作者顯示名稱 snapshot |
| `rating` | `PositiveSmallIntegerField` | 星等 |
| `title` | `CharField` | 標題 |
| `body` | `TextField` | 內容 |
| `created_at` | `DateTimeField` | 建立時間 |

公開 API：

- 使用 `author_display_name_snapshot` 經匿名函式處理後輸出

### 8.2 `product_questions`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 商品 |
| `author` | `ForeignKey(users)` | 提問者 |
| `author_display_name_snapshot` | `CharField` | 顯示名稱 snapshot |
| `title` | `CharField` | 標題 |
| `body` | `TextField` | 內容 |
| `created_at` | `DateTimeField` | 建立時間 |

### 8.3 `product_question_answers`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `question` | `ForeignKey(product_questions)` | 所屬問題 |
| `author` | `ForeignKey(users)` | 回答者 |
| `author_display_name_snapshot` | `CharField` | 顯示名稱 snapshot |
| `body` | `TextField` | 內容 |
| `created_at` | `DateTimeField` | 建立時間 |

### 8.4 `community_posts`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `author` | `ForeignKey(users)` | 作者 |
| `author_display_name_snapshot` | `CharField` | 顯示名稱 snapshot |
| `topic` | `CharField` | topic |
| `title` | `CharField` | 標題 |
| `body_html` | `TextField` | 內容 HTML |
| `votes_count` | `IntegerField(default=0)` | 快取票數 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField(null=True)` | 更新時間 |

### 8.5 `community_replies`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `post` | `ForeignKey(community_posts)` | 所屬貼文 |
| `author` | `ForeignKey(users)` | 作者 |
| `author_display_name_snapshot` | `CharField` | 顯示名稱 snapshot |
| `body` | `TextField` | 內容 |
| `created_at` | `DateTimeField` | 建立時間 |

### 8.6 `community_votes`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `post` | `ForeignKey(community_posts)` | 所屬貼文 |
| `user` | `ForeignKey(users)` | 投票者 |
| `value` | `SmallIntegerField` | 目前專案用 upvote，可先固定 `1` |
| `created_at` | `DateTimeField` | 建立時間 |

建議 constraint：

- `UniqueConstraint(fields=["post", "user"])`

## 9. banner、媒體、管理與審核

### 9.1 `banners`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `title` | `CharField(blank=True)` | 標題 |
| `copy_text` | `TextField(blank=True)` | 文案 |
| `image_path` | `CharField` | 圖片 |
| `link_url` | `URLField(blank=True)` | 連結 |
| `position` | `CharField(blank=True)` | 版位 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `status` | `CharField` | `pending` / `approved` / `rejected` / `active` / `inactive` |
| `rejection_reason` | `TextField(blank=True)` | 拒絕原因 |
| `applicant_user` | `ForeignKey(users, null=True, related_name="+")` | 申請者 |
| `reviewed_by` | `ForeignKey(users, null=True, related_name="+")` | 審核人 |
| `starts_at` | `DateTimeField(null=True)` | 顯示開始 |
| `ends_at` | `DateTimeField(null=True)` | 顯示結束 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 9.2 `media_assets`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `uploaded_by` | `ForeignKey(users, null=True)` | 上傳者 |
| `file_path` | `CharField` | 路徑 |
| `file_name` | `CharField` | 原始檔名 |
| `mime_type` | `CharField(blank=True)` | MIME type |
| `file_size` | `BigIntegerField(default=0)` | 檔案大小 |
| `created_at` | `DateTimeField` | 建立時間 |

### 9.3 `admin_audit_logs`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `actor` | `ForeignKey(users)` | 操作者 |
| `action_type` | `CharField` | 例如 `approve_product`, `suspend_user` |
| `target_type` | `CharField` | 例如 `product`, `user`, `order` |
| `target_id` | `CharField` | 目標識別值 |
| `note` | `TextField(blank=True)` | 備註 |
| `payload_json` | `JSONField(default=dict)` | 變更前後資料 |
| `created_at` | `DateTimeField` | 建立時間 |

## 10. 比價與推薦

### 10.1 `competitor_sites`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `code` | `SlugField(unique=True)` | 來源代碼 |
| `name` | `CharField` | 站點名稱 |
| `base_url` | `URLField(blank=True)` | 基礎網址 |
| `source_type` | `CharField` | `mock` / `api` / `crawler` |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `notes` | `TextField(blank=True)` | 備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 10.2 `competitor_products`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `site` | `ForeignKey(competitor_sites)` | 來源站點 |
| `product` | `ForeignKey(products)` | 對應本站商品 |
| `external_product_id` | `CharField(blank=True)` | 外部站自己的商品 ID / key |
| `name` | `CharField` | 外部商品名稱 |
| `product_url` | `CharField(blank=True)` | 外部商品網址 |
| `image_url` | `CharField(blank=True)` | 外部商品圖網址 |
| `latest_price` | `DecimalField(null=True)` | 最新抓到的價格 |
| `latest_currency` | `CharField(default="TWD")` | 最新價格的幣別 |
| `availability_status` | `CharField(blank=True)` | `in_stock` / `out_of_stock` / `unknown` |
| `last_checked_at` | `DateTimeField(null=True)` | 最後檢查時間 |
| `latest_payload_json` | `JSONField(default=dict)` | 最近一次抓取的原始資料 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

建議 constraint：
- `UniqueConstraint(fields=["product", "site", "external_product_id"])`

### 10.3 `product_recommendations`

| 欄位 | 型別 | 說明 |
| --- | --- | --- |
| `id` | `BigAutoField` | 主鍵 |
| `source_product` | `ForeignKey(products, related_name="+")` | 來源商品 |
| `target_product` | `ForeignKey(products, related_name="+")` | 推薦商品 |
| `relation_type` | `CharField` | `similar` / `also_bought` / `manual` |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |

## 11. 不建議遺漏的欄位與規則

### 11.1 訂單 snapshot 不能省

至少要留：

- `buyer_username_snapshot`
- `buyer_display_name_snapshot`
- `buyer_email_snapshot`
- `shipping_address_snapshot`
- `invoice_profile_snapshot`
- `product_name_snapshot`
- `variant_name_snapshot`
- `sku_snapshot`
- `unit_price`
- `seller_display_name_snapshot`

### 11.2 內容資料不能只存匿名後名稱

不要只存：

- `A**`
- `ab***c`

應存：

- `author_user_id`
- `author_display_name_snapshot`

匿名輸出留在 service 層。

### 11.3 支付 callback / query 必須留原始 log

正式整合最怕日後查不到：

- callback 有沒有進來
- 回來時原始 payload 是什麼
- 哪次資料是 return，哪次是 callback，哪次是 query

所以 `payment_callback_logs` 不應省略。

### 11.4 session 遷移要明確

如果決定讓 cart / favorite / compare / recent view 落 DB，就要同步調整：

- login 時 guest bucket merge
- logout 是否清空個人化資料
- 跨裝置同步規則

## 12. migration 建議順序

### Wave 1：最小可交易核心

- `users`
- `user_addresses`
- `user_invoice_profiles`
- `user_shipping_rules`
- `brands`
- `categories`
- `products`
- `product_images`
- `product_variants`
- `orders`
- `order_items`
- `order_service_requests`
- `payment_transactions`
- `payment_callback_logs`

### Wave 2：體驗完整化

- `carts`
- `cart_items`
- `user_favorites`
- `compare_items`
- `recent_views`
- `seller_requests`
- `banners`
- `media_assets`
- `admin_audit_logs`

### Wave 3：內容與擴充

- `product_reviews`
- `product_questions`
- `product_question_answers`
- `community_posts`
- `community_replies`
- `community_votes`
- `competitor_sites`
- `competitor_products`
- `product_recommendations`
- `shipment_events`

## 13. 目前功能盤點後的資料庫提醒

### 13.1 目前已可支撐資料表設計的流程

- 註冊 / 登入 / 賣家申請
- 商品建立 / 編輯 / 審核
- 購物車 / checkout / 建立訂單
- 賣家出貨 / 買家完成訂單
- 評論 / 問答 / 社群
- staff 用戶 / 商品 / 內容 / banner 管理

### 13.2 目前仍要保留彈性的區塊

- NewebPay callback / query 整合尚未完全定案
- 物流目前只保留 checkout store map / 超商選店相關資料
- cart / favorites / compare / recent views 是否 DB 化尚未拍板

## 14. 建表前的最後決策清單

正式開始寫 ORM / migration 前，建議先確認：

1. cart / favorites / compare / recent views 是否入 DB
2. `seller_request_status` 是保留在 `users`，還是完全以 `seller_requests` 為準
3. `brand` / `category` 是否從一開始就正規化成 FK
4. 訂單 `payment_method` 是否保留通用值加細節值，或只保留 gateway 回傳值
5. 評論 / 問答 / 社群對外是否一律匿名
6. payment / callback log 是否採 JSONField 長期保留

## 15. 結論

以目前專案狀態來看，開始正式建資料庫時，最重要的不是先把 `models.py` 填滿，而是先把以下三件事固定：

- 核心交易資料的 snapshot 策略
- session / 個人化資料是否持久化
- 匿名規則在資料層與輸出層的分工

這三件事一旦定好，`users -> products -> orders -> payments` 這條主線就可以穩定開始 migration。

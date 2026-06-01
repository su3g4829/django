# 資料庫建置草案

這份文件整理的是：**如果現在要把專案從 JSON-backed prototype 轉成 Django ORM / 正式資料庫**，建議會建立哪些資料表、每張表大致有哪些欄位、彼此如何關聯。

目前依據的是現有程式中的資料結構：

- `myapp/repositories/local_store.py`
- `myapp/services/auth_demo.py`
- `myapp/services/product_management.py`
- `myapp/services/orders.py`
- `myapp/services/reviews.py`
- `myapp/services/questions.py`
- `myapp/services/community.py`

---

## 設計原則

- 先把**核心交易資料**正規化：會員、商品、商品變體、訂單、訂單明細。
- 訂單中的地址、發票、賣家顯示名稱等，建議保留 **snapshot 欄位**，避免事後修改會員資料導致歷史訂單內容失真。
- 目前 JSON 中很多欄位同時存：
  - `user_id`
  - `username`
  - `display_name`
  
  ORM 化後建議：
  - **關聯欄位保留 `ForeignKey`**
  - **歷史快照欄位保留文字版 username / display_name**

---

## 第一波：核心資料表

這一波最適合先做，因為欄位相對穩定。

### 1. `users`
用途：會員主檔，取代目前 `users.json`

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `username` | `CharField(unique=True)` | 登入帳號 |
| `password_hash` | `CharField` | 密碼雜湊 |
| `display_name` | `CharField` | 顯示名稱 |
| `email` | `EmailField(blank=True)` | Email |
| `role` | `CharField` | `member` / `seller` / `admin` |
| `account_status` | `CharField` | `active` / `suspended` |
| `seller_request_status` | `CharField(blank=True)` | `pending` / `approved` / `rejected` / 空值 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `last_login_at` | `DateTimeField(null=True)` | 最近登入時間 |
| `seller_requested_at` | `DateTimeField(null=True)` | 申請賣家時間 |
| `seller_reviewed_at` | `DateTimeField(null=True)` | 審核完成時間 |
| `account_status_updated_at` | `DateTimeField(null=True)` | 帳號狀態更新時間 |

---

### 2. `addresses`
用途：會員地址簿

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 所屬會員 |
| `label` | `CharField` | 地址標籤，例如「住家」、「公司」 |
| `recipient` | `CharField` | 收件人 |
| `phone` | `CharField` | 聯絡電話 |
| `postal_code` | `CharField` | 郵遞區號 |
| `city` | `CharField` | 縣市 |
| `district` | `CharField` | 區域 |
| `address_line` | `CharField` | 詳細地址 |
| `is_default` | `BooleanField` | 是否預設地址 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 3. `invoice_profiles`
用途：會員發票資料

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `OneToOneField(users)` | 所屬會員 |
| `invoice_type` | `CharField` | `personal` / `company` |
| `carrier_code` | `CharField(blank=True)` | 個人載具 |
| `company_name` | `CharField(blank=True)` | 公司名稱 |
| `tax_id` | `CharField(blank=True)` | 統編 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 4. `products`
用途：商品主檔

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `owner` | `ForeignKey(users)` | 商品擁有者 / 賣家 |
| `slug` | `SlugField(unique=True)` | URL 用 slug |
| `name` | `CharField` | 商品名稱 |
| `brand` | `CharField` | 品牌 |
| `category` | `CharField` | 分類 |
| `price` | `DecimalField` | 主要售價 |
| `compare_at_price` | `DecimalField(null=True)` | 原價 / 比較價 |
| `stock` | `IntegerField` | 基本庫存；若主用變體，可作總庫存或備援欄位 |
| `status` | `CharField` | `draft` / `pending` / `active` / `rejected` / `archived` |
| `review_note` | `TextField(blank=True)` | 商品審核備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |
| `owner_username_snapshot` | `CharField` | 賣家帳號快照 |
| `owner_display_name_snapshot` | `CharField` | 賣家顯示名稱快照 |

補充：

- `tags` 建議不要直接做成純字串欄位，較佳做法有兩種：
  - 先做 `JSONField`
  - 或拆 `product_tags`
- `specs` 建議先用 `JSONField`

---

### 5. `product_images`
用途：商品圖片

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `image_path` | `CharField` | 圖片路徑 |
| `sort_order` | `PositiveIntegerField` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |

---

### 6. `product_variants`
用途：商品變體 / SKU

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `name` | `CharField` | 變體名稱 |
| `sku` | `CharField(blank=True)` | SKU |
| `price` | `DecimalField` | 變體售價 |
| `compare_at_price` | `DecimalField(null=True)` | 變體原價 / 劃線價 |
| `stock` | `IntegerField` | 變體庫存 |
| `color` | `CharField(blank=True)` | 顏色 |
| `size` | `CharField(blank=True)` | 尺寸 |
| `attributes_json` | `JSONField(default=dict)` | 其他屬性 |
| `image_index` | `PositiveIntegerField(null=True)` | 對應第幾張商品圖 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 7. `orders`
用途：訂單主檔

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `buyer` | `ForeignKey(users)` | 下單會員 |
| `status` | `CharField` | `confirmed` / `cancelled` / `refunded` |
| `coupon` | `CharField(blank=True)` | 折扣碼 |
| `buyer_note` | `TextField(blank=True)` | 買家備註 |
| `subtotal_amount` | `DecimalField` | 小計 |
| `shipping_amount` | `DecimalField` | 運費 |
| `discount_amount` | `DecimalField` | 折扣 |
| `total_amount` | `DecimalField` | 總計 |
| `created_at` | `DateTimeField` | 訂單建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `buyer_username_snapshot` | `CharField` | 買家帳號快照 |
| `buyer_display_name_snapshot` | `CharField` | 買家顯示名稱快照 |
| `buyer_email_snapshot` | `EmailField(blank=True)` | 買家 email 快照 |
| `shipping_address_snapshot` | `JSONField` | 下單當下收件地址快照 |
| `invoice_profile_snapshot` | `JSONField` | 下單當下發票資料快照 |

---

### 8. `order_items`
用途：訂單商品明細

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 所屬訂單 |
| `product` | `ForeignKey(products, null=True)` | 對應商品；允許商品已刪除後保留歷史 |
| `variant` | `ForeignKey(product_variants, null=True)` | 對應變體；允許變體已刪除後保留歷史 |
| `seller` | `ForeignKey(users, null=True)` | 賣家 |
| `product_name_snapshot` | `CharField` | 商品名稱快照 |
| `display_name_snapshot` | `CharField` | 顯示名稱快照 |
| `slug_snapshot` | `CharField` | slug 快照 |
| `variant_name_snapshot` | `CharField(blank=True)` | 變體名稱快照 |
| `sku_snapshot` | `CharField(blank=True)` | SKU 快照 |
| `unit_price` | `DecimalField` | 單價快照 |
| `quantity` | `PositiveIntegerField` | 數量 |
| `line_total` | `DecimalField` | 單列總額 |
| `seller_username_snapshot` | `CharField` | 賣家帳號快照 |
| `seller_display_name_snapshot` | `CharField` | 賣家顯示名稱快照 |
| `seller_status` | `CharField` | `pending_shipment` / `shipped` / `completed` |
| `shipping_note` | `TextField(blank=True)` | 出貨備註 |
| `tracking_number` | `CharField(blank=True)` | 物流編號 |
| `shipped_at` | `DateTimeField(null=True)` | 出貨時間 |
| `completed_at` | `DateTimeField(null=True)` | 完成時間 |

---

### 9. `order_service_requests`
用途：訂單售後申請

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `order` | `OneToOneField(orders)` | 一張訂單目前一筆售後申請 |
| `request_type` | `CharField` | `cancel` / `refund` |
| `status` | `CharField` | `pending` / `approved` / `rejected` |
| `reason` | `TextField` | 申請原因 |
| `note` | `TextField(blank=True)` | 審核備註 |
| `created_at` | `DateTimeField` | 申請時間 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |

---

## 第二波：內容互動資料表

這一波是評論、問答、論壇，建議在核心交易表穩定後再接。

### 10. `reviews`
用途：商品評論

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `author` | `ForeignKey(users)` | 評論者 |
| `rating` | `PositiveSmallIntegerField` | 星等 |
| `title` | `CharField` | 評論標題 |
| `body` | `TextField` | 評論內容 |
| `created_at` | `DateTimeField` | 建立時間 |
| `author_username_snapshot` | `CharField` | 作者帳號快照 |
| `author_display_name_snapshot` | `CharField` | 作者名稱快照 |

---

### 11. `product_questions`
用途：商品問答主表

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 所屬商品 |
| `author` | `ForeignKey(users)` | 發問者 |
| `title` | `CharField` | 問題標題 |
| `body` | `TextField` | 問題內容 |
| `created_at` | `DateTimeField` | 建立時間 |
| `author_username_snapshot` | `CharField` | 作者帳號快照 |
| `author_display_name_snapshot` | `CharField` | 作者名稱快照 |

---

### 12. `product_question_answers`
用途：商品問答回覆

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `question` | `ForeignKey(product_questions)` | 所屬問題 |
| `author` | `ForeignKey(users)` | 回答者 |
| `body` | `TextField` | 回答內容 |
| `created_at` | `DateTimeField` | 建立時間 |
| `author_username_snapshot` | `CharField` | 作者帳號快照 |
| `author_display_name_snapshot` | `CharField` | 作者名稱快照 |

---

### 13. `community_posts`
用途：社群文章

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `author` | `ForeignKey(users)` | 發文者 |
| `topic` | `CharField` | 主題分類 |
| `title` | `CharField` | 標題 |
| `body` | `TextField` | 內文 |
| `votes` | `IntegerField(default=0)` | 票數 / 按讚數 |
| `tags_json` | `JSONField(default=list)` | 標籤 |
| `created_at` | `DateTimeField` | 建立時間 |
| `author_username_snapshot` | `CharField` | 作者帳號快照 |
| `author_display_name_snapshot` | `CharField` | 作者名稱快照 |

---

### 14. `community_replies`
用途：社群文章回覆

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `post` | `ForeignKey(community_posts)` | 所屬文章 |
| `author` | `ForeignKey(users)` | 回覆者 |
| `body` | `TextField` | 回覆內容 |
| `created_at` | `DateTimeField` | 建立時間 |
| `author_username_snapshot` | `CharField` | 作者帳號快照 |
| `author_display_name_snapshot` | `CharField` | 作者名稱快照 |

---

## 第三波：可選資料表

這些可以做，但不一定一開始就要拆。

### 15. `carts`
用途：會員購物車主表

若未來不再只依賴 session，而要支援跨裝置同步購物車，建議建立此表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `OneToOneField(users)` | 所屬會員 |
| `coupon` | `CharField(blank=True)` | 已套用折扣碼 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 16. `cart_items`
用途：購物車商品明細

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `cart` | `ForeignKey(carts)` | 所屬購物車 |
| `product` | `ForeignKey(products)` | 對應商品 |
| `variant` | `ForeignKey(product_variants, null=True)` | 對應變體 |
| `quantity` | `PositiveIntegerField` | 數量 |
| `unit_price_snapshot` | `DecimalField` | 加入購物車當下價格快照 |
| `product_name_snapshot` | `CharField` | 商品名稱快照 |
| `variant_name_snapshot` | `CharField(blank=True)` | 變體名稱快照 |
| `sku_snapshot` | `CharField(blank=True)` | SKU 快照 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 17. `user_favorites`
用途：會員收藏商品

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 會員 |
| `product` | `ForeignKey(products)` | 收藏商品 |
| `created_at` | `DateTimeField` | 收藏時間 |

建議加唯一限制：
- `UniqueConstraint(fields=["user", "product"])`

---

### 18. `recently_viewed_products`
用途：會員最近瀏覽紀錄

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 會員 |
| `product` | `ForeignKey(products)` | 瀏覽商品 |
| `viewed_at` | `DateTimeField` | 瀏覽時間 |

補充：
- 若未登入也要記錄最近瀏覽，可維持 session-only，不一定入庫。

---

### 19. `brands`
用途：品牌主檔

目前 `products.brand` 是字串。若要做品牌頁、品牌排序、品牌啟用狀態與 SEO，建議拆主表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `slug` | `SlugField(unique=True)` | 品牌網址代稱 |
| `name` | `CharField(unique=True)` | 品牌名稱 |
| `description` | `TextField(blank=True)` | 品牌說明 |
| `logo_path` | `CharField(blank=True)` | 品牌 logo |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 20. `categories`
用途：商品分類主檔

目前 `products.category` 是字串。若要做分類頁、階層分類、排序與 SEO，建議拆主表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `parent` | `ForeignKey("self", null=True, blank=True)` | 上層分類 |
| `slug` | `SlugField(unique=True)` | 分類網址代稱 |
| `name` | `CharField` | 分類名稱 |
| `description` | `TextField(blank=True)` | 分類說明 |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `sort_order` | `PositiveIntegerField(default=0)` | 排序 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 21. `tags`
用途：商品 / 社群標籤主檔

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `slug` | `SlugField(unique=True)` | 標籤網址代稱 |
| `name` | `CharField(unique=True)` | 標籤名稱 |
| `created_at` | `DateTimeField` | 建立時間 |

---

### 22. `product_tag_relations`
用途：商品與標籤關聯

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `product` | `ForeignKey(products)` | 商品 |
| `tag` | `ForeignKey(tags)` | 標籤 |

建議加唯一限制：
- `UniqueConstraint(fields=["product", "tag"])`

---

### 23. `community_post_votes`
用途：論壇文章按讚 / 投票紀錄

目前 `community_posts.votes` 只有聚合值。若要防止重複投票並保留紀錄，建議加此表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `post` | `ForeignKey(community_posts)` | 所屬文章 |
| `user` | `ForeignKey(users)` | 投票會員 |
| `value` | `SmallIntegerField` | 目前可先定義為 `1` |
| `created_at` | `DateTimeField` | 建立時間 |

建議加唯一限制：
- `UniqueConstraint(fields=["post", "user"])`

---

### 24. `shipment_events`
用途：物流歷程事件

若未來不是只顯示最終狀態，而要顯示「已出貨 / 已到站 / 已送達」等事件，建議拆此表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `order_item` | `ForeignKey(order_items)` | 對應訂單明細 |
| `event_type` | `CharField` | 例如 `created` / `shipped` / `in_transit` / `delivered` |
| `message` | `TextField(blank=True)` | 事件說明 |
| `tracking_number` | `CharField(blank=True)` | 當下物流單號 |
| `created_at` | `DateTimeField` | 事件時間 |
| `created_by` | `ForeignKey(users, null=True)` | 建立事件的人員 |

---

### 25. `admin_audit_logs`
用途：後台管理操作紀錄

目前已有管理者審核賣家、審核商品、審核售後、停權會員等功能，正式上線時應保留操作歷程。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `actor` | `ForeignKey(users)` | 操作者 |
| `action_type` | `CharField` | 例如 `approve_product` / `review_seller_request` / `suspend_user` |
| `target_type` | `CharField` | 例如 `product` / `user` / `order_service_request` |
| `target_id` | `CharField` | 目標主鍵，先保留字串彈性 |
| `note` | `TextField(blank=True)` | 備註 |
| `payload_json` | `JSONField(default=dict)` | 變更前後或額外上下文 |
| `created_at` | `DateTimeField` | 操作時間 |

---

### 26. `notifications`
用途：通知中心

若未來要支援站內通知，例如賣家審核結果、商品審核結果、訂單售後結果，可建立此表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 通知接收者 |
| `title` | `CharField` | 通知標題 |
| `message` | `TextField` | 通知內容 |
| `notification_type` | `CharField` | 例如 `seller_request` / `order` / `review` |
| `target_url` | `CharField(blank=True)` | 點擊後前往頁面 |
| `is_read` | `BooleanField(default=False)` | 是否已讀 |
| `created_at` | `DateTimeField` | 建立時間 |
| `read_at` | `DateTimeField(null=True)` | 已讀時間 |

---

### 27. `media_assets`
用途：媒體資產主檔

目前 `product_images` 直接存 path 即可。若未來要支援共用圖片庫、圖檔類型管理或多模組共用圖片，可再加此表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `uploaded_by` | `ForeignKey(users, null=True)` | 上傳者 |
| `file_path` | `CharField` | 檔案路徑 |
| `file_name` | `CharField` | 原始檔名 |
| `mime_type` | `CharField(blank=True)` | 檔案 MIME 類型 |
| `file_size` | `BigIntegerField(default=0)` | 檔案大小 |
| `created_at` | `DateTimeField` | 建立時間 |

---

### 28. `seller_requests`
用途：賣家申請審核紀錄

目前系統是把狀態直接寫在 `users`。  
若要保留完整審核歷史，建議另外拆表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `user` | `ForeignKey(users)` | 申請者 |
| `status` | `CharField` | `pending` / `approved` / `rejected` |
| `note` | `TextField(blank=True)` | 審核備註 |
| `created_at` | `DateTimeField` | 申請時間 |
| `reviewed_at` | `DateTimeField(null=True)` | 審核時間 |
| `reviewed_by` | `ForeignKey(users, null=True)` | 管理者 |

---

### 29. `competitor_sites`
競品站點主檔，記錄比價資料來自哪一個外部平台。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `code` | `SlugField(unique=True)` | 站點代碼，例如 `momo`、`pchome` |
| `name` | `CharField` | 站點名稱 |
| `base_url` | `URLField` | 站點首頁或主網域 |
| `source_type` | `CharField` | `mock` / `api` / `crawler` |
| `is_active` | `BooleanField(default=True)` | 是否啟用 |
| `notes` | `TextField(blank=True)` | 備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 30. `competitor_products`
競品商品對照表，用來把本站商品與外站商品建立人工或半自動的配對關係。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `site` | `ForeignKey(competitor_sites)` | 來源站點 |
| `product` | `ForeignKey(products)` | 本站商品 |
| `variant` | `ForeignKey(product_variants, null=True)` | 若比價細到變體，可對應本站變體 |
| `external_product_key` | `CharField(blank=True)` | 外站商品 ID / SKU / 識別碼 |
| `external_title` | `CharField` | 外站商品標題 |
| `external_url` | `URLField` | 外站商品頁連結 |
| `matching_status` | `CharField` | `matched` / `possible` / `unmatched` / `archived` |
| `last_checked_at` | `DateTimeField(null=True)` | 最近一次抓價時間 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

---

### 31. `price_snapshots`
價格快照表，保存每次抓到的競品價格，用於比價顯示與後續價格歷史圖。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `competitor_product` | `ForeignKey(competitor_products)` | 對應外站商品 |
| `captured_price` | `DecimalField` | 抓到的價格 |
| `currency` | `CharField(default='TWD')` | 幣別 |
| `captured_at` | `DateTimeField` | 抓價時間 |
| `availability_status` | `CharField(blank=True)` | `in_stock` / `out_of_stock` / `unknown` |
| `payload_json` | `JSONField(default=dict)` | 保留原始抓取回應或額外欄位 |
| `created_at` | `DateTimeField` | 建立時間 |

---

### 32. `product_recommendations`
用途：手動推薦關聯

如果未來仍保留 `recommendations.json` 的概念，可改成表。

| 欄位 | 型別建議 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `source_product` | `ForeignKey(products)` | 來源商品 |
| `target_product` | `ForeignKey(products)` | 被推薦商品 |
| `relation_type` | `CharField` | `similar` / `also_bought` / `manual` |
| `sort_order` | `PositiveIntegerField` | 排序 |

---

## 欄位型別的實務建議

### 建議用 `JSONField` 的欄位
- `products.specs`
- `product_variants.attributes_json`
- `orders.shipping_address_snapshot`
- `orders.invoice_profile_snapshot`
- `community_posts.tags_json`
- `admin_audit_logs.payload_json`
- `price_snapshots.payload_json`

### 建議保留 snapshot 的欄位
- 訂單中的買家名稱 / email
- 訂單明細中的商品名稱 / SKU / 單價
- 訂單明細中的賣家名稱
- 評論 / 問答 / 論壇中的作者名稱

原因：
- 使用者之後改名，不應影響歷史資料顯示
- 商品之後改名或改價，不應影響既有訂單

---

## 特價商品顯示規則

### 商品主表層級
- `products.price`
  - 目前售價
- `products.compare_at_price`
  - 原價 / 劃線價

判斷方式：
- 若 `compare_at_price` 有值，且 `compare_at_price > price`
  - 代表此商品目前為特價商品

前端常見顯示：
- 現價：`price`
- 原價：`compare_at_price`（刪除線）
- 折扣額：`compare_at_price - price`
- 折扣百分比：依前端即時計算

### 商品變體層級
- `product_variants.price`
  - 該變體目前售價
- `product_variants.compare_at_price`
  - 該變體原價 / 劃線價

適用情境：
- 不同尺寸價格不同
- 不同顏色價格不同
- 只有部分變體在特價

判斷方式：
- 若 `variant.compare_at_price > variant.price`
  - 該變體為特價

### 前端建議顯示邏輯

#### 沒有選變體時
- 優先顯示商品主表的：
  - `products.price`
  - `products.compare_at_price`

#### 已選變體時
- 改顯示選中變體的：
  - `product_variants.price`
  - `product_variants.compare_at_price`

這樣可避免：
- 主商品顯示有特價，但實際被選中的變體沒有特價
- 或反過來，主商品沒有特價，但某個變體其實有折扣

### 後續可再擴充的欄位

若未來要做限時活動價，可再增加：

- `sale_starts_at`
- `sale_ends_at`

可加在：
- `products`
- 或 `product_variants`

第一版若只需要正常顯示「原價 / 特價」，目前的：
- `price`
- `compare_at_price`

就已足夠。

---

## 建議 migration 波段

### Wave 1
- `users`
- `addresses`
- `invoice_profiles`
- `products`
- `product_images`
- `product_variants`
- `orders`
- `order_items`
- `order_service_requests`
- `carts`
- `cart_items`
- `user_favorites`
- `recently_viewed_products`

### Wave 2
- `brands`
- `categories`
- `tags`
- `product_tag_relations`
- `reviews`
- `product_questions`
- `product_question_answers`

### Wave 3
- `community_posts`
- `community_replies`
- `community_post_votes`
- `competitor_sites`
- `competitor_products`
- `price_snapshots`
- `shipment_events`
- `admin_audit_logs`
- `notifications`
- `media_assets`
- `seller_requests`
- `product_recommendations`

---

## 最後結論

如果現在要正式開始做 ORM，**最合理的起手式不是一次把所有 JSON 都搬完**，而是：

1. 先做核心交易表  
   `users / products / product_variants / orders / order_items`
2. 再補會員周邊  
   `addresses / invoice_profiles / seller_requests`
3. 最後再搬內容互動  
   `reviews / questions / posts`

這樣 migration 風險最低，也最符合你現在專案的成熟度。

---

## 藍新支付 / 藍新物流測試架構補充表

這一組資料表對應目前先做的 **藍新支付 mock** 與 **藍新物流 mock**。
目的不是直接上正式金流，而是先把：
- 訂單對應的支付交易資料
- callback / webhook 紀錄
- 物流托運單資料
- 物流狀態回傳紀錄

先用 ORM 規格定義清楚，之後可把目前 `JSON` mock log 平滑換成正式資料表。

### 33. `payment_transactions`
保存每一次藍新支付交易建立結果。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 對應訂單 |
| `buyer` | `ForeignKey(users)` | 對應買家 |
| `provider` | `CharField` | 預設記錄 `newebpay_payment` |
| `mode` | `CharField` | `mock` / `sandbox` / `production` |
| `merchant_order_no` | `CharField(unique=True)` | 商店端訂單交易編號 |
| `trade_no` | `CharField(unique=True)` | 金流交易編號 |
| `status` | `CharField` | `pending` / `paid` / `failed` / `refunded` |
| `amount` | `DecimalField` | 交易金額 |
| `currency` | `CharField(default='TWD')` | 幣別 |
| `payment_url` | `URLField(blank=True)` | 導向付款頁或測試網址 |
| `return_url` | `URLField(blank=True)` | 後端通知網址 |
| `client_back_url` | `URLField(blank=True)` | 前端完成後導回網址 |
| `note` | `TextField(blank=True)` | 測試備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |
| `paid_at` | `DateTimeField(null=True)` | 付款成功時間 |

### 34. `payment_callback_logs`
保存藍新支付 callback / webhook 每次回傳內容。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `payment_transaction` | `ForeignKey(payment_transactions)` | 對應支付交易 |
| `provider` | `CharField` | 預設記錄 `newebpay_payment` |
| `callback_status` | `CharField` | callback 回傳狀態 |
| `result_message` | `TextField(blank=True)` | 回傳描述 |
| `payload_json` | `JSONField(default=dict)` | 原始 callback payload |
| `created_at` | `DateTimeField` | callback 接收時間 |

### 35. `logistics_shipments`
保存藍新物流托運單建立結果。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `order` | `ForeignKey(orders)` | 對應訂單 |
| `seller` | `ForeignKey(users)` | 建立托運單的賣家 |
| `provider` | `CharField` | 預設記錄 `newebpay_logistics` |
| `mode` | `CharField` | `mock` / `sandbox` / `production` |
| `logistics_no` | `CharField(unique=True)` | 物流單號 |
| `status` | `CharField` | `created` / `picked_up` / `delivered` / `failed` |
| `store_type` | `CharField` | 例如 `UNIMARTC2C` |
| `temperature` | `CharField(blank=True)` | 常溫 / 低溫等 |
| `receiver_name` | `CharField(blank=True)` | 收件人 |
| `receiver_phone` | `CharField(blank=True)` | 收件人電話 |
| `shipment_note` | `TextField(blank=True)` | 出貨備註 |
| `created_at` | `DateTimeField` | 建立時間 |
| `updated_at` | `DateTimeField` | 更新時間 |

### 36. `logistics_callback_logs`
保存藍新物流 callback / webhook 每次回傳內容。

| 欄位 | 建議型別 | 說明 |
|---|---|---|
| `id` | `BigAutoField` | 主鍵 |
| `logistics_shipment` | `ForeignKey(logistics_shipments)` | 對應物流托運單 |
| `provider` | `CharField` | 預設記錄 `newebpay_logistics` |
| `callback_status` | `CharField` | callback 回傳狀態 |
| `result_message` | `TextField(blank=True)` | 回傳描述 |
| `payload_json` | `JSONField(default=dict)` | 原始 callback payload |
| `created_at` | `DateTimeField` | callback 接收時間 |

### 藍新支付 / 物流補充備註
- `payment_callback_logs.payload_json` 建議使用 `JSONField`
- `logistics_callback_logs.payload_json` 建議使用 `JSONField`
- 若開始做正式金流 / 物流，建議把以下表放入下一波 migration：
  - `payment_transactions`
  - `payment_callback_logs`
  - `logistics_shipments`
  - `logistics_callback_logs`

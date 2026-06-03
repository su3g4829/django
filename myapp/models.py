"""
資料庫 schema 規劃模型。

這份 `models.py` 的目的是把目前 JSON 檔與 session 中的資料結構，
先整理成 Django ORM 可表達的資料表草案，供後續正式導入資料庫時使用。

目前注意事項：
- 這次只有規劃 schema，沒有建立 migration。
- 專案現行流程仍以 JSON repository 與 signed-cookie session 為主。
- 若未來真的要啟用這份 schema，應在第一個正式 migration 前設定
  `AUTH_USER_MODEL = "myapp.AppUser"`，避免外鍵綁到 Django 內建 `auth.User`。
"""

from django.db import models

# -----------------------------------------------------------------------------
# Django model 常見語法速查
# -----------------------------------------------------------------------------
# `models.Model`
# - 來源：`django.db.models`
# - 功能：所有 Django ORM 資料表 class 的基底類別
#
# `models.TextChoices`
# - 來源：`django.db.models`
# - 功能：建立可重用的字串列舉，通常搭配 `CharField(choices=...)`
#
# `class Meta`
# - 來源：Django model 內部設定語法
# - 功能：控制資料表名稱、預設排序、唯一約束、索引、是否為抽象基底等
#
# `def __str__(self) -> str`
# - 來源：Python 物件方法，Django 會在 admin / shell / 關聯欄位顯示時使用
# - 功能：定義這筆資料轉成字串時要顯示什麼
#
# `models.ForeignKey`
# - 來源：`django.db.models`
# - 功能：多對一關聯欄位
#
# `models.OneToOneField`
# - 來源：`django.db.models`
# - 功能：一對一關聯欄位
#
# `related_name`
# - 來源：關聯欄位參數
# - 功能：讓被關聯的一方可以反向查詢，例如 `user.addresses.all()`
#
# `on_delete`
# - 來源：關聯欄位參數
# - 功能：控制關聯目標被刪除時，這筆資料如何處理
#
# `models.JSONField`
# - 來源：`django.db.models`
# - 功能：存放彈性 JSON 結構，適合規格、快照、原始 payload
#
# `models.UniqueConstraint`
# - 來源：Django ORM 的資料庫約束設定
# - 功能：保證某些欄位組合不能重複


class TimestampedModel(models.Model):
    """抽象基底：所有需要建立/更新時間的資料表共用。"""

    # Django ORM 的 `DateTimeField`：
    # - `auto_now_add=True`：建立資料時自動寫入時間
    created_at = models.DateTimeField(auto_now_add=True)
    # - `auto_now=True`：每次更新資料時自動刷新時間
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # `abstract = True` 代表這個 class 只是共用基底，不會建立實際資料表。
        abstract = True


#
# 列舉定義
# 這一段集中放狀態欄位選項，避免 magic string 散落在各個 model。
# 後續 service / serializer / admin 若要顯示中文標籤，也應優先沿用這裡。
#
class AppUserRole(models.TextChoices):
    # `models.TextChoices` 是 Django ORM 的列舉工具。
    # 這類 class 本身不是資料表，而是提供給其他 model 欄位的 `choices=` 使用。
    """平台帳號角色。決定前後台可見功能與權限範圍。"""

    MEMBER = "member", "Member"
    SELLER = "seller", "Seller"
    ADMIN = "admin", "Admin"


class AccountStatus(models.TextChoices):
    # `models.TextChoices` 來自 `django.db.models`。
    # 功能是集中定義可選狀態值，供後面的 `CharField(choices=...)` 直接重用。
    """帳號啟用狀態。用於登入限制、前台可用性與後台停權。"""

    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class SellerRequestStatus(models.TextChoices):
    """賣家申請流程狀態。描述使用者是否申請、審核中、已通過或被拒絕。"""

    NONE = "none", "None"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ProductStatus(models.TextChoices):
    # 這個 class 不是資料表，而是商品狀態列舉。
    # `Product.status` 會使用 `choices=ProductStatus.choices` 限制欄位值。
    """商品生命週期狀態。控制商品是否可在前台顯示與是否需要審核。"""

    DRAFT = "draft", "Draft"
    PENDING_REVIEW = "pending_review", "Pending Review"
    ACTIVE = "active", "Active"
    REJECTED = "rejected", "Rejected"
    ARCHIVED = "archived", "Archived"


class BannerStatus(models.TextChoices):
    """Banner 審核與上下線狀態。"""

    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ARCHIVED = "archived", "Archived"


class OrderStatus(models.TextChoices):
    """訂單主狀態。表示整筆訂單在交易流程中的總體進度。"""

    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class SellerLineStatus(models.TextChoices):
    """訂單明細的賣家履約狀態。用於多賣家、多商品拆單出貨。"""

    PENDING_SHIPMENT = "pending_shipment", "Pending Shipment"
    SHIPPED = "shipped", "Shipped"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class PaymentStatus(models.TextChoices):
    """付款狀態。描述付款單從建立、成功、失敗到退款的階段。"""

    PENDING = "pending", "Pending"
    PREPARED = "prepared", "Prepared"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    REFUNDED = "refunded", "Refunded"


class PaymentSource(models.TextChoices):
    # 付款來源列舉，用來標記資料來自 prepare、return、callback、query 或人工操作。
    # 這能幫助 PaymentTransaction / PaymentCallbackLog 區分資料是怎麼進系統的。
    """付款資料來源。用來區分是送出、前台 return、後台 callback、query 或人工修正。"""

    PREPARE = "prepare", "Prepare"
    RETURN = "return", "Return"
    CALLBACK = "callback", "Callback"
    QUERY = "query", "Query"
    MANUAL = "manual", "Manual"


class ShippingMethod(models.TextChoices):
    """配送方式。先保留宅配與超商取貨兩種主要模式。"""

    HOME_DELIVERY = "home_delivery", "Home Delivery"
    CONVENIENCE_STORE = "convenience_store", "Convenience Store"


class InvoiceType(models.TextChoices):
    """發票類型。對應個人發票與公司發票。"""

    PERSONAL = "personal", "Personal"
    COMPANY = "company", "Company"


class ServiceRequestType(models.TextChoices):
    """售後服務類型，例如退貨、換貨、退款或其他客服案件。"""

    RETURN = "return", "Return"
    EXCHANGE = "exchange", "Exchange"
    REFUND = "refund", "Refund"
    OTHER = "other", "Other"


class ServiceRequestStatus(models.TextChoices):
    """售後服務處理狀態。用於客服/後台追蹤案件進度。"""

    OPEN = "open", "Open"
    REVIEWING = "reviewing", "Reviewing"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CLOSED = "closed", "Closed"


class ShipmentEventType(models.TextChoices):
    """物流事件型別。記錄出貨歷程而不是只保存當前狀態。"""

    CREATED = "created", "Created"
    READY = "ready", "Ready"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    PICKED_UP = "picked_up", "Picked Up"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class CommunityTopic(models.TextChoices):
    """社群貼文分類主題。可用於前台分區與後台內容管理。"""

    GENERAL = "general", "General"
    PRODUCT = "product", "Product"
    SUPPORT = "support", "Support"


class ModerationStatus(models.TextChoices):
    """內容審核狀態。適用於評論、問答、社群內容等對外可見資料。"""

    VISIBLE = "visible", "Visible"
    HIDDEN = "hidden", "Hidden"
    FLAGGED = "flagged", "Flagged"
    DELETED = "deleted", "Deleted"


#
# 會員 / 身分 / 設定
#
class AppUser(TimestampedModel):
    """
    平台使用者主表。

    對應目前 `users.json` 的核心欄位，包含：
    - 登入識別：username / email / password_hash
    - 顯示資訊：display_name
    - 權限身份：member / seller / admin
    - 帳號狀態與賣家申請狀態

    這張表只放使用者主資料。
    地址、發票設定、運費規則另外拆到子表，避免使用者主表過胖。
    """

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=255)
    display_name = models.CharField(max_length=150)
    role = models.CharField(max_length=20, choices=AppUserRole.choices, default=AppUserRole.MEMBER)
    account_status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.ACTIVE)
    seller_request_status = models.CharField(
        max_length=20,
        choices=SellerRequestStatus.choices,
        default=SellerRequestStatus.NONE,
    )
    # `ForeignKey`：
    # - 來源：`django.db.models.ForeignKey`
    # - 功能：建立多對一關聯
    # `related_name="default_for_users"` 讓地址那端可反向查詢哪些會員把它設成預設地址。
    default_address = models.ForeignKey(
        "UserAddress",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_users",
    )
    last_login_at = models.DateTimeField(null=True, blank=True)
    seller_requested_at = models.DateTimeField(null=True, blank=True)
    seller_reviewed_at = models.DateTimeField(null=True, blank=True)
    account_status_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # `db_table` / `ordering` 都屬於 Django model 的 `Meta` 設定。
        # `db_table` 指定資料表名；`ordering` 指定預設查詢排序。
        db_table = "users"
        ordering = ["id"]

    def __str__(self) -> str:
        # `__str__` 是 Python 物件方法；Django admin / shell / 關聯選單會顯示這個字串。
        return self.username


class UserAddress(TimestampedModel):
    """
    使用者地址簿。

    一位使用者可有多筆地址，`AppUser.default_address` 會指向預設地址。
    這張表同時提供：
    - 結帳收件地址來源
    - 會員中心地址管理
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=100)
    recipient = models.CharField(max_length=100)
    phone = models.CharField(max_length=30)
    city = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    address_line = models.CharField(max_length=255)

    class Meta:
        db_table = "user_addresses"
        ordering = ["id"]


class UserInvoiceProfile(TimestampedModel):
    """
    使用者發票偏好設定。

    這裡放的是「預設」發票資訊，不代表歷史訂單內容。
    真正下單時仍需把發票資訊快照寫進 `Order`，避免會員後改資料影響舊訂單。
    """

    # `OneToOneField`：
    # - 來源：`django.db.models.OneToOneField`
    # - 功能：建立一對一關聯
    # 這裡表示一個會員只對應一份主要發票設定。
    user = models.OneToOneField("myapp.AppUser", on_delete=models.CASCADE, related_name="invoice_profile")
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.PERSONAL)
    carrier_code = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    tax_id = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = "user_invoice_profiles"


class UserShippingRule(TimestampedModel):
    """
    賣家運費規則。

    目前對應 seller 的宅配/超商是否開啟、各自運費與免運門檻。
    若未來要支援更複雜的運費模板，可再獨立成多張規則表。
    """

    # 同一位賣家通常只對應一份主要運費規則，所以這裡也用 OneToOneField。
    user = models.OneToOneField("myapp.AppUser", on_delete=models.CASCADE, related_name="shipping_rules")
    home_delivery_enabled = models.BooleanField(default=True)
    home_delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    convenience_store_enabled = models.BooleanField(default=True)
    convenience_store_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    free_shipping_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "user_shipping_rules"


class SellerRequest(TimestampedModel):
    """
    賣家申請紀錄。

    雖然 `AppUser` 上已有當前申請狀態，但這張表保留申請歷程，
    方便後續做審核記錄、駁回原因與審核追蹤。
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, related_name="seller_requests")
    # `is_current` 用來標示這筆是否為目前最新的申請狀態。
    # 未來若同一個使用者多次申請、撤回、再申請，可以保留完整歷史，
    # 同時讓 service 很快找到「目前生效中的那一筆」。
    is_current = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=SellerRequestStatus.choices, default=SellerRequestStatus.PENDING)
    note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "myapp.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_seller_requests",
    )

    class Meta:
        db_table = "seller_requests"
        ordering = ["-created_at"]


#
# 商品主資料
#
class Brand(TimestampedModel):
    """商品品牌主表。供商品列表、品牌頁、篩選與 SEO slug 使用。"""

    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # `Meta` 是 Django model 內部設定 class。
        # 這裡指定實際資料表名稱 `brands`，並讓查詢預設依 `name` 排序。
        db_table = "brands"
        ordering = ["name"]

    def __str__(self) -> str:
        # `__str__` 來自 Python 物件模型。
        # Django admin、shell、外鍵下拉選單都會用這個字串當代表文字。
        return self.name


class Category(TimestampedModel):
    """
    商品分類主表。

    先保留 `parent` 自關聯，讓之後可以支援單層或多層分類，不必重建 schema。
    """

    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=160)
    # 自關聯 `ForeignKey("self")`：
    # - 來源：Django ORM 關聯欄位
    # - 功能：同一張分類表自己連到自己，支援父分類 / 子分類結構
    # - `related_name="children"`：父分類可用 `category.children.all()` 取回子分類
    parent = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="children")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # `Meta` 設定這張分類表的實際資料表名與預設排序方式。
        db_table = "categories"
        ordering = ["name"]

    def __str__(self) -> str:
        # 分類在 Django admin / shell 中顯示時，直接顯示可讀名稱。
        return self.name


class Tag(TimestampedModel):
    """商品標籤主表。用於搜尋、推薦與前台展示。"""

    slug = models.SlugField(max_length=160, unique=True)
    name = models.CharField(max_length=160, unique=True)

    class Meta:
        # Tag 也是一般 Django model；這裡指定資料表名與預設排序。
        db_table = "tags"
        ordering = ["name"]

    def __str__(self) -> str:
        # 讓 Tag 物件在 Django admin / shell 裡顯示 `name`，而不是 `Tag object (1)`。
        return self.name


class Product(TimestampedModel):
    """
    商品主表。

    這張表放商品本體與審核狀態：
    - 基本資訊：名稱、slug、描述、品牌、分類
    - 價格與庫存：price / compare_at_price / stock
    - 彈性規格：specs JSON
    - 擁有者與審核資訊：owner / status / review_note

    `owner_*_snapshot` 保留建立當下的賣家資訊快照，
    避免賣家改名後舊資料完全失去歷史脈絡。
    """

    slug = models.SlugField(max_length=200, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # 這三個都是多對一關聯：
    # - 多個商品對一個品牌
    # - 多個商品對一個分類
    # - 多個商品對一位賣家
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    owner = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    # `DecimalField` 適合金額，避免 float 精度問題。
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(default=0)
    # `JSONField` 用來保存彈性規格資料，例如材質、容量、尺寸摘要。
    specs = models.JSONField(default=dict, blank=True)
    # `choices=ProductStatus.choices` 代表這個欄位只能使用 ProductStatus 定義的列舉值。
    status = models.CharField(max_length=20, choices=ProductStatus.choices, default=ProductStatus.DRAFT)
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "myapp.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_products",
    )
    owner_username_snapshot = models.CharField(max_length=150, blank=True)
    owner_display_name_snapshot = models.CharField(max_length=150, blank=True)

    class Meta:
        # 商品主表預設依 `id` 排序，方便與既有 JSON fixture / 舊邏輯對齊。
        db_table = "products"
        ordering = ["id"]

    def __str__(self) -> str:
        # 商品物件轉成字串時，顯示商品名稱。
        return self.name


class ProductImage(TimestampedModel):
    """
    商品圖片表。

    一個商品可有多張圖片，前台排序與主要圖都由這張表控制。
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    file_path = models.CharField(max_length=500)
    sort_order = models.PositiveIntegerField(default=0)
    alt_text = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        # 同一商品的圖片通常會依排序值顯示，這裡先按商品、再按排序值、最後按 id。
        db_table = "product_images"
        ordering = ["product_id", "sort_order", "id"]


class ProductVariant(TimestampedModel):
    """
    商品變體表。

    一個商品可有多個尺寸/顏色/組合版本。
    `attributes` 用 JSON 保留彈性結構，例如 size/color。
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    external_variant_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    # 現行商品建立流程允許 SKU 空白，因此先不要做成必填且全域唯一。
    # 後續若要強化，可改成在同商品下唯一，或由 service 層補齊規則。
    sku = models.CharField(max_length=255, blank=True, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock = models.IntegerField(default=0)
    attributes = models.JSONField(default=dict, blank=True)
    image = models.ForeignKey(ProductImage, on_delete=models.SET_NULL, null=True, blank=True, related_name="variants")
    image_path_snapshot = models.CharField(max_length=500, blank=True)

    class Meta:
        # 變體資料通常跟著商品一起顯示，所以先按商品，再按自己的建立順序排序。
        db_table = "product_variants"
        ordering = ["product_id", "id"]


class ProductTagRelation(models.Model):
    """
    商品與標籤的多對多關聯表。

    雖然 Django 可直接用 `ManyToManyField`，這裡保留獨立 class，
    是為了之後若要增加排序、推薦權重、標籤來源等欄位時比較好擴充。
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        # `constraints` 也是 Django model 的 `Meta` 設定之一。
        # `models.UniqueConstraint` 來自 `django.db.models`，
        # 用來保證同一個 product + tag 組合只能出現一次。
        db_table = "product_tag_relations"
        constraints = [
            models.UniqueConstraint(fields=["product", "tag"], name="uniq_product_tag_relation"),
        ]


#
# 使用者購物行為 / 個人化
#
class Cart(TimestampedModel):
    """
    購物車主表。

    目前專案實際上仍使用 session 保存購物車；這張表是未來若要將購物車持久化到 DB
    時的規劃結構。可同時支援登入使用者與訪客 session。
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, null=True, blank=True, related_name="carts")
    session_key = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # 這張表目前只先固定資料表名稱；排序規則未來可再依需求補。
        db_table = "carts"


class CartItem(TimestampedModel):
    """
    購物車明細。

    這裡保留商品/變體外鍵，也保留價格與名稱 snapshot，
    避免商品改價後購物車內容完全無法還原當時畫面。
    """

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    # item_key 對應目前 cart service 的 key 規則：
    # - 無變體：`product-slug`
    # - 有變體：`product-slug__variant-id`
    # 之後若正式切 DB cart，以 `(cart, item_key)` 當唯一鍵會比 nullable
    # variant 外鍵更穩，避免 MySQL 對 UNIQUE + NULL 的重複容忍問題。
    item_key = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    product_name_snapshot = models.CharField(max_length=255)
    variant_name_snapshot = models.CharField(max_length=255, blank=True)
    product_slug_snapshot = models.SlugField(max_length=200)

    class Meta:
        # 避免同一購物車中重複出現同商品/同變體多筆資料。
        # 正常情況應該是更新數量，而不是新增重複列。
        db_table = "cart_items"
        constraints = [
            models.UniqueConstraint(fields=["cart", "item_key"], name="uniq_cart_item_key"),
        ]


class UserFavorite(TimestampedModel):
    """
    會員收藏商品。

    這是會員對商品的長期偏好資料，與 session 型的暫時行為不同。
    唯一約束確保同一使用者對同一商品只收藏一次。
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")

    class Meta:
        # 同一使用者對同一商品只能收藏一次。
        db_table = "user_favorites"
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="uniq_user_favorite"),
        ]


class CompareItem(TimestampedModel):
    """
    商品比較清單。

    目前前台比價清單仍可由 session 支撐；若之後要持久化或跨裝置同步，
    這張表就是正式落點。
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, null=True, blank=True, related_name="compare_items")
    session_key = models.CharField(max_length=100, blank=True)
    # `bucket_key` 是給資料庫唯一鍵用的穩定 owner key。
    # 例如：
    # - 已登入會員：`user:123`
    # - 訪客模式：`session:abcxyz`
    # 這樣可以避免 MySQL 在 `NULL` 欄位唯一約束上的不同行為。
    bucket_key = models.CharField(max_length=140)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="compare_entries")

    class Meta:
        db_table = "compare_items"
        constraints = [
            # 比較清單在資料庫層應該是 set-like，同一個 bucket 對同一商品只能有一筆。
            models.UniqueConstraint(fields=["bucket_key", "product"], name="uniq_compare_bucket_product"),
        ]


class RecentView(TimestampedModel):
    """
    最近瀏覽商品紀錄。

    用來支援：
    - 會員中心最近看過
    - 前台快速返回
    - 推薦系統的瀏覽行為訊號
    """

    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, null=True, blank=True, related_name="recent_views")
    session_key = models.CharField(max_length=100, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="recent_views")
    viewed_at = models.DateTimeField()

    class Meta:
        # 最近瀏覽的查詢通常需要最新在前。
        db_table = "recent_views"
        ordering = ["-viewed_at"]


#
# 訂單 / 履約 / 售後
#
class Order(TimestampedModel):
    """
    訂單主表。

    這張表是整個交易流程核心，除訂單狀態外還保存：
    - 收件資料快照
    - 超商門市資料快照
    - 發票資料快照
    - 金額摘要
    - 付款結果摘要

    注意：訂單表中的地址、收件人、發票欄位都應保留 snapshot，
    不應只依賴使用者當前設定。
    """

    order_no = models.CharField(max_length=50, unique=True)
    buyer = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    shipping_method = models.CharField(max_length=30, choices=ShippingMethod.choices)
    payment_method = models.CharField(max_length=100, blank=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    payment_trade_no = models.CharField(max_length=100, blank=True)
    payment_merchant_order_no = models.CharField(max_length=100, blank=True)
    buyer_email = models.EmailField(blank=True)
    # 買家資訊快照，避免會員之後修改帳號顯示名稱影響舊訂單。
    buyer_username_snapshot = models.CharField(max_length=150, blank=True)
    buyer_display_name_snapshot = models.CharField(max_length=150, blank=True)
    # 宅配收件資訊快照。
    shipping_label = models.CharField(max_length=100, blank=True)
    shipping_recipient = models.CharField(max_length=100, blank=True)
    shipping_phone = models.CharField(max_length=30, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_district = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_address_line = models.CharField(max_length=255, blank=True)
    # 超商取貨門市資訊快照。
    pickup_store_code = models.CharField(max_length=50, blank=True)
    pickup_store_name = models.CharField(max_length=255, blank=True)
    pickup_store_address = models.CharField(max_length=255, blank=True)
    pickup_store_type = models.CharField(max_length=50, blank=True)
    pickup_recipient = models.CharField(max_length=100, blank=True)
    pickup_phone = models.CharField(max_length=30, blank=True)
    # 發票資訊快照。
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices, default=InvoiceType.PERSONAL)
    invoice_carrier_code = models.CharField(max_length=100, blank=True)
    invoice_company_name = models.CharField(max_length=255, blank=True)
    invoice_tax_id = models.CharField(max_length=20, blank=True)
    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # 訂單列表幾乎都會先看最新資料，所以預設使用 `-id` 倒序。
        db_table = "orders"
        ordering = ["-id"]


class OrderItem(TimestampedModel):
    """
    訂單商品明細。

    一張訂單會拆成多個 order item，並保留：
    - 商品與變體外鍵
    - 賣家外鍵
    - 當下名稱、SKU、顯示名稱、價格的快照
    - 每筆明細自己的出貨狀態

    這樣可以支援一張訂單內含多賣家、多商品，且每條明細各自出貨。
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    seller = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="sold_order_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    # 商品與賣家快照，避免來源資料變更後無法還原歷史訂單內容。
    product_slug_snapshot = models.SlugField(max_length=200)
    product_name_snapshot = models.CharField(max_length=255)
    product_display_name_snapshot = models.CharField(max_length=255, blank=True)
    variant_external_id_snapshot = models.CharField(max_length=255, blank=True)
    variant_name_snapshot = models.CharField(max_length=255, blank=True)
    sku_snapshot = models.CharField(max_length=255, blank=True)
    seller_username_snapshot = models.CharField(max_length=150, blank=True)
    seller_display_name_snapshot = models.CharField(max_length=150, blank=True)
    seller_status = models.CharField(max_length=30, choices=SellerLineStatus.choices, default=SellerLineStatus.PENDING_SHIPMENT)
    tracking_number = models.CharField(max_length=100, blank=True)
    shipping_note = models.TextField(blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # 訂單項目維持建立順序即可，避免同張訂單內的商品順序不穩定。
        db_table = "order_items"
        ordering = ["id"]


class OrderServiceRequest(TimestampedModel):
    """
    售後服務申請。

    用於退貨、換貨、退款或其他客服處理需求。
    可以綁整張訂單，也可以細到某個 order item。
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="service_requests")
    order_item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="service_requests")
    user = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="service_requests")
    request_type = models.CharField(max_length=20, choices=ServiceRequestType.choices)
    status = models.CharField(max_length=20, choices=ServiceRequestStatus.choices, default=ServiceRequestStatus.OPEN)
    reason = models.TextField(blank=True)
    note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "myapp.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_service_requests",
    )

    class Meta:
        db_table = "order_service_requests"
        ordering = ["-created_at"]


class ShipmentEvent(TimestampedModel):
    """
    出貨/物流事件紀錄。

    與 `OrderItem.seller_status` 不同，這張表記錄的是歷程事件，
    例如建立、已出貨、已送達、已完成等時間點。
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="shipment_events")
    order_item = models.ForeignKey(OrderItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="shipment_events")
    event_type = models.CharField(max_length=30, choices=ShipmentEventType.choices)
    tracking_number = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    operator = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="shipment_events")
    happened_at = models.DateTimeField()

    class Meta:
        db_table = "shipment_events"
        ordering = ["happened_at", "id"]


#
# 金流
#
class PaymentTransaction(TimestampedModel):
    """
    付款交易主表。

    一張訂單可對應多次付款嘗試，因此付款資訊不能只放在 `Order`。
    這張表保留：
    - 商店訂單編號 / 藍新交易序號
    - 付款方式代碼與顯示名稱
    - 送出給 gateway 的 form 欄位
    - callback / return / query 後得到的結果
    - 最近一次 query 的診斷資訊
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_transactions")
    provider = models.CharField(max_length=50, default="newebpay")
    source = models.CharField(max_length=20, choices=PaymentSource.choices, default=PaymentSource.PREPARE)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PREPARED)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    merchant_id = models.CharField(max_length=50, blank=True)
    merchant_order_no = models.CharField(max_length=100, db_index=True)
    trade_no = models.CharField(max_length=100, blank=True, db_index=True)
    payment_type_code = models.CharField(max_length=100, blank=True)
    payment_method_label = models.CharField(max_length=100, blank=True)
    gateway_url = models.CharField(max_length=500, blank=True)
    callback_count = models.PositiveIntegerField(default=0)
    # 下面幾個 JSON 欄位主要用於保留支付整合調試與追查資料。
    prepared_form_fields = models.JSONField(default=dict, blank=True)
    prepared_trade_info_params = models.JSONField(default=dict, blank=True)
    latest_raw_payload = models.JSONField(default=dict, blank=True)
    latest_result_payload = models.JSONField(default=dict, blank=True)
    last_query_amount = models.CharField(max_length=50, blank=True)
    last_query_merchant_order_no = models.CharField(max_length=100, blank=True)
    last_query_error = models.TextField(blank=True)
    last_query_response = models.JSONField(default=dict, blank=True)
    last_query_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # 一筆訂單可能會有多次付款嘗試，最新那筆通常最重要，所以用新到舊排序。
        db_table = "payment_transactions"
        ordering = ["-id"]


class PaymentCallbackLog(TimestampedModel):
    """
    金流回傳紀錄表。

    用來逐筆保存 callback / return / query 的原始資料與解析結果，
    方便稽核、除錯、對帳與追查第三方整合問題。
    """

    payment_transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="callback_logs",
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name="payment_callback_logs")
    provider = models.CharField(max_length=50, default="newebpay")
    source = models.CharField(max_length=20, choices=PaymentSource.choices)
    is_success = models.BooleanField(default=False)
    http_status = models.PositiveIntegerField(default=200)
    raw_payload = models.JSONField(default=dict, blank=True)
    parsed_payload = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        # callback / return / query log 也以最新事件最重要，因此採倒序。
        db_table = "payment_callback_logs"
        ordering = ["-id"]


#
# 內容：評論 / 問答 / 社群
#
class ProductReview(TimestampedModel):
    """
    商品評論。

    DB 內保留真實作者關聯與作者名稱快照；
    API 對外是否匿名顯示，應在 service / serializer 層處理，不在資料庫層硬改。
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    author = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    author_name_snapshot = models.CharField(max_length=150)
    public_display_name = models.CharField(max_length=150, blank=True)
    rating = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    moderation_status = models.CharField(max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.VISIBLE)

    class Meta:
        db_table = "product_reviews"
        ordering = ["-id"]


class ProductQuestion(TimestampedModel):
    """
    商品問答中的提問主表。

    與評論不同，問答需要再往下連到回答表，因此拆成 Question / Answer 兩層。
    公開顯示是否匿名，仍由 API 層控制。
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="questions")
    author = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="questions")
    author_name_snapshot = models.CharField(max_length=150)
    public_display_name = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    moderation_status = models.CharField(max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.VISIBLE)

    class Meta:
        db_table = "product_questions"
        ordering = ["-id"]


class ProductQuestionAnswer(TimestampedModel):
    """
    商品問答中的回答表。

    一個問題可對應多個回答，回答者可能是賣家、管理者或一般會員。
    """

    question = models.ForeignKey(ProductQuestion, on_delete=models.CASCADE, related_name="answers")
    author = models.ForeignKey(
        "myapp.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_answers",
    )
    author_name_snapshot = models.CharField(max_length=150)
    public_display_name = models.CharField(max_length=150, blank=True)
    body = models.TextField()
    moderation_status = models.CharField(max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.VISIBLE)

    class Meta:
        db_table = "product_question_answers"
        ordering = ["id"]


class CommunityPost(TimestampedModel):
    """
    社群貼文主表。

    目前對應論壇/社群牆的主文內容，包含 topic、標籤、票數與匿名顯示資料。
    """

    topic = models.CharField(max_length=30, choices=CommunityTopic.choices, default=CommunityTopic.GENERAL)
    author = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="community_posts")
    author_name_snapshot = models.CharField(max_length=150)
    public_display_name = models.CharField(max_length=150, blank=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    tags = models.JSONField(default=list, blank=True)
    vote_count = models.IntegerField(default=0)
    moderation_status = models.CharField(max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.VISIBLE)

    class Meta:
        db_table = "community_posts"
        ordering = ["-id"]


class CommunityReply(TimestampedModel):
    """
    社群貼文回覆表。

    與主文分表，方便未來：
    - 獨立審核
    - 回覆分頁
    - 針對回覆做更多權限或通知邏輯
    """

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="replies")
    author = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="community_replies")
    author_name_snapshot = models.CharField(max_length=150)
    public_display_name = models.CharField(max_length=150, blank=True)
    body = models.TextField()
    moderation_status = models.CharField(max_length=20, choices=ModerationStatus.choices, default=ModerationStatus.VISIBLE)

    class Meta:
        db_table = "community_replies"
        ordering = ["id"]


class CommunityVote(TimestampedModel):
    """
    社群貼文投票紀錄。

    目前先用單純的貼文投票模型。
    若未來要支援回覆按讚、倒讚、表情反應，可再擴充。
    """

    post = models.ForeignKey(CommunityPost, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey("myapp.AppUser", on_delete=models.CASCADE, related_name="community_votes")
    value = models.SmallIntegerField(default=1)

    class Meta:
        db_table = "community_votes"
        constraints = [
            models.UniqueConstraint(fields=["post", "user"], name="uniq_community_post_vote"),
        ]


#
# 營運素材 / Banner / 後台稽核
#
class MediaAsset(TimestampedModel):
    """
    媒體資產主表。

    用於統一管理商品圖、Banner 圖或未來其他上傳檔案。
    如果之後要做檔案回收、尺寸資訊或 CDN，同步點都會在這張表。
    """

    owner = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="media_assets")
    file_path = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(default=0)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    purpose = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "media_assets"
        ordering = ["-id"]


class Banner(TimestampedModel):
    """
    Banner / 廣告申請與展示資料。

    同時覆蓋：
    - 賣家申請的 banner 內容
    - 後台審核狀態
    - 前台顯示位置、期間、排序
    """

    title = models.CharField(max_length=255)
    copy_text = models.TextField(blank=True)
    image_path = models.CharField(max_length=500, blank=True)
    media_asset = models.ForeignKey(MediaAsset, on_delete=models.SET_NULL, null=True, blank=True, related_name="banners")
    link_url = models.CharField(max_length=500, blank=True)
    starts_at = models.DateField(null=True, blank=True)
    ends_at = models.DateField(null=True, blank=True)
    position = models.CharField(max_length=100)
    position_label = models.CharField(max_length=150, blank=True)
    note = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=BannerStatus.choices, default=BannerStatus.PENDING)
    is_active = models.BooleanField(default=False)
    is_currently_visible = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True)
    applicant = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="banner_applications")
    applicant_username_snapshot = models.CharField(max_length=150, blank=True)
    applicant_display_name_snapshot = models.CharField(max_length=150, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "myapp.AppUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_banners",
    )
    reviewed_by_username_snapshot = models.CharField(max_length=150, blank=True)
    reviewed_by_display_name_snapshot = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = "banners"
        ordering = ["sort_order", "id"]


class AdminAuditLog(TimestampedModel):
    """
    後台操作稽核紀錄。

    正式上資料庫後，凡是帳號狀態調整、商品審核、Banner 審核、內容隱藏等，
    都應有可追查的 before / after 資料。
    """

    actor = models.ForeignKey("myapp.AppUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="admin_audit_logs")
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    summary = models.CharField(max_length=255, blank=True)
    before_data = models.JSONField(default=dict, blank=True)
    after_data = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "admin_audit_logs"
        ordering = ["-id"]


#
# 競品價格 / 推薦
#
class CompetitorSite(TimestampedModel):
    """比價站點主表，例如不同外部電商來源。"""

    name = models.CharField(max_length=150, unique=True)
    base_url = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "competitor_sites"
        ordering = ["name"]


class CompetitorProduct(TimestampedModel):
    """
    外部站點商品主表，供價格追蹤與競品對照使用。

    這裡不保存每次抓價的完整歷史，而是只保留「目前最新」的價格資訊，
    避免之後商品數量變多時，價格快照表膨脹過快。
    """

    # 一筆外部商品對照必須知道它對應站內哪個商品，
    # 不然之後會無法回答「這個競品價格屬於我們哪件商品」。
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="competitor_products")
    site = models.ForeignKey(CompetitorSite, on_delete=models.CASCADE, related_name="products")
    external_product_id = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    product_url = models.CharField(max_length=500, blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    latest_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    latest_currency = models.CharField(max_length=10, default="TWD")
    availability_status = models.CharField(max_length=30, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    latest_payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "competitor_products"
        ordering = ["site_id", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "site", "external_product_id"],
                name="uniq_competitor_product_mapping",
            ),
        ]


class ProductRecommendation(TimestampedModel):
    """
    商品推薦關聯表。

    可作為人工推薦、規則推薦或未來演算法推薦的落點。
    目前先用 `source_product -> recommended_product` 的簡單模型表示。
    """

    source_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="outgoing_recommendations")
    recommended_product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="incoming_recommendations")
    score = models.DecimalField(max_digits=8, decimal_places=4, default=0)
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "product_recommendations"
        constraints = [
            models.UniqueConstraint(
                fields=["source_product", "recommended_product"],
                name="uniq_product_recommendation",
            ),
        ]

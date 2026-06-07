"""REST Framework Serializer 定義。

這個檔案集中放置 API 請求與回應用的 Serializer。
目前專案仍以本地 JSON 與 service layer 為核心，
因此這裡使用的是 `rest_framework.serializers.Serializer`，
而不是依賴 Django ORM 的 `ModelSerializer`。
"""
from __future__ import annotations

from rest_framework import serializers


# ---------------------------------------------------------------------------
# 商品瀏覽 / 商品主資料
# 這一段描述商品總覽、商品明細、分類、比較頁會用到的 payload 結構。
# 來源模組為 DRF `rest_framework.serializers`。
# 功能是替 API view 做輸入驗證與輸出結構約束。
# ---------------------------------------------------------------------------
class ProductListQuerySerializer(serializers.Serializer):
    """商品列表 query string 驗證器。

    主要供：
    - 商品總覽頁
    - 品牌頁 / 分類頁
    - 關鍵字搜尋結果頁

    用途是先把 `request.query_params` 轉成乾淨型別，
    避免 view 直接處理未驗證的字串資料。
    """
    q = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.CharField(required=False, allow_blank=True)
    tag = serializers.CharField(required=False, allow_blank=True)
    color = serializers.CharField(required=False, allow_blank=True)
    size = serializers.CharField(required=False, allow_blank=True)
    sort = serializers.CharField(required=False, allow_blank=True, default="featured")
    min_price = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    max_price = serializers.DecimalField(required=False, max_digits=10, decimal_places=2)
    page = serializers.IntegerField(required=False, min_value=1, default=1)


class VariantAttributesSerializer(serializers.Serializer):
    """商品變體的屬性欄位。

    目前主要描述前端最常用的兩種規格：
    - 顏色 `color`
    - 尺寸 `size`
    """
    color = serializers.CharField(required=False, allow_blank=True)
    size = serializers.CharField(required=False, allow_blank=True)


class VariantSerializer(serializers.Serializer):
    """單一商品變體的回應格式。

    這份結構會被商品詳情頁與賣家商品編輯頁共用，
    用來描述變體價格、庫存、圖片與規格屬性。
    """
    id = serializers.CharField()
    name = serializers.CharField()
    sku = serializers.CharField(required=False, allow_blank=True)
    price = serializers.FloatField()
    stock = serializers.IntegerField()
    image = serializers.CharField(required=False, allow_blank=True)
    image_index = serializers.IntegerField(required=False, allow_null=True)
    attributes = VariantAttributesSerializer(required=False)


class ProductSerializer(serializers.Serializer):
    """前台商品主回應格式。

    這是商品列表、商品詳情、收藏、推薦、比較頁共用的核心 payload。
    除了基本資料，也保留前端直接渲染會用到的衍生欄位。
    """
    # 商品主識別與基本展示欄位
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    price = serializers.FloatField()
    compare_at_price = serializers.FloatField(required=False, allow_null=True)
    brand = serializers.CharField()
    category = serializers.CharField()
    category_slug = serializers.CharField(required=False, allow_blank=True)
    category_label = serializers.CharField(required=False, allow_blank=True)

    # 商品附屬內容：tag、圖片、規格
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    images = serializers.ListField(child=serializers.CharField(), required=False)
    primary_image = serializers.CharField(required=False, allow_blank=True)
    specs = serializers.DictField(required=False)

    # 商品狀態 / 擁有者 / 建立時間
    stock = serializers.IntegerField(required=False, allow_null=True)
    price_compare_enabled = serializers.BooleanField(required=False)
    price_compare_query = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False)
    owner_user_id = serializers.IntegerField(required=False, allow_null=True)
    owner_username = serializers.CharField(required=False, allow_blank=True)
    owner_display_name = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.CharField(required=False, allow_blank=True)
    created_at_display = serializers.CharField(required=False, allow_blank=True)
    updated_at_display = serializers.CharField(required=False, allow_blank=True)

    # 變體與前端顯示輔助欄位
    has_variants = serializers.BooleanField(required=False)
    variant_count = serializers.IntegerField(required=False)
    variant_price_min = serializers.FloatField(required=False)
    variant_price_max = serializers.FloatField(required=False)
    price_range_label = serializers.CharField(required=False)
    stock_status = serializers.CharField(required=False)
    is_favorite = serializers.BooleanField(required=False)
    color_options = serializers.ListField(child=serializers.CharField(), required=False)
    size_options = serializers.ListField(child=serializers.CharField(), required=False)
    filter_attributes = serializers.DictField(required=False)
    shipping_profile = serializers.DictField(required=False)
    variants = VariantSerializer(many=True, required=False)


class PageMetaSerializer(serializers.Serializer):
    """列表分頁資訊。

    讓前端可以根據目前頁碼、總頁數與總筆數畫出 pagination UI。
    """
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    total_items = serializers.IntegerField()


class ProductListResponseSerializer(serializers.Serializer):
    """商品列表頁的完整回應格式。

    內容除了 `items` 與分頁資訊，也包含：
    - `facets`：可供篩選 UI 使用的統計資料
    - `filters`：後端實際套用的條件回顯
    """
    items = ProductSerializer(many=True)
    meta = PageMetaSerializer()
    facets = serializers.DictField(required=False)
    filters = serializers.DictField(required=False)


class ProductCategorySerializer(serializers.Serializer):
    """商品分類主表回應格式。"""

    id = serializers.IntegerField(required=False)
    slug = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False)


class ProductCategoryListResponseSerializer(serializers.Serializer):
    """商品分類列表回應格式。"""

    items = ProductCategorySerializer(many=True)


class ProductCategoryCreateSerializer(serializers.Serializer):
    """建立商品分類的請求格式。"""

    name = serializers.CharField()
    slug = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, default=True)


class ProductCompareResponseSerializer(serializers.Serializer):
    """商品比較頁的回應格式。

    `items` 是實際可比較的商品資料；
    `slugs` 保留原始比較清單，方便前端知道哪些 slug 正在比較中。
    """

    items = ProductSerializer(many=True)
    slugs = serializers.ListField(child=serializers.CharField())


# ---------------------------------------------------------------------------
# 商品評論 / 問答 / 推薦 / 比價
# ---------------------------------------------------------------------------
class ReviewSerializer(serializers.Serializer):
    """單筆商品評論格式。

    供商品詳情頁評論區與會員中心評論摘要使用。
    """
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    author = serializers.CharField()
    author_user_id = serializers.IntegerField(required=False, allow_null=True)
    author_username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    rating = serializers.IntegerField()
    title = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)


class ReviewCreateSerializer(serializers.Serializer):
    """建立商品評論時的輸入格式。

    這層只檢查基本結構與長度，
    真正的商業規則仍交由 `review_service` 判斷。
    """
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=80)
    body = serializers.CharField()


class ReviewListResponseSerializer(serializers.Serializer):
    """商品評論列表回應格式。"""
    items = ReviewSerializer(many=True)


class QuestionAnswerSerializer(serializers.Serializer):
    """單筆問答回答格式。

    會巢狀出現在 `QuestionSerializer.answers` 內。
    """
    id = serializers.IntegerField()
    author = serializers.CharField()
    author_user_id = serializers.IntegerField(required=False, allow_null=True)
    author_username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    body = serializers.CharField()
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)


class QuestionSerializer(serializers.Serializer):
    """單筆商品問題格式。

    除了問題本身，也可帶上回答數量與巢狀回答清單，
    方便商品詳情頁一次畫出完整 Q&A 區塊。
    """
    id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    author = serializers.CharField()
    author_user_id = serializers.IntegerField(required=False, allow_null=True)
    author_username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    title = serializers.CharField()
    body = serializers.CharField()
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)
    answer_count = serializers.IntegerField(required=False)
    answers = QuestionAnswerSerializer(many=True, required=False)


class QuestionCreateSerializer(serializers.Serializer):
    """建立商品問題時的輸入格式。"""
    title = serializers.CharField(max_length=80)
    body = serializers.CharField()


class AnswerCreateSerializer(serializers.Serializer):
    """建立問題回答時的輸入格式。"""
    body = serializers.CharField()


class QuestionListResponseSerializer(serializers.Serializer):
    """商品問答列表回應格式。"""
    items = QuestionSerializer(many=True)


class RecommendationGroupSerializer(serializers.Serializer):
    """商品推薦區塊格式。

    目前固定分成：
    - `similar`：相似商品
    - `also_bought`：一起購買
    """
    similar = ProductSerializer(many=True)
    also_bought = ProductSerializer(many=True)


class CompetitorPriceItemSerializer(serializers.Serializer):
    """單一外站比價結果。

    這份 serializer 用來描述：
    - 來源站點
    - 模擬抓到的價格
    - 與本站價格的差額
    """

    site = serializers.CharField()
    site_label = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    price = serializers.FloatField()
    currency = serializers.CharField()
    captured_at = serializers.CharField()
    captured_at_display = serializers.CharField()
    status = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True)
    diff_amount = serializers.FloatField()
    diff_percent = serializers.FloatField()
    is_cheaper_than_our_price = serializers.BooleanField()
    is_same_as_our_price = serializers.BooleanField()


class PriceComparisonSerializer(serializers.Serializer):
    """商品比價結果。

    這份 payload 會提供商品頁一個獨立區塊來展示：
    - 本站售價
    - 外站模擬價格
    - 最低價資訊
    - 資料是否為 mock
    """

    # 本站商品資訊
    our_product_slug = serializers.CharField()
    our_product_name = serializers.CharField()
    our_product_id = serializers.IntegerField()
    our_price = serializers.FloatField()
    currency = serializers.CharField()
    query = serializers.CharField(required=False, allow_blank=True)

    # 比價來源摘要
    is_mock = serializers.BooleanField()
    source_type = serializers.CharField()
    last_refreshed_at = serializers.CharField()
    last_refreshed_at_display = serializers.CharField()

    # 比價結論
    lowest_price = serializers.FloatField()
    our_store_is_lowest = serializers.BooleanField()
    items = CompetitorPriceItemSerializer(many=True)


class PriceComparisonRefreshSerializer(serializers.Serializer):
    """模擬重新抓價回應。"""

    detail = serializers.CharField()
    result = PriceComparisonSerializer()


# ---------------------------------------------------------------------------
# 社群 / 論壇
# ---------------------------------------------------------------------------
class CommunityReplySerializer(serializers.Serializer):
    """單筆社群文章回覆格式。"""
    id = serializers.IntegerField()
    author = serializers.CharField()
    author_user_id = serializers.IntegerField(required=False, allow_null=True)
    author_username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    body = serializers.CharField()
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)


class CommunityPostSerializer(serializers.Serializer):
    """社群文章主回應格式。

    除了文章內容，也會帶上：
    - 投票數
    - 回覆數 / 回覆清單
    - `can_edit` / `can_delete` 這類前端權限控制欄位
    """
    id = serializers.IntegerField()
    topic = serializers.CharField()
    author = serializers.CharField()
    author_user_id = serializers.IntegerField(required=False, allow_null=True)
    author_username = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    title = serializers.CharField()
    body = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    votes = serializers.IntegerField()
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)
    reply_count = serializers.IntegerField(required=False)
    replies = CommunityReplySerializer(many=True, required=False)
    can_edit = serializers.BooleanField(required=False)
    can_delete = serializers.BooleanField(required=False)


class CommunityPostListResponseSerializer(serializers.Serializer):
    """社群文章列表回應格式。"""
    items = CommunityPostSerializer(many=True)


class CommunityPostCreateSerializer(serializers.Serializer):
    """建立社群文章時的輸入格式。

    `tags` 目前仍沿用字串輸入，交由 service 再拆解成標籤列表。
    """
    topic = serializers.CharField(required=False, allow_blank=True, default="general")
    title = serializers.CharField(max_length=120)
    body = serializers.CharField()
    tags = serializers.CharField(required=False, allow_blank=True, default="")


class CommunityPostUpdateSerializer(CommunityPostCreateSerializer):
    """編輯社群文章時的輸入格式。

    欄位結構與建立文章相同，所以直接繼承 create serializer。
    """


class CommunityReplyCreateSerializer(serializers.Serializer):
    """建立社群回覆時的輸入格式。"""
    body = serializers.CharField()


class CommunityImageUploadSerializer(serializers.Serializer):
    """論壇富文本圖片上傳。"""

    image = serializers.FileField()


class VoteResponseSerializer(serializers.Serializer):
    """文章投票後的最小回應格式。

    前端只需要文章 id 與最新票數即可即時刷新 UI。
    """
    id = serializers.IntegerField()
    votes = serializers.IntegerField()


# ---------------------------------------------------------------------------
# 會員 / 地址 / 發票 / 運費
# ---------------------------------------------------------------------------
class DemoUserSerializer(serializers.Serializer):
    """目前 demo 會員 snapshot 的回應格式。

    主要供：
    - `/api/v1/me/`
    - `/api/v1/app/bootstrap/`
    - 會員中心與後台會員管理頁
    """
    id = serializers.IntegerField()
    username = serializers.CharField()
    display_name = serializers.CharField()
    role = serializers.CharField()
    account_status = serializers.CharField(required=False)
    seller_request_status = serializers.CharField(required=False, allow_blank=True)
    email = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.CharField(required=False, allow_blank=True)
    last_login_at = serializers.CharField(required=False, allow_blank=True)
    seller_requested_at = serializers.CharField(required=False, allow_blank=True)
    seller_reviewed_at = serializers.CharField(required=False, allow_blank=True)
    shipping_rules = serializers.DictField(required=False)


class MeResponseSerializer(serializers.Serializer):
    """目前登入會員資訊回應格式。

    `user` 可為 `null`，表示尚未登入。
    """
    user = DemoUserSerializer(allow_null=True)


class ToggleStateSerializer(serializers.Serializer):
    """收藏 / 比較切換後的通用回應格式。

    不同 API 會視情況帶上：
    - `removed_slug`：比較清單超上限時被擠掉的商品
    - `compare_slugs`：最新比較清單
    """
    active = serializers.BooleanField()
    slug = serializers.CharField()
    removed_slug = serializers.CharField(required=False, allow_blank=True)
    compare_slugs = serializers.ListField(child=serializers.CharField(), required=False)


class AddressSerializer(serializers.Serializer):
    """會員地址簿中的單筆地址格式。

    主要供：
    - 地址管理頁
    - checkout 地址選擇區塊
    """
    id = serializers.IntegerField()
    label = serializers.CharField()
    recipient = serializers.CharField()
    phone = serializers.CharField()
    city = serializers.CharField()
    district = serializers.CharField()
    postal_code = serializers.CharField(required=False, allow_blank=True)
    address_line = serializers.CharField()
    created_at = serializers.CharField(required=False)
    is_default = serializers.BooleanField(required=False)


class AddressCreateSerializer(serializers.Serializer):
    """建立或新增地址時的輸入格式。"""
    label = serializers.CharField(max_length=50)
    recipient = serializers.CharField(max_length=50)
    phone = serializers.CharField(max_length=30)
    city = serializers.CharField(max_length=50)
    district = serializers.CharField(max_length=50)
    postal_code = serializers.CharField(required=False, allow_blank=True, max_length=20)
    address_line = serializers.CharField(max_length=255)


class AddressListResponseSerializer(serializers.Serializer):
    """地址簿列表回應格式。"""
    items = AddressSerializer(many=True)


class InvoiceProfileSerializer(serializers.Serializer):
    """會員發票設定資料格式。"""
    invoice_type = serializers.CharField()
    carrier_code = serializers.CharField(required=False, allow_blank=True)
    company_name = serializers.CharField(required=False, allow_blank=True)
    tax_id = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.CharField(required=False)


class InvoiceProfileUpdateSerializer(serializers.Serializer):
    """更新會員發票資料時的輸入格式。"""
    invoice_type = serializers.ChoiceField(choices=["personal", "company"])
    carrier_code = serializers.CharField(required=False, allow_blank=True)
    company_name = serializers.CharField(required=False, allow_blank=True)
    tax_id = serializers.CharField(required=False, allow_blank=True)


class SellerShippingRulesSerializer(serializers.Serializer):
    """賣家運費規則資料格式。

    主要供賣家運費設定頁與商品運送規則覆寫邏輯使用。
    """

    home_delivery_enabled = serializers.BooleanField()
    home_delivery_fee = serializers.CharField()
    convenience_store_enabled = serializers.BooleanField()
    convenience_store_fee = serializers.CharField()
    free_shipping_threshold = serializers.CharField()


# ---------------------------------------------------------------------------
# 訂單 / 付款 / 出貨
# ---------------------------------------------------------------------------
class OrderServiceRequestCreateSerializer(serializers.Serializer):
    """建立取消 / 退款申請時的輸入格式。"""
    reason = serializers.CharField()


class ServiceRequestSerializer(serializers.Serializer):
    """訂單售後服務請求格式。

    用來描述取消 / 退款申請目前的狀態、原因與審核資訊。
    """
    type = serializers.CharField(allow_blank=True)
    status = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    created_at = serializers.CharField(allow_blank=True)
    reviewed_at = serializers.CharField(allow_blank=True)
    type_label = serializers.CharField(required=False, allow_blank=True)
    status_label = serializers.CharField(required=False, allow_blank=True)
    created_at_display = serializers.CharField(required=False, allow_blank=True)
    reviewed_at_display = serializers.CharField(required=False, allow_blank=True)
    is_pending = serializers.BooleanField(required=False)


class SellerLineSerializer(serializers.Serializer):
    """訂單中的單一賣家商品列格式。

    這份結構會同時出現在：
    - 買家訂單明細
    - 賣家訂單明細
    - 平台訂單明細
    """
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    display_name = serializers.CharField(required=False)
    price = serializers.FloatField()
    qty = serializers.IntegerField()
    variant_id = serializers.CharField(required=False, allow_blank=True)
    variant_name = serializers.CharField(required=False, allow_blank=True)
    sku = serializers.CharField(required=False, allow_blank=True)
    line_total = serializers.CharField()
    seller_user_id = serializers.IntegerField(required=False, allow_null=True)
    seller_username = serializers.CharField(required=False, allow_blank=True)
    seller_display_name = serializers.CharField(required=False, allow_blank=True)
    seller_status = serializers.CharField(required=False, allow_blank=True)
    seller_status_label = serializers.CharField(required=False, allow_blank=True)
    shipping_note = serializers.CharField(required=False, allow_blank=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    shipped_at_display = serializers.CharField(required=False, allow_blank=True)
    completed_at_display = serializers.CharField(required=False, allow_blank=True)


class ShipmentGroupSerializer(serializers.Serializer):
    """賣家出貨分組格式。

    用來把同一張訂單內屬於同一賣家的 item 合併展示成一組。
    """
    seller_username = serializers.CharField()
    seller_display_name = serializers.CharField()
    seller_status = serializers.CharField()
    seller_status_label = serializers.CharField()
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    shipping_note = serializers.CharField(required=False, allow_blank=True)
    shipped_at_display = serializers.CharField(required=False, allow_blank=True)
    completed_at_display = serializers.CharField(required=False, allow_blank=True)
    items = SellerLineSerializer(many=True)


class CheckoutChoiceSerializer(serializers.Serializer):
    """結帳頁的選項欄位。"""

    value = serializers.CharField()
    label = serializers.CharField()


class OrderSerializer(serializers.Serializer):
    """訂單主體回應格式。

    這是買家、賣家、管理端訂單頁共用的核心結構，
    會依視角附帶：
    - 收件資訊
    - 付款資訊
    - 超商門市資訊
    - 出貨分組
    - 售後申請
    """
    # 訂單主識別與買家資訊
    id = serializers.IntegerField()
    buyer_user_id = serializers.IntegerField(required=False, allow_null=True)
    username = serializers.CharField()
    display_name = serializers.CharField()

    # 訂單與付款 / 履約狀態摘要
    status = serializers.CharField()
    status_label = serializers.CharField(required=False)
    coupon = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    created_at = serializers.CharField()
    created_at_display = serializers.CharField(required=False)
    buyer_email = serializers.CharField(required=False, allow_blank=True)
    item_count = serializers.IntegerField(required=False)
    totals = serializers.DictField(required=False)
    seller_totals = serializers.DictField(required=False)
    shipment_summary = serializers.CharField(required=False, allow_blank=True)
    seller_status = serializers.CharField(required=False, allow_blank=True)
    seller_status_label = serializers.CharField(required=False, allow_blank=True)
    shipping_note = serializers.CharField(required=False, allow_blank=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)
    shipped_at_display = serializers.CharField(required=False, allow_blank=True)
    completed_at_display = serializers.CharField(required=False, allow_blank=True)

    # 收件 / 配送 / 付款資訊 snapshot
    shipping_address = serializers.DictField(required=False)
    shipping_method = serializers.CharField(required=False, allow_blank=True)
    shipping_method_label = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField(required=False, allow_blank=True)
    payment_method_label = serializers.CharField(required=False, allow_blank=True)
    pickup_store_brand = serializers.CharField(required=False, allow_blank=True)
    pickup_store_brand_label = serializers.CharField(required=False, allow_blank=True)
    pickup_store_code = serializers.CharField(required=False, allow_blank=True)
    pickup_store_name = serializers.CharField(required=False, allow_blank=True)
    pickup_store_address = serializers.CharField(required=False, allow_blank=True)
    invoice_profile = serializers.DictField(required=False)
    buyer_note = serializers.CharField(required=False, allow_blank=True)

    # 售後與明細區塊
    service_request = ServiceRequestSerializer(required=False)
    can_request_cancel = serializers.BooleanField(required=False)
    can_request_refund = serializers.BooleanField(required=False)
    seller_count = serializers.IntegerField(required=False)
    items = SellerLineSerializer(many=True, required=False)
    shipment_groups = ShipmentGroupSerializer(many=True, required=False)


class OrderListResponseSerializer(serializers.Serializer):
    """OrderListResponseSerializer。
    
    負責定義 API 回應結構，讓前端可以穩定取得固定欄位。
    """
    items = OrderSerializer(many=True)


class NewebpayPaymentCreateSerializer(serializers.Serializer):
    """藍新支付 mock 建單請求。"""

    return_url = serializers.CharField(required=False, allow_blank=True)
    client_back_url = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)


class NewebpayPaymentRecordSerializer(serializers.Serializer):
    """藍新付款紀錄格式。

    用來描述一筆已建立或已收到 callback 的 payment record，
    供買家頁與 staff debug 顯示。
    """

    # 交易來源與識別
    provider = serializers.CharField()
    mode = serializers.CharField()
    order_id = serializers.IntegerField()
    buyer_username = serializers.CharField()
    merchant_order_no = serializers.CharField()
    trade_no = serializers.CharField()

    # 交易狀態與金額
    status = serializers.CharField()
    status_label = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.CharField()
    currency = serializers.CharField()

    # 回前端 / 回商店相關網址
    payment_url = serializers.CharField()
    return_url = serializers.CharField(required=False, allow_blank=True)
    client_back_url = serializers.CharField(required=False, allow_blank=True)

    # 建立、更新與 callback 歷程
    created_at = serializers.CharField()
    updated_at = serializers.CharField()
    paid_at = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    callback_count = serializers.IntegerField()
    raw_payload = serializers.DictField(required=False)


# ---------------------------------------------------------------------------
# 平台報表 / 管理端查詢
# ---------------------------------------------------------------------------
class SellerOrderUpdateSerializer(serializers.Serializer):
    """SellerOrderUpdateSerializer。
    
    負責驗證更新資料時需要的輸入欄位。
    """
    seller_status = serializers.CharField()
    shipping_note = serializers.CharField(required=False, allow_blank=True)
    tracking_number = serializers.CharField(required=False, allow_blank=True)


class SalesReportSerializer(serializers.Serializer):
    """賣家銷售報表格式。"""
    order_count = serializers.IntegerField()
    units_sold = serializers.IntegerField()
    revenue = serializers.CharField()
    status_counts = serializers.DictField()
    top_products = serializers.ListField(child=serializers.DictField())
    filters = serializers.DictField()


class DashboardSummarySerializer(serializers.Serializer):
    """DashboardSummarySerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    user = DemoUserSerializer()
    review_count = serializers.IntegerField()
    question_count = serializers.IntegerField()
    answer_count = serializers.IntegerField()
    post_count = serializers.IntegerField()
    order_count = serializers.IntegerField()
    favorite_products = ProductSerializer(many=True)
    recent_products = ProductSerializer(many=True)
    owned_products = ProductSerializer(many=True)


class AdminDashboardSerializer(serializers.Serializer):
    """後台儀表板摘要格式。"""
    users = serializers.DictField()
    products = serializers.DictField()
    orders = serializers.DictField()
    content = serializers.DictField()
    recent_reviews = serializers.ListField(child=serializers.DictField())
    recent_questions = serializers.ListField(child=serializers.DictField())
    recent_posts = serializers.ListField(child=serializers.DictField())


class AdminUserStatusUpdateSerializer(serializers.Serializer):
    """AdminUserStatusUpdateSerializer。
    
    負責驗證更新資料時需要的輸入欄位。
    """
    account_status = serializers.ChoiceField(choices=["active", "suspended"])


class UserListResponseSerializer(serializers.Serializer):
    """UserListResponseSerializer。
    
    負責定義 API 回應結構，讓前端可以穩定取得固定欄位。
    """
    items = DemoUserSerializer(many=True)


class SearchUserQuerySerializer(serializers.Serializer):
    """SearchUserQuerySerializer。
    
    負責驗證查詢參數，避免 view 直接處理未整理的 request.GET。
    """
    q = serializers.CharField(required=False, allow_blank=True)
    role = serializers.CharField(required=False, allow_blank=True)
    account_status = serializers.CharField(required=False, allow_blank=True)


class SellerOrdersQuerySerializer(serializers.Serializer):
    """SellerOrdersQuerySerializer。
    
    負責驗證查詢參數，避免 view 直接處理未整理的 request.GET。
    """
    date_from = serializers.CharField(required=False, allow_blank=True)
    date_to = serializers.CharField(required=False, allow_blank=True)


class AdminOrdersQuerySerializer(serializers.Serializer):
    """AdminOrdersQuerySerializer。
    
    負責驗證查詢參數，避免 view 直接處理未整理的 request.GET。
    """
    date_from = serializers.CharField(required=False, allow_blank=True)
    date_to = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    service_status = serializers.CharField(required=False, allow_blank=True)
    q = serializers.CharField(required=False, allow_blank=True)


class AdminProductsQuerySerializer(serializers.Serializer):
    """後台商品管理列表的查詢條件。"""

    q = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.CharField(required=False, allow_blank=True)
    owner = serializers.CharField(required=False, allow_blank=True)


class ProductPriceCompareSettingsSerializer(serializers.Serializer):
    """管理端商品比價開關與搜尋關鍵字。"""

    enabled = serializers.BooleanField(required=False, default=False)
    query = serializers.CharField(required=False, allow_blank=True, default="")


class AdminReviewsQuerySerializer(serializers.Serializer):
    """後台評論審核列表的查詢條件。"""

    q = serializers.CharField(required=False, allow_blank=True)
    rating = serializers.CharField(required=False, allow_blank=True)


class AdminQuestionsQuerySerializer(serializers.Serializer):
    """後台問答管理列表的查詢條件。"""

    q = serializers.CharField(required=False, allow_blank=True)
    answered = serializers.CharField(required=False, allow_blank=True)


class AdminPostsQuerySerializer(serializers.Serializer):
    """後台社群文章管理列表的查詢條件。"""

    q = serializers.CharField(required=False, allow_blank=True)
    topic = serializers.CharField(required=False, allow_blank=True)


class ServiceReviewSerializer(serializers.Serializer):
    """ServiceReviewSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    approved = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True)


class SessionMessageSerializer(serializers.Serializer):
    """SessionMessageSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    detail = serializers.CharField()
    user = DemoUserSerializer(allow_null=True)


class CsrfResponseSerializer(serializers.Serializer):
    """CSRF bootstrap API 回傳格式。"""

    detail = serializers.CharField()
    csrfToken = serializers.CharField()


class AppBootstrapSerializer(serializers.Serializer):
    """前端啟動畫面常用的全域狀態。"""

    user = DemoUserSerializer(allow_null=True)
    cart_count = serializers.IntegerField()
    compare_count = serializers.IntegerField()
    favorite_count = serializers.IntegerField()


class BannerSerializer(serializers.Serializer):
    """首頁宣傳 banner。"""

    id = serializers.IntegerField()
    title = serializers.CharField(required=False, allow_blank=True)
    copy_text = serializers.CharField(required=False, allow_blank=True)
    image_path = serializers.CharField()
    link_url = serializers.CharField(required=False, allow_blank=True)
    starts_at = serializers.CharField(required=False, allow_blank=True)
    ends_at = serializers.CharField(required=False, allow_blank=True)
    position = serializers.CharField(required=False, allow_blank=True)
    position_label = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField()
    status = serializers.CharField(required=False, allow_blank=True)
    status_label = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField()
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    applicant_user_id = serializers.IntegerField(required=False, allow_null=True)
    applicant_username = serializers.CharField(required=False, allow_blank=True)
    applicant_display_name = serializers.CharField(required=False, allow_blank=True)
    reviewed_at = serializers.CharField(required=False, allow_blank=True)
    reviewed_by_username = serializers.CharField(required=False, allow_blank=True)
    reviewed_by_display_name = serializers.CharField(required=False, allow_blank=True)
    created_at = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.CharField(required=False, allow_blank=True)
    is_currently_visible = serializers.BooleanField(required=False)


class BannerListResponseSerializer(serializers.Serializer):
    """Banner 列表回應。"""

    items = BannerSerializer(many=True)


class BannerApplicationCreateSerializer(serializers.Serializer):
    """會員提交 banner 申請。"""

    title = serializers.CharField(required=False, allow_blank=True, max_length=120)
    copy_text = serializers.CharField(required=False, allow_blank=True)
    link_url = serializers.CharField(required=False, allow_blank=True, max_length=255)
    starts_at = serializers.DateField()
    ends_at = serializers.DateField()
    position = serializers.CharField(required=False, allow_blank=True, default="home_main")
    note = serializers.CharField(required=False, allow_blank=True)
    image = serializers.FileField()


class AdminBannerCreateSerializer(BannerApplicationCreateSerializer):
    """管理者直接建立已通過 banner。"""

    is_active = serializers.BooleanField(required=False, default=True)


class AdminBannerUpdateSerializer(serializers.Serializer):
    """更新 banner。"""

    title = serializers.CharField(required=False, allow_blank=True, max_length=120, default="")
    copy_text = serializers.CharField(required=False, allow_blank=True, default="")
    link_url = serializers.CharField(required=False, allow_blank=True, max_length=255, default="")
    starts_at = serializers.DateField(required=False)
    ends_at = serializers.DateField(required=False)
    position = serializers.CharField(required=False, allow_blank=True, default="home_main")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False, default=True)
    sort_order = serializers.IntegerField(required=False, min_value=1, default=1)
    image = serializers.FileField(required=False)


class AdminBannerReviewSerializer(serializers.Serializer):
    """審核 banner 申請。"""

    approved = serializers.BooleanField()
    rejection_reason = serializers.CharField(required=False, allow_blank=True)


class AdminBannerReorderSerializer(serializers.Serializer):
    """更新 banner 排序。"""

    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)


class LoginRequestSerializer(serializers.Serializer):
    """LoginRequestSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    username = serializers.CharField()
    password = serializers.CharField()


class RegisterRequestSerializer(serializers.Serializer):
    """RegisterRequestSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    username = serializers.CharField()
    display_name = serializers.CharField()
    email = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField()
    password_confirm = serializers.CharField()


class ProfileUpdateSerializer(serializers.Serializer):
    """ProfileUpdateSerializer。
    
    負責驗證更新資料時需要的輸入欄位。
    """
    display_name = serializers.CharField()
    email = serializers.CharField(required=False, allow_blank=True)
    new_password = serializers.CharField(required=False, allow_blank=True)
    confirm_password = serializers.CharField(required=False, allow_blank=True)


class SellerRequestDecisionSerializer(serializers.Serializer):
    """SellerRequestDecisionSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    approved = serializers.BooleanField()


class ProductReviewDecisionSerializer(serializers.Serializer):
    """ProductReviewDecisionSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    approved = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# 購物車 / Checkout
# 這一段是前台交易主流程最常用到的 serializer。
# ---------------------------------------------------------------------------
class CartItemSerializer(serializers.Serializer):
    """購物車單項格式。

    用來描述一筆 cart line，包括商品、變體、數量與行小計。
    """
    key = serializers.CharField()
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    display_name = serializers.CharField()
    price = serializers.FloatField()
    qty = serializers.IntegerField()
    variant_id = serializers.CharField(required=False, allow_blank=True)
    variant_name = serializers.CharField(required=False, allow_blank=True)
    sku = serializers.CharField(required=False, allow_blank=True)
    line_total = serializers.FloatField()


class CartTotalsSerializer(serializers.Serializer):
    """購物車 / checkout 使用的金額摘要格式。"""
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2)
    shipping = serializers.DecimalField(max_digits=10, decimal_places=2)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total = serializers.DecimalField(max_digits=10, decimal_places=2)


class CartResponseSerializer(serializers.Serializer):
    """購物車頁主要回應格式。

    供前端一次拿到：
    - items
    - totals
    - 運送方式
    - 分賣家運費資訊
    """
    # cart line items
    items = CartItemSerializer(many=True)
    coupon = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    item_count = serializers.IntegerField()

    # 金額與結帳選項
    totals = CartTotalsSerializer()
    shipping_methods = CheckoutChoiceSerializer(many=True, required=False)
    selected_shipping_method = serializers.CharField(required=False, allow_blank=True)

    # 分賣家運費資訊與提示訊息
    seller_shipping_groups = serializers.ListField(child=serializers.DictField(), required=False)
    detail = serializers.CharField(required=False)


class CartCouponSerializer(serializers.Serializer):
    """套用或清除購物車折扣碼時的輸入格式。

    `code` 可為空值，代表清除目前折扣碼。
    """
    code = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class CartAddSerializer(serializers.Serializer):
    """加入購物車時的輸入格式。

    `variant_id` 為可選，表示這筆商品可能是單一規格商品。
    """
    slug = serializers.CharField()
    qty = serializers.IntegerField(required=False, min_value=1, default=1)
    variant_id = serializers.CharField(required=False, allow_blank=True)


class CartUpdateSerializer(serializers.Serializer):
    """更新購物車單項數量時的輸入格式。

    `qty=0` 代表把該項目移除。
    """
    qty = serializers.IntegerField(min_value=0)


class CheckoutPreviewSerializer(serializers.Serializer):
    """checkout 頁預覽資料格式。

    這是前端繪製 checkout 畫面時最完整的一包 snapshot。
    """
    # 購物車摘要
    items = CartItemSerializer(many=True)
    coupon = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    item_count = serializers.IntegerField()
    totals = CartTotalsSerializer()

    # 會員結帳資料
    addresses = AddressSerializer(many=True, required=False)
    default_address = serializers.DictField(required=False, allow_null=True)
    invoice_profile = serializers.DictField(required=False)

    # 可選的配送 / 付款 / 超商品牌
    shipping_methods = CheckoutChoiceSerializer(many=True, required=False)
    payment_methods = CheckoutChoiceSerializer(many=True, required=False)
    convenience_store_brands = CheckoutChoiceSerializer(many=True, required=False)
    selected_address_id = serializers.IntegerField(required=False, allow_null=True)
    selected_shipping_method = serializers.CharField(required=False, allow_blank=True)
    selected_payment_method = serializers.CharField(required=False, allow_blank=True)

    # 其他前端控制欄位
    seller_shipping_groups = serializers.ListField(child=serializers.DictField(), required=False)
    user = DemoUserSerializer(required=False, allow_null=True)
    requires_login = serializers.BooleanField()
    can_confirm = serializers.BooleanField()


class CheckoutConfirmSerializer(serializers.Serializer):
    """確認下單時提交的欄位。

    這份 payload 同時涵蓋：
    - 宅配地址結帳
    - 超商取貨結帳
    - 藍新付款必要欄位
    """

    address_id = serializers.IntegerField(required=False, allow_null=True)
    shipping_method = serializers.ChoiceField(
        choices=[
            "home_delivery",
            "convenience_store",
        ],
        required=False,
        default="home_delivery",
    )
    pickup_store_brand = serializers.CharField(required=False, allow_blank=True)
    pickup_store_code = serializers.CharField(required=False, allow_blank=True)
    pickup_store_name = serializers.CharField(required=False, allow_blank=True)
    pickup_store_address = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=[
            "newebpay",
        ],
        required=False,
        default="newebpay",
    )
    buyer_note = serializers.CharField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# 賣家商品寫入 / staff review / NewebPay store map
# ---------------------------------------------------------------------------
class StatusChoiceSerializer(serializers.Serializer):
    """StatusChoiceSerializer。
    
    DRF Serializer，用來驗證請求資料或整理 API 回應格式。
    """
    value = serializers.CharField()
    label = serializers.CharField()


class SellerProductWriteSerializer(serializers.Serializer):
    """賣家商品建立 / 更新表單格式。

    對應賣家商品新增頁與編輯頁送出的欄位。
    """
    # 商品主資料
    name = serializers.CharField()
    price = serializers.CharField()
    compare_at_price = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.CharField()
    category = serializers.CharField()
    tags = serializers.CharField(required=False, allow_blank=True)
    specs = serializers.CharField(required=False, allow_blank=True)
    variants = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, allow_blank=True)
    stock = serializers.CharField(required=False, allow_blank=True)

    # 商品運送規則設定
    use_seller_shipping_rules = serializers.CharField(required=False, allow_blank=True)
    allow_home_delivery = serializers.CharField(required=False, allow_blank=True)
    allow_convenience_store = serializers.CharField(required=False, allow_blank=True)
    override_home_delivery_fee = serializers.CharField(required=False, allow_blank=True)
    override_convenience_store_fee = serializers.CharField(required=False, allow_blank=True)

    # 前端編輯商品圖片時的保留 / 移除清單
    existing_image_paths = serializers.ListField(child=serializers.CharField(), required=False)
    remove_image_paths = serializers.ListField(child=serializers.CharField(), required=False)


class SellerProductListResponseSerializer(serializers.Serializer):
    """SellerProductListResponseSerializer。
    
    負責定義 API 回應結構，讓前端可以穩定取得固定欄位。
    """
    items = ProductSerializer(many=True)
    status_choices = StatusChoiceSerializer(many=True)


class StaffReviewDashboardSerializer(serializers.Serializer):
    """staff review dashboard 的回應格式。"""
    managed_products = ProductSerializer(many=True)
    seller_requests = DemoUserSerializer(many=True)


class ProductForceArchiveSerializer(serializers.Serializer):
    """管理者強制下架商品時可帶的附註。"""

    note = serializers.CharField(required=False, allow_blank=True)


class NewebpaySandboxPaymentPrepareSerializer(serializers.Serializer):
    """藍新正式 sandbox 支付準備參數。"""

    item_desc_override = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    notify_url = serializers.CharField(required=False, allow_blank=True)
    return_url = serializers.CharField(required=False, allow_blank=True)
    client_back_url = serializers.CharField(required=False, allow_blank=True)


class NewebpaySandboxPaymentPreparedSerializer(serializers.Serializer):
    """藍新 sandbox form post payload。

    前端會用這份資料建立 auto-submit form，導頁到藍新 gateway。
    """

    # 平台與訂單辨識
    provider = serializers.CharField()
    mode = serializers.CharField()
    order_id = serializers.IntegerField()
    buyer_username = serializers.CharField()
    merchant_order_no = serializers.CharField()

    # 前端真正送往藍新的 gateway 設定
    gateway_url = serializers.CharField()
    form_method = serializers.CharField()

    # staff debug 可讀的明文 / 密文欄位
    trade_info_params = serializers.DictField()
    form_fields = serializers.DictField()
    note = serializers.CharField()


class NewebpaySandboxPaymentCallbackSerializer(serializers.Serializer):
    """藍新支付 sandbox callback 原始欄位。"""

    Status = serializers.CharField()
    MerchantID = serializers.CharField()
    TradeInfo = serializers.CharField()
    TradeSha = serializers.CharField()


class CheckoutStoreMapPrepareSerializer(serializers.Serializer):
    """準備藍新超商選店 payload 時的輸入格式。

    前端會先送這份資料到本站，再由後端組出實際送往藍新的表單欄位。
    """

    pickup_store_brand = serializers.CharField()
    payment_method = serializers.CharField(required=False, allow_blank=True)
    return_url = serializers.CharField(required=False, allow_blank=True)


class CheckoutStoreMapPreparedSerializer(serializers.Serializer):
    """藍新 store-map 自動送出 payload 的回應格式。

    這份資料主要給前端建立一個隱藏 form 並自動 submit。
    除了送單欄位，也保留 debug 用的明文參數。
    """

    # 基本識別資訊
    provider = serializers.CharField()
    mode = serializers.CharField()
    selection_token = serializers.CharField()
    buyer_username = serializers.CharField()
    pickup_store_brand = serializers.CharField()
    pickup_store_brand_label = serializers.CharField()
    payment_method = serializers.CharField(required=False, allow_blank=True)
    merchant_order_no = serializers.CharField()

    # 實際送往藍新的表單資訊
    action_url = serializers.CharField()
    form_method = serializers.CharField()
    callback_url = serializers.CharField()
    return_url = serializers.CharField()

    # debug / 檢查用途
    plain_params = serializers.DictField()
    form_fields = serializers.DictField()
    note = serializers.CharField()


class CheckoutStoreSelectionSerializer(serializers.Serializer):
    """checkout 回填超商門市時使用的資料格式。

    checkout 頁會依 `is_ready` 判斷是否已拿到完整門市資訊。
    """

    selection_token = serializers.CharField()
    status = serializers.CharField()
    is_ready = serializers.BooleanField()
    pickup_store_brand = serializers.CharField(required=False, allow_blank=True)
    pickup_store_brand_label = serializers.CharField(required=False, allow_blank=True)
    pickup_store_code = serializers.CharField(required=False, allow_blank=True)
    pickup_store_name = serializers.CharField(required=False, allow_blank=True)
    pickup_store_address = serializers.CharField(required=False, allow_blank=True)
    merchant_order_no = serializers.CharField(required=False, allow_blank=True)
    updated_at = serializers.CharField(required=False, allow_blank=True)


class NewebpayStoreMapCallbackSerializer(serializers.Serializer):
    """藍新 store-map callback 原始欄位。"""

    MerchantID = serializers.CharField(required=False, allow_blank=True)
    MerchantOrderNo = serializers.CharField(required=False, allow_blank=True)
    StoreID = serializers.CharField(required=False, allow_blank=True)
    StoreName = serializers.CharField(required=False, allow_blank=True)
    StoreAddr = serializers.CharField(required=False, allow_blank=True)
    StoreType = serializers.CharField(required=False, allow_blank=True)
    ExtraData = serializers.CharField(required=False, allow_blank=True)
    Status = serializers.CharField(required=False, allow_blank=True)

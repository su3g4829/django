"""Store 專案的 canonical DRF API 路由表。

來源模組：
- `django.urls.path`
- `drf_spectacular` 文件 view
- `myapp.api.views` 內的 APIView

用途：
- 集中維護 `/api/v1/...` 的正式 API 路由
- 讓前端頁面、service、文件頁都能對照同一份 canonical route
- 避免舊 alias 或零散路由讓 API 邊界變得不清楚
"""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

urlpatterns = [
    # ------------------------------------------------------------------
    # OpenAPI / API 文件
    # 給開發者查看 schema、Swagger UI、ReDoc。
    # 不直接參與前台業務功能。
    # ------------------------------------------------------------------
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),

    # ------------------------------------------------------------------
    # Auth / session / app bootstrap / 公開初始化資料
    # 對應：
    # - 登入 / 註冊 / 登出頁
    # - Next.js app 啟動時的 bootstrap
    # - 首頁 banner 與公開商品分類主表
    # ------------------------------------------------------------------
    path("auth/csrf/", views.AuthCsrfApi.as_view(), name="api-auth-csrf"),
    path("auth/login/", views.LoginApi.as_view(), name="api-login"),
    path("auth/register/", views.RegisterApi.as_view(), name="api-register"),
    path("auth/logout/", views.LogoutApi.as_view(), name="api-logout"),
    path("app/bootstrap/", views.AppBootstrapApi.as_view(), name="api-app-bootstrap"),
    path("banners/", views.BannerListApi.as_view(), name="api-banners"),
    path("product-categories/", views.ProductCategoriesApi.as_view(), name="api-product-categories"),

    # ------------------------------------------------------------------
    # Member center / buyer account / seller center
    # 對應：
    # - 會員中心首頁 / 會員資料 / 地址 / 發票 / 賣家申請
    # - 買家訂單列表與明細
    # - 賣家訂單列表、明細、銷售報表
    # ------------------------------------------------------------------
    path("me/", views.MeApi.as_view(), name="api-me"),
    path("me/profile/", views.MeProfileApi.as_view(), name="api-me-profile"),
    path("me/shipping-rules/", views.MeShippingRulesApi.as_view(), name="api-me-shipping-rules"),
    path("me/dashboard/", views.MeDashboardApi.as_view(), name="api-me-dashboard"),
    path("me/banner-applications/", views.MeBannerApplicationsApi.as_view(), name="api-me-banner-applications"),
    path("me/seller-request/", views.SellerRequestApi.as_view(), name="api-me-seller-request"),
    path("me/addresses/", views.MeAddressesApi.as_view(), name="api-me-addresses"),
    path("me/addresses/<int:address_id>/default/", views.MeAddressDefaultApi.as_view(), name="api-me-address-default"),
    path("me/addresses/<int:address_id>/", views.MeAddressDeleteApi.as_view(), name="api-me-address-delete"),
    path("me/invoice/", views.MeInvoiceApi.as_view(), name="api-me-invoice"),
    path("me/orders/", views.BuyerOrdersApi.as_view(), name="api-buyer-orders"),
    path("me/orders/<int:order_id>/", views.BuyerOrderDetailApi.as_view(), name="api-buyer-order-detail"),
    path("me/orders/<int:order_id>/cancel-request/", views.BuyerCancelRequestApi.as_view(), name="api-buyer-order-cancel-request"),
    path("me/orders/<int:order_id>/refund-request/", views.BuyerRefundRequestApi.as_view(), name="api-buyer-order-refund-request"),
    path("me/orders/<int:order_id>/complete/", views.BuyerOrderCompleteApi.as_view(), name="api-buyer-order-complete"),
    path("me/orders/<int:order_id>/newebpay-payment/", views.BuyerNewebpayPaymentApi.as_view(), name="api-buyer-newebpay-payment"),
    path(
        "me/orders/<int:order_id>/newebpay-payment/sandbox/",
        views.BuyerNewebpaySandboxPaymentPrepareApi.as_view(),
        name="api-buyer-newebpay-payment-sandbox",
    ),
    path("me/sales/", views.SellerOrdersApi.as_view(), name="api-seller-orders"),
    path("me/sales/report/", views.SellerSalesReportApi.as_view(), name="api-seller-sales-report"),
    path("me/sales/<int:order_id>/", views.SellerOrderDetailApi.as_view(), name="api-seller-order-detail"),
    path("me/sales/<int:order_id>/update/", views.SellerOrderUpdateApi.as_view(), name="api-seller-order-update"),

    # ------------------------------------------------------------------
    # Seller product management
    # 對應：
    # - 賣家商品列表
    # - 賣家新增商品頁
    # - 賣家商品編輯 / 下架 / 複製
    # ------------------------------------------------------------------
    path("me/products/", views.SellerProductsApi.as_view(), name="api-seller-products"),
    path("me/products/<slug:slug>/", views.SellerProductDetailApi.as_view(), name="api-seller-product-detail"),
    path("me/products/<slug:slug>/archive/", views.SellerProductArchiveApi.as_view(), name="api-seller-product-archive"),
    path("me/products/<slug:slug>/duplicate/", views.SellerProductDuplicateApi.as_view(), name="api-seller-product-duplicate"),

    # ------------------------------------------------------------------
    # Cart / checkout / NewebPay integrations
    # 對應：
    # - 購物車頁
    # - checkout 頁
    # - 買家訂單頁的前往藍新付款
    # - staff NewebPay debug / store-map debug
    #
    # 這一組同時包含：
    # - cart CRUD
    # - checkout preview / confirm
    # - 超商地圖選店 flow
    # - NewebPay payment callback / return
    # ------------------------------------------------------------------
    path("cart/", views.CartApi.as_view(), name="api-cart"),
    path("cart/items/", views.CartAddApi.as_view(), name="api-cart-add"),
    path("cart/items/<path:item_key>/", views.CartItemApi.as_view(), name="api-cart-item"),
    path("checkout/preview/", views.CheckoutPreviewApi.as_view(), name="api-checkout-preview"),
    path("checkout/confirm/", views.CheckoutConfirmApi.as_view(), name="api-checkout-confirm"),
    path(
        "checkout/logistics/store-map/prepare/",
        views.BuyerCheckoutStoreMapPrepareApi.as_view(),
        name="api-checkout-store-map-prepare",
    ),
    path(
        "staff/integrations/newebpay/logistics/store-map/debug/",
        views.AdminCheckoutStoreMapDebugApi.as_view(),
        name="api-admin-checkout-store-map-debug",
    ),
    path(
        "checkout/logistics/store-selection/",
        views.BuyerCheckoutStoreSelectionApi.as_view(),
        name="api-checkout-store-selection",
    ),
    path(
        "integrations/newebpay/logistics/store-map/callback/",
        views.NewebpayStoreMapCallbackApi.as_view(),
        name="api-newebpay-logistics-store-map-callback",
    ),
    path(
        "integrations/newebpay/payment/sandbox/callback/",
        views.NewebpaySandboxPaymentCallbackApi.as_view(),
        name="api-newebpay-payment-sandbox-callback",
    ),
    path(
        "integrations/newebpay/payment/sandbox/return/",
        views.NewebpaySandboxPaymentReturnApi.as_view(),
        name="api-newebpay-payment-sandbox-return",
    ),

    # ------------------------------------------------------------------
    # Staff / admin / moderation
    # 對應：
    # - staff dashboard
    # - staff 訂單 / 商品 / 會員 / Banner / 內容管理
    # - staff 審核中心與 payment debug
    # ------------------------------------------------------------------
    path("staff/reviews/", views.StaffReviewDashboardApi.as_view(), name="api-admin-review-dashboard"),
    path("staff/dashboard/", views.AdminDashboardApi.as_view(), name="api-admin-dashboard"),
    path("staff/banners/", views.AdminBannersApi.as_view(), name="api-admin-banners"),
    path("staff/banners/reorder/", views.AdminBannerReorderApi.as_view(), name="api-admin-banners-reorder"),
    path("staff/banners/<int:banner_id>/review/", views.AdminBannerReviewApi.as_view(), name="api-admin-banner-review"),
    path("staff/banners/<int:banner_id>/", views.AdminBannerDetailApi.as_view(), name="api-admin-banner-detail"),
    path("staff/orders/", views.AdminOrdersApi.as_view(), name="api-admin-orders"),
    path("staff/orders/<int:order_id>/", views.AdminOrderDetailApi.as_view(), name="api-admin-order-detail"),
    path(
        "staff/orders/<int:order_id>/payment-debug/",
        views.AdminOrderPaymentDebugApi.as_view(),
        name="api-admin-order-payment-debug",
    ),
    path("staff/orders/<int:order_id>/service-review/", views.AdminOrderServiceReviewApi.as_view(), name="api-admin-order-service-review"),
    path("staff/users/", views.AdminUsersApi.as_view(), name="api-admin-users"),
    path("staff/products/", views.AdminProductsApi.as_view(), name="api-admin-products"),
    path(
        "staff/products/<slug:slug>/price-compare-settings/",
        views.AdminProductPriceCompareSettingsApi.as_view(),
        name="api-admin-product-price-compare-settings",
    ),
    path("staff/product-categories/", views.AdminProductCategoriesApi.as_view(), name="api-admin-product-categories"),
    path("staff/products/<slug:slug>/publish/", views.AdminProductPublishApi.as_view(), name="api-admin-product-publish"),
    path("staff/users/<slug:username>/status/", views.AdminUserStatusApi.as_view(), name="api-admin-user-status"),
    path("staff/products/<slug:slug>/", views.AdminProductDeleteApi.as_view(), name="api-admin-product-delete"),
    path("staff/content/reviews/", views.AdminReviewsApi.as_view(), name="api-admin-content-reviews"),
    path("staff/content/reviews/<int:review_id>/", views.AdminReviewDetailApi.as_view(), name="api-admin-content-review-detail"),
    path("staff/content/questions/", views.AdminQuestionsApi.as_view(), name="api-admin-content-questions"),
    path("staff/content/questions/<int:question_id>/", views.AdminQuestionDetailApi.as_view(), name="api-admin-content-question-detail"),
    path("staff/content/posts/", views.AdminPostsApi.as_view(), name="api-admin-content-posts"),
    path("staff/content/posts/<int:post_id>/", views.AdminPostDetailApi.as_view(), name="api-admin-content-post-detail"),
    path(
        "staff/seller-requests/<slug:username>/review/",
        views.SellerRequestReviewApi.as_view(),
        name="api-admin-seller-request-review",
    ),
    path("staff/products/<slug:slug>/archive/", views.AdminProductArchiveApi.as_view(), name="api-admin-product-archive"),

    # ------------------------------------------------------------------
    # Product browsing / interaction / price compare
    # 對應：
    # - 商品總覽頁
    # - 商品詳情頁
    # - 商品比較頁
    # - 商品評論 / 問答 / 推薦 / 收藏 / 比價
    # ------------------------------------------------------------------
    path("products/", views.ProductListApi.as_view(), name="api-products"),
    path("products/compare/", views.CompareListApi.as_view(), name="api-product-compare-list"),
    path("products/<slug:slug>/", views.ProductDetailApi.as_view(), name="api-product-detail"),
    path("products/<slug:slug>/favorite/", views.FavoriteToggleApi.as_view(), name="api-product-favorite-toggle"),
    path("products/<slug:slug>/compare/", views.CompareToggleApi.as_view(), name="api-product-compare-toggle"),
    path("products/<slug:slug>/reviews/", views.ProductReviewsApi.as_view(), name="api-product-reviews"),
    path("products/<slug:slug>/questions/", views.ProductQuestionsApi.as_view(), name="api-product-questions"),
    path("products/<slug:slug>/questions/<int:question_id>/answers/", views.ProductAnswersApi.as_view(), name="api-product-answers"),
    path("products/<slug:slug>/recommendations/", views.ProductRecommendationsApi.as_view(), name="api-product-recommendations"),
    path("products/<slug:slug>/price-compare/", views.ProductPriceCompareApi.as_view(), name="api-product-price-compare"),
    path("products/<slug:slug>/price-compare/refresh/", views.ProductPriceCompareRefreshApi.as_view(), name="api-product-price-compare-refresh"),

    # ------------------------------------------------------------------
    # Community / forum
    # 對應：
    # - 社群文章列表
    # - 社群文章詳情頁
    # - 回覆 / 投票 / 內文圖片上傳
    # ------------------------------------------------------------------
    path("community/posts/", views.CommunityPostsApi.as_view(), name="api-community-posts"),
    path("community/uploads/images/", views.CommunityImageUploadApi.as_view(), name="api-community-image-upload"),
    path("community/posts/<int:post_id>/", views.CommunityPostDetailApi.as_view(), name="api-community-post-detail"),
    path("community/posts/<int:post_id>/replies/", views.CommunityRepliesApi.as_view(), name="api-community-replies"),
    path("community/posts/<int:post_id>/vote/", views.CommunityVoteApi.as_view(), name="api-community-vote"),
]

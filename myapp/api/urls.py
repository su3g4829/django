"""DRF canonical API 路由。"""

from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

urlpatterns = [
    # OpenAPI / Swagger
    path("schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-swagger-ui"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="api-schema"), name="api-redoc"),

    # Auth / session / app bootstrap
    path("auth/csrf/", views.AuthCsrfApi.as_view(), name="api-auth-csrf"),
    path("auth/login/", views.LoginApi.as_view(), name="api-login"),
    path("auth/register/", views.RegisterApi.as_view(), name="api-register"),
    path("auth/logout/", views.LogoutApi.as_view(), name="api-logout"),
    path("app/bootstrap/", views.AppBootstrapApi.as_view(), name="api-app-bootstrap"),

    # 會員中心
    path("me/", views.MeApi.as_view(), name="api-me"),
    path("me/profile/", views.MeProfileApi.as_view(), name="api-me-profile"),
    path("me/dashboard/", views.MeDashboardApi.as_view(), name="api-me-dashboard"),
    path("me/seller-request/", views.SellerRequestApi.as_view(), name="api-me-seller-request"),
    path("me/addresses/", views.MeAddressesApi.as_view(), name="api-me-addresses"),
    path("me/addresses/<int:address_id>/default/", views.MeAddressDefaultApi.as_view(), name="api-me-address-default"),
    path("me/addresses/<int:address_id>/", views.MeAddressDeleteApi.as_view(), name="api-me-address-delete"),
    path("me/invoice/", views.MeInvoiceApi.as_view(), name="api-me-invoice"),
    path("me/orders/", views.BuyerOrdersApi.as_view(), name="api-buyer-orders"),
    path("me/orders/<int:order_id>/", views.BuyerOrderDetailApi.as_view(), name="api-buyer-order-detail"),
    path("me/orders/<int:order_id>/cancel-request/", views.BuyerCancelRequestApi.as_view(), name="api-buyer-order-cancel-request"),
    path("me/orders/<int:order_id>/refund-request/", views.BuyerRefundRequestApi.as_view(), name="api-buyer-order-refund-request"),
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
    path("me/sales/<int:order_id>/newebpay-logistics/", views.SellerNewebpayLogisticsApi.as_view(), name="api-seller-newebpay-logistics"),
    path(
        "me/sales/<int:order_id>/newebpay-logistics/sandbox/",
        views.SellerNewebpaySandboxLogisticsPrepareApi.as_view(),
        name="api-seller-newebpay-logistics-sandbox",
    ),

    # 賣家商品管理
    path("me/products/", views.SellerProductsApi.as_view(), name="api-seller-products"),
    path("me/products/<slug:slug>/", views.SellerProductDetailApi.as_view(), name="api-seller-product-detail"),
    path("me/products/<slug:slug>/archive/", views.SellerProductArchiveApi.as_view(), name="api-seller-product-archive"),
    path("me/products/<slug:slug>/duplicate/", views.SellerProductDuplicateApi.as_view(), name="api-seller-product-duplicate"),

    # 購物車 / 結帳
    path("cart/", views.CartApi.as_view(), name="api-cart"),
    path("cart/items/", views.CartAddApi.as_view(), name="api-cart-add"),
    path("cart/items/<path:item_key>/", views.CartItemApi.as_view(), name="api-cart-item"),
    path("checkout/preview/", views.CheckoutPreviewApi.as_view(), name="api-checkout-preview"),
    path("checkout/confirm/", views.CheckoutConfirmApi.as_view(), name="api-checkout-confirm"),
    path("integrations/newebpay/payment/callback/", views.NewebpayPaymentCallbackApi.as_view(), name="api-newebpay-payment-callback"),
    path("integrations/newebpay/logistics/callback/", views.NewebpayLogisticsCallbackApi.as_view(), name="api-newebpay-logistics-callback"),
    path(
        "integrations/newebpay/payment/sandbox/callback/",
        views.NewebpaySandboxPaymentCallbackApi.as_view(),
        name="api-newebpay-payment-sandbox-callback",
    ),
    path(
        "integrations/newebpay/logistics/sandbox/callback/",
        views.NewebpaySandboxLogisticsCallbackApi.as_view(),
        name="api-newebpay-logistics-sandbox-callback",
    ),

    # 後台管理
    path("staff/reviews/", views.StaffReviewDashboardApi.as_view(), name="api-admin-review-dashboard"),
    path("staff/dashboard/", views.AdminDashboardApi.as_view(), name="api-admin-dashboard"),
    path("staff/orders/", views.AdminOrdersApi.as_view(), name="api-admin-orders"),
    path("staff/orders/<int:order_id>/", views.AdminOrderDetailApi.as_view(), name="api-admin-order-detail"),
    path("staff/orders/<int:order_id>/service-review/", views.AdminOrderServiceReviewApi.as_view(), name="api-admin-order-service-review"),
    path("staff/users/", views.AdminUsersApi.as_view(), name="api-admin-users"),
    path("staff/users/<slug:username>/status/", views.AdminUserStatusApi.as_view(), name="api-admin-user-status"),
    path("staff/products/<slug:slug>/review/", views.ProductReviewDecisionApi.as_view(), name="api-admin-product-review"),
    path("staff/seller-requests/<slug:username>/review/", views.SellerRequestReviewApi.as_view(), name="api-admin-seller-request-review"),

    # 商品與內容
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
    path("community/posts/", views.CommunityPostsApi.as_view(), name="api-community-posts"),
    path("community/posts/<int:post_id>/", views.CommunityPostDetailApi.as_view(), name="api-community-post-detail"),
    path("community/posts/<int:post_id>/replies/", views.CommunityRepliesApi.as_view(), name="api-community-replies"),
    path("community/posts/<int:post_id>/vote/", views.CommunityVoteApi.as_view(), name="api-community-vote"),
]

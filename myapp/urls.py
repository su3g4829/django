"""
myapp/urls.py
--------------

此檔案現在只保留兩種網址：

1. 使用者原本熟悉的 HTML 路徑，但統一轉址到 Next.js 前端。
2. Django 後端自身需要的文件頁、健康檢查與 legacy API alias。
"""

from django.urls import path

from . import ops_views
from . import views
from .api import views as api_views

urlpatterns = [
    path("sm/<slug:selection_token>/", api_views.NewebpayStoreMapReturnRelayView.as_view(), name="newebpay_store_map_return_relay"),
    # ===== Next.js 前端入口 =====
    path("", views.FrontendRedirectView.as_view(frontend_path="/"), name="frontend-root"),
    path("index/", views.FrontendRedirectView.as_view(frontend_path="/"), name="home"),
    path("login/", views.FrontendRedirectView.as_view(frontend_path="/login"), name="login"),
    path("register/", views.FrontendRedirectView.as_view(frontend_path="/register"), name="register"),
    path("me/", views.FrontendRedirectView.as_view(frontend_path="/me/dashboard"), name="me"),
    path("me/profile/", views.FrontendRedirectView.as_view(frontend_path="/me/profile"), name="profile_edit"),
    path("me/promotions/", views.FrontendRedirectView.as_view(frontend_path="/me/promotions"), name="promotion_application"),
    path("me/addresses/", views.FrontendRedirectView.as_view(frontend_path="/me/addresses"), name="address_book"),
    path("me/invoice/", views.FrontendRedirectView.as_view(frontend_path="/me/invoice"), name="invoice_profile"),
    path("me/products/", views.FrontendRedirectView.as_view(frontend_path="/me/products"), name="my_products"),
    path("me/products/create/", views.FrontendRedirectView.as_view(frontend_path="/me/products/new"), name="product_create"),
    path("me/products/<slug:slug>/edit/", views.FrontendRedirectView.as_view(frontend_path="/me/products/{slug}"), name="product_edit"),
    path("me/sales/", views.FrontendRedirectView.as_view(frontend_path="/me/sales"), name="seller_order_list"),
    path("me/sales/report/", views.FrontendRedirectView.as_view(frontend_path="/me/sales/report"), name="seller_sales_report"),
    path("me/sales/<int:order_id>/", views.FrontendRedirectView.as_view(frontend_path="/me/sales/{order_id}"), name="seller_order_detail"),
    path("staff/reviews/", views.FrontendRedirectView.as_view(frontend_path="/staff/reviews"), name="staff_review_dashboard"),
    path("staff/dashboard/", views.FrontendRedirectView.as_view(frontend_path="/staff/dashboard"), name="admin_dashboard"),
    path("staff/banners/", views.FrontendRedirectView.as_view(frontend_path="/staff/banners"), name="admin_banner_list"),
    path("staff/orders/", views.FrontendRedirectView.as_view(frontend_path="/staff/orders"), name="admin_order_list"),
    path("staff/orders/<int:order_id>/", views.FrontendRedirectView.as_view(frontend_path="/staff/orders/{order_id}"), name="admin_order_detail"),
    path("staff/users/", views.FrontendRedirectView.as_view(frontend_path="/staff/users"), name="admin_user_list"),
    path("staff/products/", views.FrontendRedirectView.as_view(frontend_path="/staff/products"), name="admin_product_list"),
    path("staff/content/reviews/", views.FrontendRedirectView.as_view(frontend_path="/staff/content/reviews"), name="admin_content_reviews"),
    path("staff/content/questions/", views.FrontendRedirectView.as_view(frontend_path="/staff/content/questions"), name="admin_content_questions"),
    path("staff/content/posts/", views.FrontendRedirectView.as_view(frontend_path="/staff/content/posts"), name="admin_content_posts"),
    path("orders/", views.FrontendRedirectView.as_view(frontend_path="/orders"), name="order_list"),
    path("orders/<int:order_id>/", views.FrontendRedirectView.as_view(frontend_path="/orders/{order_id}"), name="order_detail"),
    path("cart/", views.FrontendRedirectView.as_view(frontend_path="/cart"), name="cart"),
    path("checkout/preview/", views.FrontendRedirectView.as_view(frontend_path="/checkout"), name="checkout_preview"),
    path("community/", views.FrontendRedirectView.as_view(frontend_path="/community"), name="community_list"),
    path("community/<int:post_id>/", views.FrontendRedirectView.as_view(frontend_path="/community/{post_id}"), name="community_post_detail"),
    path("products/", views.FrontendRedirectView.as_view(frontend_path="/products"), name="product_list"),
    path("products/compare/", views.FrontendRedirectView.as_view(frontend_path="/products/compare"), name="product_compare"),
    path("brands/<slug:brand_slug>/", views.FrontendRedirectView.as_view(frontend_path="/brands/{brand_slug}"), name="brand_detail"),
    path("categories/<slug:category_slug>/", views.FrontendRedirectView.as_view(frontend_path="/categories/{category_slug}"), name="category_detail"),
    path("products/<slug:slug>/", views.FrontendRedirectView.as_view(frontend_path="/products/{slug}"), name="product_detail"),

    # ===== Django 後端文件 / health =====
    path("docs/api-routes/", views.api_route_record_view, name="api_route_record"),
    path("docs/html-write-migrations/", views.html_write_migration_record_view, name="html_write_migration_record"),
    path("docs/no-db-infrastructure/", ops_views.no_db_infrastructure_view, name="no_db_infrastructure"),
    path("health/live/", ops_views.health_live, name="health_live"),
    path("health/ready/", ops_views.health_ready, name="health_ready"),

    # ===== Django 直接輸出的檔案 =====
    path("me/sales/export/orders.csv", views.seller_orders_csv, name="seller_orders_csv"),
    path("me/sales/export/report.csv", views.seller_report_csv, name="seller_report_csv"),

    # ===== Legacy API aliases =====
    path("api/products/<slug:slug>/reviews/", api_views.LegacyProductReviewsApi.as_view(), name="product_reviews_api"),
    path("api/products/<slug:slug>/questions/", api_views.LegacyProductQuestionsApi.as_view(), name="product_questions_api"),
    path(
        "api/products/<slug:slug>/questions/<int:question_id>/answers/",
        api_views.LegacyProductAnswersApi.as_view(),
        name="product_answers_api",
    ),
    path(
        "api/products/<slug:slug>/recommendations/",
        api_views.LegacyProductRecommendationsApi.as_view(),
        name="product_recommendations_api",
    ),
    path("api/community/posts/", api_views.LegacyCommunityPostsApi.as_view(), name="community_posts_api"),
    path("api/community/posts/<int:post_id>/", api_views.LegacyCommunityPostDetailApi.as_view(), name="community_post_detail_api"),
    path("api/community/posts/<int:post_id>/replies/", api_views.LegacyCommunityRepliesApi.as_view(), name="community_replies_api"),
    path("api/community/posts/<int:post_id>/vote/", api_views.LegacyCommunityVoteApi.as_view(), name="community_vote_api"),
]

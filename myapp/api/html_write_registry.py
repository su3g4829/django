"""HTML 寫入路由遷移登錄表。

這個檔案專門記錄「舊的 HTML form POST 路由」如何被 DRF API 取代。
用途是讓 `/docs/html-write-migrations/` 可以清楚列出：
- 舊模板原本送到哪個 HTML route
- 現在改成送到哪個 canonical DRF API
- 路由是否已完全移除
"""
from __future__ import annotations

HTML_WRITE_MIGRATIONS = [
    {
        "group": "Auth / Session",
        "items": [
            {
                "name": "Login Form",
                "template": "templates/auth/login.html",
                "legacy_route": "POST /login/",
                "canonical_api": "POST /api/v1/auth/login/",
                "router_status": "removed",
                "notes": "Template submit now goes directly to DRF and redirects with client-side handling.",
            },
            {
                "name": "Register Form",
                "template": "templates/auth/register.html",
                "legacy_route": "POST /register/",
                "canonical_api": "POST /api/v1/auth/register/",
                "router_status": "removed",
                "notes": "Account creation now uses the DRF auth endpoint and then redirects to next/home.",
            },
            {
                "name": "Logout Form",
                "template": "templates/base.html",
                "legacy_route": "POST /logout/",
                "canonical_api": "POST /api/v1/auth/logout/",
                "router_status": "removed",
                "notes": "Header logout control now clears the demo session through DRF.",
            },
            {
                "name": "Profile Update",
                "template": "templates/me/profile.html",
                "legacy_route": "POST /me/profile/",
                "canonical_api": "POST /api/v1/me/profile/",
                "router_status": "removed",
                "notes": "Display name and password updates are now API-first.",
            },
            {
                "name": "Seller Access Request",
                "template": "templates/me/profile.html",
                "legacy_route": "POST /me/seller-request/",
                "canonical_api": "POST /api/v1/me/seller-request/",
                "router_status": "removed",
                "notes": "Seller request buttons now call the DRF account endpoint.",
            },
        ],
    },
    {
        "group": "Cart / Checkout",
        "items": [
            {
                "name": "Add To Cart",
                "template": "templates/products/detail.html",
                "legacy_route": "POST /cart/add/<slug>/",
                "canonical_api": "POST /api/v1/cart/items/",
                "router_status": "removed",
                "notes": "Product detail form now submits slug, qty, and variant directly to DRF.",
            },
            {
                "name": "Cart Line Update",
                "template": "templates/cart/cart.html",
                "legacy_route": "POST /cart/update/<item_key>/",
                "canonical_api": "PATCH /api/v1/cart/items/<item_key>/",
                "router_status": "removed",
                "notes": "Quantity updates now target the DRF cart item endpoint.",
            },
            {
                "name": "Cart Line Delete",
                "template": "templates/cart/cart.html",
                "legacy_route": "POST /cart/remove/<item_key>/",
                "canonical_api": "DELETE /api/v1/cart/items/<item_key>/",
                "router_status": "removed",
                "notes": "Removal now uses the same DRF cart item endpoint with DELETE.",
            },
            {
                "name": "Coupon Apply / Clear",
                "template": "templates/cart/cart.html",
                "legacy_route": "POST /cart/",
                "canonical_api": "POST /api/v1/cart/",
                "router_status": "removed",
                "notes": "Coupon actions are now handled by the DRF cart snapshot endpoint.",
            },
            {
                "name": "Checkout Confirm",
                "template": "templates/checkout/preview.html",
                "legacy_route": "POST /checkout/confirm/",
                "canonical_api": "POST /api/v1/checkout/confirm/",
                "router_status": "removed",
                "notes": "Order creation is now API-first and client-side redirects to buyer order detail.",
            },
        ],
    },
    {
        "group": "Catalog / Engagement",
        "items": [
            {
                "name": "Favorite Toggle",
                "template": "templates/products/detail.html",
                "legacy_route": "POST /products/<slug>/favorite/",
                "canonical_api": "POST /api/v1/products/<slug>/favorite/",
                "router_status": "removed",
                "notes": "Product favorite writes now use the DRF toggle endpoint.",
            },
            {
                "name": "Compare Toggle",
                "template": "templates/products/list.html, templates/products/detail.html",
                "legacy_route": "POST /products/<slug>/compare/",
                "canonical_api": "POST /api/v1/products/<slug>/compare/",
                "router_status": "removed",
                "notes": "Compare list writes now go through DRF.",
            },
            {
                "name": "Review Submit",
                "template": "templates/products/detail.html",
                "legacy_route": "POST /products/<slug>/reviews/",
                "canonical_api": "POST /api/v1/products/<slug>/reviews/",
                "router_status": "removed",
                "notes": "Review creation uses DRF validation and response shape.",
            },
            {
                "name": "Question Submit",
                "template": "templates/products/detail.html",
                "legacy_route": "POST /products/<slug>/questions/",
                "canonical_api": "POST /api/v1/products/<slug>/questions/",
                "router_status": "removed",
                "notes": "Product Q&A submit is API-first.",
            },
            {
                "name": "Answer Submit",
                "template": "templates/products/detail.html",
                "legacy_route": "POST /products/<slug>/questions/<question_id>/answers/",
                "canonical_api": "POST /api/v1/products/<slug>/questions/<question_id>/answers/",
                "router_status": "removed",
                "notes": "Question answer submit is API-first.",
            },
        ],
    },
    {
        "group": "Community",
        "items": [
            {
                "name": "Post Create",
                "template": "templates/community/list.html",
                "legacy_route": "POST /community/create/",
                "canonical_api": "POST /api/v1/community/posts/",
                "router_status": "removed",
                "notes": "Forum post creation now goes directly through DRF and redirects to the new thread.",
            },
            {
                "name": "Reply Create",
                "template": "templates/community/detail.html",
                "legacy_route": "POST /community/<post_id>/replies/",
                "canonical_api": "POST /api/v1/community/posts/<post_id>/replies/",
                "router_status": "removed",
                "notes": "Thread replies now use the DRF reply endpoint.",
            },
            {
                "name": "Vote",
                "template": "templates/community/detail.html",
                "legacy_route": "POST /community/<post_id>/vote/",
                "canonical_api": "POST /api/v1/community/posts/<post_id>/vote/",
                "router_status": "removed",
                "notes": "Forum upvote actions now use the canonical DRF route.",
            },
        ],
    },
    {
        "group": "Buyer / Seller / Admin Operations",
        "items": [
            {
                "name": "Address Book Writes",
                "template": "templates/me/addresses.html",
                "legacy_route": "POST /me/addresses/ and related default/delete routes",
                "canonical_api": "POST /api/v1/me/addresses/, POST /api/v1/me/addresses/<id>/default/, DELETE /api/v1/me/addresses/<id>/",
                "router_status": "removed",
                "notes": "Address create/default/delete now all go through DRF.",
            },
            {
                "name": "Invoice Profile",
                "template": "templates/me/invoice.html",
                "legacy_route": "POST /me/invoice/",
                "canonical_api": "POST /api/v1/me/invoice/",
                "router_status": "removed",
                "notes": "Invoice updates now target the DRF account endpoint.",
            },
            {
                "name": "Buyer Service Requests",
                "template": "templates/orders/detail.html",
                "legacy_route": "POST /orders/<id>/cancel-request/ and refund-request/",
                "canonical_api": "POST /api/v1/me/orders/<id>/cancel-request/ and refund-request/",
                "router_status": "removed",
                "notes": "Cancel/refund requests now submit via DRF.",
            },
            {
                "name": "Seller Order Update",
                "template": "templates/seller/order_detail.html",
                "legacy_route": "POST /me/sales/<id>/update/",
                "canonical_api": "POST /api/v1/me/sales/<id>/update/",
                "router_status": "removed",
                "notes": "Fulfillment updates now go through the DRF seller endpoint.",
            },
            {
                "name": "Seller Product CRUD",
                "template": "templates/products/form.html, templates/me/products.html",
                "legacy_route": "POST /me/products/... create/edit/archive/delete/duplicate",
                "canonical_api": "POST /api/v1/me/products/, PUT /api/v1/me/products/<slug>/, POST /archive/, POST /duplicate/, DELETE /api/v1/me/products/<slug>/",
                "router_status": "removed",
                "notes": "Seller product management UI is now API-first.",
            },
            {
                "name": "Admin Review Workflows",
                "template": "templates/staff/review_dashboard.html, templates/staff/order_detail.html, templates/staff/users.html",
                "legacy_route": "POST review/user/service routes under /staff/",
                "canonical_api": "POST /api/v1/staff/reviews/... /staff/orders/... /staff/users/... /staff/products/... ",
                "router_status": "removed",
                "notes": "Admin review actions now submit through canonical DRF endpoints.",
            },
        ],
    },
]

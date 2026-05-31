"""DRF API 視圖層。

這個模組負責把 HTTP 請求轉交給既有 service / repository，
並使用 DRF `Response` 回傳統一的 JSON 格式。
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

from django.middleware.csrf import get_token
from django.http import HttpResponseRedirect, QueryDict
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..repositories import local_store
from ..services import admin_portal
from ..services import auth_demo
from ..services import banners as banner_service
from ..services import cart as cart_service
from ..services import community as community_service
from ..services import customer_center
from ..services import newebpay_logistics as newebpay_logistics_service
from ..services import newebpay_logistics_real as newebpay_logistics_real_service
from ..services import newebpay_payment as newebpay_payment_service
from ..services import newebpay_payment_real as newebpay_payment_real_service
from ..services import orders as order_service
from ..services import personalization as personalization_service
from ..services import price_compare as price_compare_service
from ..services import product_management
from ..services import profile as profile_service
from ..services import questions as question_service
from ..services import recommendations as recommendation_service
from ..services import reviews as review_service
from . import serializers as sz
from .permissions import IsAdminDemoUser
from .permissions import IsDemoAuthenticated
from .permissions import IsSellerOrAdminDemoUser
from .permissions import get_demo_user

PAGE_SIZE = 3


class PayloadAdapter(dict):
    """提供 `getlist()` 的簡易資料容器。

    產品建立 / 編輯流程原本是給 Django form 使用，
    這裡補一層 adapter，讓 JSON 與 multipart/form-data 都能共用同一套 service。
    """

    def getlist(self, key: str) -> list[Any]:
        """回傳指定欄位的多值清單。"""
        value = self.get(key, [])
        if isinstance(value, list):
            return value
        if value in (None, ""):
            return []
        return [value]


def _error(message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    """建立統一錯誤回應。"""
    return Response({"detail": message}, status=status_code)


def _validated(serializer_class, data: Any) -> Dict[str, Any]:
    """驗證輸入資料並回傳 `validated_data`。"""
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def _current_user_or_403(request) -> Dict[str, str] | Response:
    """取得目前登入會員；未登入時直接回傳 403。"""
    user = get_demo_user(request)
    if not user:
        return _error("Please log in first.", status.HTTP_403_FORBIDDEN)
    return user


def _parse_decimal(value: Any) -> Decimal | None:
    """把 query string 價格條件轉成 Decimal。"""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _serialize_product(product: Dict[str, Any], request=None) -> Dict[str, Any]:
    """將商品整理成 API 輸出格式。"""
    item = product_management.prepare_product_for_display(product)
    if request is not None:
        item["is_favorite"] = personalization_service.is_favorite(request.session, str(item.get("slug", "")))
    return item


def _serialize_products(products: Iterable[Dict[str, Any]], request=None) -> list[Dict[str, Any]]:
    """批次整理商品資料。"""
    return [_serialize_product(item, request) for item in products]


def _can_manage_community_post(user: Dict[str, Any] | None, post: Dict[str, Any]) -> bool:
    """判斷目前會員是否為文章作者。"""
    if not user:
        return False

    post_username = str(post.get("author_username") or "").strip().lower()
    user_username = str(user.get("username") or "").strip().lower()
    if post_username and user_username and post_username == user_username:
        return True

    post_user_id = post.get("author_user_id")
    user_id = user.get("id")
    return post_user_id is not None and user_id is not None and str(post_user_id) == str(user_id)


def _serialize_community_post(post: Dict[str, Any], request) -> Dict[str, Any]:
    """補上前端控制編輯 / 刪除按鈕所需欄位。"""
    item = dict(post)
    can_manage = _can_manage_community_post(get_demo_user(request), item)
    item["can_edit"] = can_manage
    item["can_delete"] = can_manage
    return item


def _serialize_community_posts(posts: Iterable[Dict[str, Any]], request) -> list[Dict[str, Any]]:
    """批次整理文章列表資料。"""
    return [_serialize_community_post(post, request) for post in posts]


def _build_product_list_payload(request, params: Dict[str, Any]) -> Dict[str, Any]:
    """依查詢條件建立商品列表回應。"""
    page = int(params.get("page") or 1)
    q = str(params.get("q") or "").strip().lower()
    category = str(params.get("category") or "").strip().lower()
    brand = str(params.get("brand") or "").strip().lower()
    tag = str(params.get("tag") or "").strip().lower()
    color = str(params.get("color") or "").strip().lower()
    size = str(params.get("size") or "").strip().lower()
    sort = str(params.get("sort") or "featured").strip().lower()
    min_price = _parse_decimal(params.get("min_price"))
    max_price = _parse_decimal(params.get("max_price"))

    products = product_management.list_public_products()
    filtered = product_management.filter_products(
        products,
        q=q,
        category=category,
        brand=brand,
        tag=tag,
        min_price=min_price,
        max_price=max_price,
        color=color,
        size=size,
    )
    ordered = product_management.sort_products(filtered, sort)
    total_items = len(ordered)
    total_pages = max(1, (total_items + PAGE_SIZE - 1) // PAGE_SIZE)
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    items = ordered[start:end]
    return {
        "items": _serialize_products(items, request),
        "meta": {
            "page": safe_page,
            "total_pages": total_pages,
            "total_items": total_items,
        },
        "facets": product_management.build_catalog_facets(products),
        "filters": {
            "q": q,
            "category": category,
            "brand": brand,
            "tag": tag,
            "color": color,
            "size": size,
            "sort": sort,
            "min_price": str(min_price) if min_price is not None else "",
            "max_price": str(max_price) if max_price is not None else "",
        },
    }


def _build_cart_response(session, detail: str = "", *, shipping_method: str = "") -> Dict[str, Any]:
    """把 session 購物車整理成 API 回應格式。"""
    cart = cart_service.get_cart(session)
    items = []
    for raw_item in cart.get("items", {}).values():
        item = dict(raw_item)
        item.setdefault("key", cart_service.make_item_key(item.get("slug", ""), item.get("variant_id", "")))
        item.setdefault("display_name", item.get("name", ""))
        item["line_total"] = round(float(item["price"]) * int(item["qty"]), 2)
        items.append(item)

    selected_shipping_method = order_service.normalize_checkout_shipping_method(
        str(shipping_method or order_service.SHIPPING_METHOD_HOME_DELIVERY).strip()
    )

    cart_pricing = order_service.build_checkout_totals(
        session,
        shipping_method=selected_shipping_method,
    )
    payload = {
        "items": items,
        "coupon": cart.get("coupon"),
        "item_count": cart_service.count_items(session),
        "totals": {
            key: format(value, ".2f") for key, value in cart_pricing["totals"].items()
        },
        "shipping_methods": order_service.get_checkout_shipping_methods(),
        "selected_shipping_method": selected_shipping_method,
        "seller_shipping_groups": cart_pricing["seller_shipping_groups"],
    }
    unsupported_detail = ""
    if cart_pricing["unsupported_sellers"]:
        unsupported_detail = (
            "The selected shipping method is not available for: "
            + ", ".join(cart_pricing["unsupported_sellers"])
            + "."
        )
    if detail:
        payload["detail"] = f"{detail} {unsupported_detail}".strip()
    elif unsupported_detail:
        payload["detail"] = unsupported_detail
    return payload


def _build_checkout_preview_payload(request) -> Dict[str, Any]:
    """建立結帳預覽回應。"""
    user = get_demo_user(request)
    payload = _build_cart_response(request.session)
    selected_shipping_method = order_service.normalize_checkout_shipping_method(
        str(request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY).strip()
        or order_service.SHIPPING_METHOD_HOME_DELIVERY
    )
    try:
        checkout_pricing = order_service.build_checkout_totals(
            request.session,
            shipping_method=selected_shipping_method,
        )
        payload["totals"] = checkout_pricing["totals"]
        payload["seller_shipping_groups"] = checkout_pricing["seller_shipping_groups"]
        if checkout_pricing["unsupported_sellers"]:
            payload["detail"] = (
                "The selected shipping method is not available for: "
                + ", ".join(checkout_pricing["unsupported_sellers"])
                + "."
            )
    except ValueError as exc:
        payload["detail"] = str(exc)
        payload["seller_shipping_groups"] = []
    addresses = customer_center.list_addresses(user["username"]) if user else []
    default_address = customer_center.get_default_address(user["username"]) if user else None
    payload["addresses"] = addresses
    payload["default_address"] = default_address
    payload["selected_address_id"] = default_address.get("id") if default_address else None
    payload["invoice_profile"] = customer_center.get_invoice_profile(user["username"]) if user else {}
    payload["shipping_methods"] = order_service.get_checkout_shipping_methods()
    payload["payment_methods"] = order_service.get_checkout_payment_methods()
    payload["convenience_store_brands"] = order_service.get_convenience_store_brands()
    payload["selected_shipping_method"] = selected_shipping_method
    payload["selected_payment_method"] = order_service.PAYMENT_METHOD_NEWEBPAY_CREDIT
    payload["user"] = user
    payload["requires_login"] = user is None
    payload["can_confirm"] = bool(
        user and payload["item_count"] > 0 and default_address and not payload.get("detail")
    )
    return payload


def _build_dashboard_payload(user: Dict[str, str], session) -> Dict[str, Any]:
    """建立會員中心儀表板回應。"""
    dashboard = profile_service.build_profile_dashboard(user, session)
    return {
        "user": user,
        "review_count": len(dashboard["reviews"]),
        "question_count": len(dashboard["questions"]),
        "answer_count": len(dashboard["answers"]),
        "post_count": len(dashboard["posts"]),
        "order_count": len(dashboard["orders"]),
        "favorite_products": _serialize_products(dashboard["favorite_products"]),
        "recent_products": _serialize_products(dashboard["recent_products"]),
        "owned_products": dashboard["owned_products"],
    }


def _build_app_bootstrap_payload(request) -> Dict[str, Any]:
    """回傳前端啟動畫面常用的全域狀態。"""
    user = get_demo_user(request)
    return {
        "user": user,
        "cart_count": cart_service.count_items(request.session),
        "compare_count": len(personalization_service.get_compare_slugs(request.session)),
        "favorite_count": len(personalization_service.get_favorite_slugs(request.session)),
    }


class BannerListApi(APIView):
    """提供首頁公開 banner 列表的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳已啟用的 banner。"""
        return Response({"items": banner_service.list_public_banners()})


class MeBannerApplicationsApi(APIView):
    """提供會員自己的首頁宣傳申請列表與送件 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳目前會員送出的 banner 申請。"""
        user = get_demo_user(request)
        return Response({"items": banner_service.list_user_applications(user["username"])})

    def post(self, request):
        """提交新的 banner 申請。"""
        user = get_demo_user(request)
        payload = _validated(sz.BannerApplicationCreateSerializer, request.data)
        try:
            banner = banner_service.submit_banner_application(
                user=user,
                title=str(payload.get("title", "")),
                copy_text=str(payload.get("copy_text", "")),
                link_url=str(payload.get("link_url", "")),
                starts_at=str(payload["starts_at"]),
                ends_at=str(payload["ends_at"]),
                position=str(payload.get("position", "home_main")),
                note=str(payload.get("note", "")),
                uploaded_image=payload["image"],
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(banner, status=status.HTTP_201_CREATED)


class AdminBannersApi(APIView):
    """提供管理者 banner 列表與建立的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳所有 banner。"""
        return Response({"items": banner_service.list_admin_banners()})

    def post(self, request):
        """建立 banner。"""
        user = get_demo_user(request)
        payload = _validated(sz.AdminBannerCreateSerializer, request.data)
        try:
            banner = banner_service.create_admin_banner(
                user=user,
                title=str(payload.get("title", "")),
                copy_text=str(payload.get("copy_text", "")),
                link_url=str(payload.get("link_url", "")),
                starts_at=str(payload["starts_at"]),
                ends_at=str(payload["ends_at"]),
                position=str(payload.get("position", "home_main")),
                note=str(payload.get("note", "")),
                is_active=bool(payload.get("is_active", True)),
                uploaded_image=payload["image"],
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(banner, status=status.HTTP_201_CREATED)


class AdminBannerDetailApi(APIView):
    """提供管理者單一 banner 更新與刪除的 API。"""

    permission_classes = [IsAdminDemoUser]

    def put(self, request, banner_id: int):
        """更新 banner。"""
        payload = _validated(sz.AdminBannerUpdateSerializer, request.data)
        try:
            banner = banner_service.update_banner(
                banner_id=banner_id,
                title=str(payload.get("title", "")),
                copy_text=str(payload.get("copy_text", "")),
                link_url=str(payload.get("link_url", "")),
                starts_at=str(payload["starts_at"]),
                ends_at=str(payload["ends_at"]),
                position=str(payload.get("position", "home_main")),
                note=str(payload.get("note", "")),
                is_active=bool(payload.get("is_active", True)),
                sort_order=int(payload.get("sort_order", 1)),
                uploaded_image=payload.get("image"),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
            return _error(message, status_code)
        return Response(banner)

    def delete(self, request, banner_id: int):
        """刪除 banner。"""
        try:
            banner_service.delete_banner(banner_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminBannerReviewApi(APIView):
    """提供管理者審核 banner 申請的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, banner_id: int):
        """核准或拒絕申請。"""
        reviewer = get_demo_user(request)
        payload = _validated(sz.AdminBannerReviewSerializer, request.data)
        try:
            banner = banner_service.review_banner_application(
                banner_id=banner_id,
                reviewer=reviewer,
                approved=bool(payload["approved"]),
                rejection_reason=str(payload.get("rejection_reason", "")),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
            return _error(message, status_code)
        return Response(banner)


class AdminBannerReorderApi(APIView):
    """提供管理者調整 banner 排序的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request):
        """依照送入 ID 清單更新排序。"""
        payload = _validated(sz.AdminBannerReorderSerializer, request.data)
        return Response({"items": banner_service.reorder_banners(list(payload["ids"]))})


def _parse_order_id_from_merchant_order_no(merchant_order_no: str) -> int | None:
    """從藍新 MerchantOrderNo 取回原始訂單 ID。"""
    if not merchant_order_no.startswith("ORDER"):
        return None
    raw = merchant_order_no[5:].split("-", 1)[0]
    return int(raw) if raw.isdigit() else None


def _payload_from_request(request) -> PayloadAdapter:
    """把 JSON / form-data 整理成可給 service 使用的 payload。"""
    payload = PayloadAdapter()
    data = request.data
    if isinstance(data, QueryDict):
        for key in data.keys():
            values = data.getlist(key)
            payload[key] = values if len(values) > 1 else data.get(key)
    else:
        for key, value in dict(data).items():
            payload[key] = value
    return payload


def _product_or_404(slug: str, user: Dict[str, str] | None = None) -> Dict[str, Any] | Response:
    """取得前台可見商品；找不到時回傳 404。"""
    product = product_management.get_visible_product(slug, user)
    if not product:
        return _error("Product not found.", status.HTTP_404_NOT_FOUND)
    return product


def _owned_product_or_404(user: Dict[str, str], slug: str) -> Dict[str, Any] | Response:
    """取得賣家自有商品；找不到時回傳 404。"""
    product = product_management.get_user_product(user["username"], slug)
    if not product:
        return _error("Product not found.", status.HTTP_404_NOT_FOUND)
    return product


def _admin_or_owned_product_or_404(user: Dict[str, str], slug: str) -> Dict[str, Any] | Response:
    """Return any product for admins, or only owned products for sellers."""
    if auth_demo.is_admin(user):
        product = product_management.get_product_for_admin(slug)
    else:
        product = product_management.get_user_product(user["username"], slug)
    if not product:
        return _error("Product not found.", status.HTTP_404_NOT_FOUND)
    return product


class ProductListApi(APIView):
    """提供商品列表與條件篩選的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """處理商品列表查詢。"""
        params = _validated(sz.ProductListQuerySerializer, request.query_params)
        return Response(_build_product_list_payload(request, params))


class ProductDetailApi(APIView):
    """提供單一商品詳情的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理商品詳情查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        return Response(_serialize_product(product, request))


class ProductReviewsApi(APIView):
    """提供商品評論查詢與建立的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理評論列表查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        items = review_service.list_reviews(product["id"])
        return Response({"items": items})

    def post(self, request, slug: str):
        """處理新增評論。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        product = _product_or_404(slug, user)
        if isinstance(product, Response):
            return product
        payload = _validated(sz.ReviewCreateSerializer, request.data)
        try:
            review = review_service.create_review(
                product_id=product["id"],
                author=user["display_name"],
                author_username=user["username"],
                author_user_id=user["id"],
                rating=int(payload["rating"]),
                title=str(payload["title"]),
                body=str(payload["body"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        items = review_service.list_reviews(product["id"])
        created = next((item for item in items if item["id"] == review["id"]), review)
        return Response(created, status=status.HTTP_201_CREATED)


class ProductQuestionsApi(APIView):
    """提供商品問答查詢與提問的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理問答列表查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        return Response({"items": question_service.list_questions(product["id"])})

    def post(self, request, slug: str):
        """處理新增問題。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        product = _product_or_404(slug, user)
        if isinstance(product, Response):
            return product
        payload = _validated(sz.QuestionCreateSerializer, request.data)
        try:
            question = question_service.create_question(
                product_id=product["id"],
                author=user["display_name"],
                author_username=user["username"],
                author_user_id=user["id"],
                title=str(payload["title"]),
                body=str(payload["body"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        items = question_service.list_questions(product["id"])
        created = next((item for item in items if item["id"] == question["id"]), question)
        return Response(created, status=status.HTTP_201_CREATED)


class ProductAnswersApi(APIView):
    """提供商品問答回答建立的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, slug: str, question_id: int):
        """處理新增回答。"""
        user = get_demo_user(request)
        product = _product_or_404(slug, user)
        if isinstance(product, Response):
            return product
        payload = _validated(sz.AnswerCreateSerializer, request.data)
        try:
            question_service.create_answer(
                product_id=product["id"],
                question_id=question_id,
                author=user["display_name"],
                author_username=user["username"],
                author_user_id=user["id"],
                body=str(payload["body"]),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST)
        updated = next(
            (item for item in question_service.list_questions(product["id"]) if item["id"] == question_id),
            None,
        )
        if not updated:
            return _error("Question not found.", status.HTTP_404_NOT_FOUND)
        return Response(updated, status=status.HTTP_201_CREATED)


class ProductRecommendationsApi(APIView):
    """提供商品推薦清單的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理推薦清單查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        groups = recommendation_service.get_product_recommendations(product)
        return Response(
            {
                "similar": _serialize_products(groups.get("similar", [])),
                "also_bought": _serialize_products(groups.get("also_bought", [])),
            }
        )


class ProductPriceCompareApi(APIView):
    """商品比價結果 API。

    這支 API 目前回傳的是 mock crawler / mock API 整理後的資料，
    用來先把比價功能的前後端流程建立起來。
    """

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """讀取單一商品的固定網址比價結果。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        try:
            payload = price_compare_service.get_price_comparison(product)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(payload)


class ProductPriceCompareRefreshApi(APIView):
    """模擬重新抓價 API。

    這支 API 不會真的連外抓資料，而是：
    - 更新 mock 抓價時間
    - 微調 mock 價格

    目的在於讓前端能展示「重新抓價」這個操作流程。
    """

    permission_classes = [AllowAny]

    def post(self, request, slug: str):
        """重新抓取單一商品的固定外站價格。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        try:
            result = price_compare_service.refresh_mock_price_comparison(product)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "detail": "價格比較已更新。",
                "result": result,
            }
        )


class CommunityPostsApi(APIView):
    """提供社群文章列表與發文的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """處理文章列表查詢。"""
        topic = str(request.query_params.get("topic", "")).strip().lower() or None
        return Response({"items": _serialize_community_posts(community_service.list_posts(topic), request)})

    def post(self, request):
        """處理建立文章。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        payload = _validated(sz.CommunityPostCreateSerializer, request.data)
        try:
            post = community_service.create_post(
                topic=str(payload.get("topic", "general")),
                author=user["display_name"],
                author_username=user["username"],
                author_user_id=user["id"],
                title=str(payload["title"]),
                body=str(payload["body"]),
                tags=str(payload.get("tags", "")),
            )
        except ValueError as exc:
            return _error(str(exc))
        detail = community_service.get_post_detail(post["id"]) or post
        return Response(_serialize_community_post(detail, request), status=status.HTTP_201_CREATED)


class CommunityImageUploadApi(APIView):
    """提供論壇富文本編輯器圖片上傳。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request):
        """接收一張圖片並回傳可儲存的靜態路徑。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        payload = _validated(sz.CommunityImageUploadSerializer, request.data)
        try:
            path = community_service.save_editor_image(payload["image"])
        except ValueError as exc:
            return _error(str(exc))
        return Response({"path": path}, status=status.HTTP_201_CREATED)


class CommunityPostDetailApi(APIView):
    """提供社群單篇文章詳情的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, post_id: int):
        """處理單篇文章查詢。"""
        post = community_service.get_post_detail(post_id)
        if not post:
            return _error("Post not found.", status.HTTP_404_NOT_FOUND)
        return Response(_serialize_community_post(post, request))

    def put(self, request, post_id: int):
        """處理作者編輯自己的文章。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        payload = _validated(sz.CommunityPostUpdateSerializer, request.data)
        try:
            community_service.update_post(
                post_id=post_id,
                username=user["username"],
                user_id=user.get("id"),
                topic=str(payload.get("topic", "general")),
                title=str(payload["title"]),
                body=str(payload["body"]),
                tags=str(payload.get("tags", "")),
            )
        except PermissionError as exc:
            return _error(str(exc), status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST)

        post = community_service.get_post_detail(post_id)
        if not post:
            return _error("Post not found.", status.HTTP_404_NOT_FOUND)
        return Response(_serialize_community_post(post, request))

    def delete(self, request, post_id: int):
        """處理作者刪除自己的文章。"""
        user = _current_user_or_403(request)
        if isinstance(user, Response):
            return user
        try:
            community_service.delete_post(post_id=post_id, username=user["username"], user_id=user.get("id"))
        except PermissionError as exc:
            return _error(str(exc), status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommunityRepliesApi(APIView):
    """提供社群文章回覆建立的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, post_id: int):
        """處理新增回覆。"""
        user = get_demo_user(request)
        payload = _validated(sz.CommunityReplyCreateSerializer, request.data)
        try:
            community_service.create_reply(
                post_id=post_id,
                author=user["display_name"],
                author_username=user["username"],
                author_user_id=user["id"],
                body=str(payload["body"]),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST)
        detail = community_service.get_post_detail(post_id)
        if not detail:
            return _error("Post not found.", status.HTTP_404_NOT_FOUND)
        return Response(_serialize_community_post(detail, request), status=status.HTTP_201_CREATED)


class CommunityVoteApi(APIView):
    """提供社群文章投票的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, post_id: int):
        """處理文章投票。"""
        try:
            post = community_service.upvote_post(post_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"id": post["id"], "votes": post["votes"]})


class MeApi(APIView):
    """提供目前登入會員資料的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳目前 session 會員。"""
        return Response({"user": get_demo_user(request)})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AuthCsrfApi(APIView):
    """提供前端初始化所需的 CSRF cookie。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """發出 CSRF cookie 與 token。"""
        return Response({"detail": "CSRF cookie issued.", "csrfToken": get_token(request)})


class AppBootstrapApi(APIView):
    """提供前端 header / session 初始化資料。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳目前會員與購物車 / 收藏 / 比較數量。"""
        return Response(_build_app_bootstrap_payload(request))


class MeDashboardApi(APIView):
    """提供會員中心儀表板資料的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳會員中心摘要。"""
        user = get_demo_user(request)
        return Response(_build_dashboard_payload(user, request.session))


class FavoriteToggleApi(APIView):
    """提供商品收藏切換的 API。"""

    permission_classes = [AllowAny]

    def post(self, request, slug: str):
        """切換商品收藏狀態。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        active = personalization_service.toggle_favorite(request.session, product)
        return Response(
            {
                "active": active,
                "slug": slug,
                "favorite_count": len(personalization_service.get_favorite_slugs(request.session)),
            }
        )


class CompareToggleApi(APIView):
    """提供商品比較切換的 API。"""

    permission_classes = [AllowAny]

    def post(self, request, slug: str):
        """切換商品比較狀態。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        active, removed_slug = personalization_service.toggle_compare(request.session, product)
        return Response(
            {
                "active": active,
                "slug": slug,
                "removed_slug": removed_slug,
                "compare_slugs": personalization_service.get_compare_slugs(request.session),
            }
        )


class CompareListApi(APIView):
    """提供 Next.js 商品比較頁的比較清單。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """讀取目前 session 的比較商品清單。"""
        user = get_demo_user(request)
        slugs = personalization_service.get_compare_slugs(request.session)
        products = product_management.get_compare_products(slugs, user)
        return Response({"items": _serialize_products(products), "slugs": slugs})


class MeAddressesApi(APIView):
    """提供會員地址簿查詢與建立的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳地址列表。"""
        user = get_demo_user(request)
        return Response({"items": customer_center.list_addresses(user["username"])})

    def post(self, request):
        """建立新地址。"""
        user = get_demo_user(request)
        payload = _validated(sz.AddressCreateSerializer, request.data)
        try:
            address = customer_center.add_address(user["username"], payload)
        except ValueError as exc:
            return _error(str(exc))
        return Response(address, status=status.HTTP_201_CREATED)


class MeAddressDefaultApi(APIView):
    """提供預設地址設定的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, address_id: int):
        """設定預設地址。"""
        user = get_demo_user(request)
        try:
            address = customer_center.set_default_address(user["username"], address_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(address)


class MeAddressDeleteApi(APIView):
    """提供地址刪除的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def delete(self, request, address_id: int):
        """刪除地址。"""
        user = get_demo_user(request)
        try:
            customer_center.remove_address(user["username"], address_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeInvoiceApi(APIView):
    """提供發票資料查詢與更新的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """讀取發票資料。"""
        user = get_demo_user(request)
        return Response(customer_center.get_invoice_profile(user["username"]))

    def post(self, request):
        """更新發票資料。"""
        user = get_demo_user(request)
        payload = _validated(sz.InvoiceProfileUpdateSerializer, request.data)
        try:
            profile = customer_center.update_invoice_profile(user["username"], payload)
        except ValueError as exc:
            return _error(str(exc))
        return Response(profile)


class BuyerOrdersApi(APIView):
    """提供買家訂單列表的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳買家訂單列表。"""
        user = get_demo_user(request)
        return Response({"items": order_service.list_orders_for_user(user["username"])})


class BuyerOrderDetailApi(APIView):
    """提供買家訂單明細的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request, order_id: int):
        """回傳買家訂單明細。"""
        user = get_demo_user(request)
        order = order_service.get_order_detail_for_user(order_id, user["username"])
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class BuyerCancelRequestApi(APIView):
    """提供買家取消訂單申請的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, order_id: int):
        """送出取消申請。"""
        user = get_demo_user(request)
        payload = _validated(sz.OrderServiceRequestCreateSerializer, request.data)
        try:
            order = order_service.request_order_service(
                order_id,
                user["username"],
                request_type=order_service.SERVICE_REQUEST_CANCEL,
                reason=str(payload["reason"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(order)


class BuyerRefundRequestApi(APIView):
    """提供買家退款申請的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, order_id: int):
        """送出退款申請。"""
        user = get_demo_user(request)
        payload = _validated(sz.OrderServiceRequestCreateSerializer, request.data)
        try:
            order = order_service.request_order_service(
                order_id,
                user["username"],
                request_type=order_service.SERVICE_REQUEST_REFUND,
                reason=str(payload["reason"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(order)


class BuyerNewebpayPaymentApi(APIView):
    """藍新支付 mock 測試 API。

    提供買家建立付款交易與查詢最新 mock 支付紀錄。
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request, order_id: int):
        """讀取某張訂單目前最新的藍新支付 mock 紀錄。"""
        user = get_demo_user(request)
        try:
            record = newebpay_payment_service.get_payment_record(order_id, user["username"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        if not record:
            return _error("Payment record not found.", status.HTTP_404_NOT_FOUND)
        return Response(record)

    def post(self, request, order_id: int):
        """建立一筆新的藍新支付 mock 交易。"""
        user = get_demo_user(request)
        payload = _validated(sz.NewebpayPaymentCreateSerializer, request.data)
        try:
            record = newebpay_payment_service.create_payment_request(
                order_id,
                user["username"],
                return_url=str(payload.get("return_url", "")),
                client_back_url=str(payload.get("client_back_url", "")),
                note=str(payload.get("note", "")),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(record, status=status.HTTP_201_CREATED)


class NewebpayPaymentCallbackApi(APIView):
    """藍新支付 mock callback 測試入口。"""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """模擬藍新支付以 callback/webhook 回傳交易狀態。"""
        payload = _validated(sz.NewebpayPaymentCallbackSerializer, request.data)
        try:
            record = newebpay_payment_service.handle_payment_callback(
                trade_no=str(payload["trade_no"]),
                status_value=str(payload["status"]),
                paid_amount=str(payload.get("paid_amount", "")),
                result_message=str(payload.get("result_message", "")),
                raw_payload=dict(request.data),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"detail": "NewebPay payment mock callback processed.", "record": record})


class SellerOrdersApi(APIView):
    """提供賣家訂單列表的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """回傳賣家訂單列表。"""
        user = get_demo_user(request)
        params = _validated(sz.SellerOrdersQuerySerializer, request.query_params)
        items = order_service.list_orders_for_seller(
            user["username"],
            date_from=str(params.get("date_from", "")),
            date_to=str(params.get("date_to", "")),
        )
        return Response({"items": items})


class SellerNewebpayLogisticsApi(APIView):
    """藍新物流 mock 測試 API。

    提供賣家建立托運單與查詢該張訂單最新的物流 mock 紀錄。
    """

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request, order_id: int):
        """讀取賣家可見訂單目前最新的藍新物流 mock 紀錄。"""
        user = get_demo_user(request)
        try:
            record = newebpay_logistics_service.get_logistics_record(order_id, user["username"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        if not record:
            return _error("Logistics record not found.", status.HTTP_404_NOT_FOUND)
        return Response(record)

    def post(self, request, order_id: int):
        """建立一筆藍新物流 mock 托運單。"""
        user = get_demo_user(request)
        payload = _validated(sz.NewebpayLogisticsCreateSerializer, request.data)
        try:
            record = newebpay_logistics_service.create_logistics_request(
                order_id,
                user["username"],
                store_type=str(payload.get("store_type", "")),
                temperature=str(payload.get("temperature", "")),
                shipment_note=str(payload.get("shipment_note", "")),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(record, status=status.HTTP_201_CREATED)


class NewebpayLogisticsCallbackApi(APIView):
    """藍新物流 mock callback 測試入口。"""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """模擬藍新物流 callback/webhook 更新配送狀態。"""
        payload = _validated(sz.NewebpayLogisticsCallbackSerializer, request.data)
        try:
            record = newebpay_logistics_service.handle_logistics_callback(
                logistics_no=str(payload["logistics_no"]),
                status_value=str(payload["status"]),
                result_message=str(payload.get("result_message", "")),
                raw_payload=dict(request.data),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"detail": "NewebPay logistics mock callback processed.", "record": record})


class BuyerNewebpaySandboxPaymentPrepareApi(APIView):
    """準備藍新正式 sandbox 支付 form payload。

    這支 API 不直接向藍新送單，而是回傳前端需要 POST 到藍新 gateway 的欄位資料。
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request, order_id: int):
        """回傳藍新 sandbox 支付設定摘要。"""
        return Response(newebpay_payment_real_service.get_runtime_summary(order_id=order_id))

    def post(self, request, order_id: int):
        """依訂單內容組出藍新支付 sandbox form payload。"""
        user = get_demo_user(request)
        payload = _validated(sz.NewebpaySandboxPaymentPrepareSerializer, request.data)
        try:
            prepared = newebpay_payment_real_service.prepare_checkout(
                order_id,
                user["username"],
                item_desc_override=str(payload.get("item_desc_override", "")),
                email=str(payload.get("email", "")),
                notify_url=str(payload.get("notify_url", "")),
                return_url=str(payload.get("return_url", "")),
                client_back_url=str(payload.get("client_back_url", "")),
            )
        except newebpay_payment_real_service.NewebpayConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except newebpay_payment_real_service.NewebpayDependencyError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        newebpay_payment_real_service.persist_prepared_attempt(prepared)
        return Response(prepared)


class NewebpaySandboxPaymentCallbackApi(APIView):
    """接收藍新正式 sandbox payment callback。"""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """驗證 TradeSha 並解密 TradeInfo。"""
        payload = _validated(sz.NewebpaySandboxPaymentCallbackSerializer, request.data)
        try:
            record = newebpay_payment_real_service.handle_callback(
                status=str(payload["Status"]),
                merchant_id=str(payload["MerchantID"]),
                trade_info=str(payload["TradeInfo"]),
                trade_sha=str(payload["TradeSha"]),
            )
        except newebpay_payment_real_service.NewebpayConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except newebpay_payment_real_service.NewebpayDependencyError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        newebpay_payment_real_service.persist_callback_record(record)
        return Response({"detail": "NewebPay sandbox payment callback processed.", "record": record})


class NewebpaySandboxPaymentReturnApi(APIView):
    """處理藍新前台支付完成後回到瀏覽器的導轉。"""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def _redirect_url(self, order_id: int | None, query: Dict[str, str]) -> str:
        frontend_origin = (os.getenv("STORE_FRONTEND_ORIGIN", "") or "").rstrip("/")
        if frontend_origin and order_id:
            base = f"{frontend_origin}/orders/{order_id}"
        elif frontend_origin:
            base = f"{frontend_origin}/orders"
        else:
            base = "/orders"
        suffix = urlencode(query)
        return f"{base}?{suffix}" if suffix else base

    def _handle(self, raw_payload: Dict[str, Any]) -> HttpResponseRedirect:
        required = {
            "Status": str(raw_payload.get("Status", "")),
            "MerchantID": str(raw_payload.get("MerchantID", "")),
            "TradeInfo": str(raw_payload.get("TradeInfo", "")),
            "TradeSha": str(raw_payload.get("TradeSha", "")),
        }
        if not all(required.values()):
            return HttpResponseRedirect(self._redirect_url(None, {"payment_callback": "invalid"}))

        try:
            record = newebpay_payment_real_service.handle_callback(
                status=required["Status"],
                merchant_id=required["MerchantID"],
                trade_info=required["TradeInfo"],
                trade_sha=required["TradeSha"],
            )
        except Exception as exc:  # pragma: no cover - redirect fallback
            return HttpResponseRedirect(self._redirect_url(None, {"payment_callback": "failed", "message": str(exc)}))

        newebpay_payment_real_service.persist_callback_record(record)
        decoded = record.get("decoded_payload") or {}
        result = decoded.get("Result") if isinstance(decoded, dict) else {}
        merchant_order_no = ""
        if isinstance(result, dict):
            merchant_order_no = str(result.get("MerchantOrderNo", ""))
        if not merchant_order_no and isinstance(decoded, dict):
            merchant_order_no = str(decoded.get("MerchantOrderNo", ""))
        order_id = _parse_order_id_from_merchant_order_no(merchant_order_no) if merchant_order_no else None
        return HttpResponseRedirect(
            self._redirect_url(
                order_id,
                {
                    "payment_callback": "success",
                    "trade_status": str(record.get("status", "")),
                    "merchant_order_no": merchant_order_no,
                },
            )
        )

    def get(self, request):
        """接受瀏覽器 GET 回傳。"""
        return self._handle(dict(request.query_params))

    def post(self, request):
        """接受藍新前台支付 POST 回傳。"""
        return self._handle(dict(request.data))


class SellerNewebpaySandboxLogisticsPrepareApi(APIView):
    """建立藍新物流 sandbox scaffold 資料。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request, order_id: int):
        """回傳藍新物流 scaffold 設定摘要。"""
        return Response(newebpay_logistics_real_service.get_runtime_summary())

    def post(self, request, order_id: int):
        """把賣家訂單整理成物流 sandbox scaffold payload。"""
        user = get_demo_user(request)
        payload = _validated(sz.NewebpaySandboxLogisticsPrepareSerializer, request.data)
        try:
            prepared = newebpay_logistics_real_service.prepare_logistics_request(
                order_id,
                user["username"],
                logistics_type=str(payload.get("logistics_type", "")) or "UNIMARTC2C",
                shipment_note=str(payload.get("shipment_note", "")),
            )
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        newebpay_logistics_real_service.persist_prepared_attempt(prepared)
        return Response(prepared)


class NewebpaySandboxLogisticsCallbackApi(APIView):
    """接收藍新物流 sandbox callback 原始資料。"""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """目前先原樣收件，供後續對照物流規格欄位。"""
        _validated(sz.NewebpaySandboxLogisticsCallbackSerializer, request.data)
        try:
            record = newebpay_logistics_real_service.handle_callback(dict(request.data))
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "NewebPay sandbox logistics callback processed.", "record": record})


class SellerOrderDetailApi(APIView):
    """提供賣家訂單明細的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request, order_id: int):
        """回傳賣家訂單明細。"""
        user = get_demo_user(request)
        order = order_service.get_order_detail_for_seller(order_id, user["username"])
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class SellerOrderUpdateApi(APIView):
    """提供賣家訂單狀態更新的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def post(self, request, order_id: int):
        """更新賣家履約狀態。"""
        user = get_demo_user(request)
        payload = _validated(sz.SellerOrderUpdateSerializer, request.data)
        try:
            order = order_service.update_seller_order(
                order_id,
                user["username"],
                seller_status=str(payload["seller_status"]),
                shipping_note=str(payload.get("shipping_note", "")),
                tracking_number=str(payload.get("tracking_number", "")),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(order)


class SellerSalesReportApi(APIView):
    """提供賣家銷售報表的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """回傳賣家銷售報表。"""
        user = get_demo_user(request)
        params = _validated(sz.SellerOrdersQuerySerializer, request.query_params)
        report = order_service.build_sales_report(
            user["username"],
            date_from=str(params.get("date_from", "")),
            date_to=str(params.get("date_to", "")),
        )
        return Response(report)


class AdminDashboardApi(APIView):
    """提供後台儀表板資料的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳後台摘要。"""
        return Response(admin_portal.build_dashboard())


class AdminOrdersApi(APIView):
    """提供後台訂單列表的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳後台訂單列表。"""
        params = _validated(sz.AdminOrdersQuerySerializer, request.query_params)
        items = order_service.list_orders_for_admin(
            date_from=str(params.get("date_from", "")),
            date_to=str(params.get("date_to", "")),
            status=str(params.get("status", "")),
            service_status=str(params.get("service_status", "")),
            q=str(params.get("q", "")),
        )
        return Response({"items": items})


class AdminOrderDetailApi(APIView):
    """提供後台訂單明細的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request, order_id: int):
        """回傳後台訂單明細。"""
        order = order_service.get_order_detail_for_admin(order_id)
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class AdminOrderServiceReviewApi(APIView):
    """提供後台售後審核的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, order_id: int):
        """審核取消 / 退款申請。"""
        payload = _validated(sz.ServiceReviewSerializer, request.data)
        try:
            order = order_service.review_service_request(
                order_id,
                approved=bool(payload["approved"]),
                note=str(payload.get("note", "")),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(order)


class AdminUsersApi(APIView):
    """提供後台會員列表的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳會員列表。"""
        params = _validated(sz.SearchUserQuerySerializer, request.query_params)
        items = auth_demo.list_users(
            search=str(params.get("q", "")),
            role=str(params.get("role", "")),
            account_status=str(params.get("account_status", "")),
        )
        return Response({"items": items})


class AdminProductsApi(APIView):
    """Provide the admin product management list."""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        params = _validated(sz.AdminProductsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_products(
            q=str(params.get("q", "")),
            status=str(params.get("status", "")),
            category=str(params.get("category", "")),
            brand=str(params.get("brand", "")),
            owner=str(params.get("owner", "")),
        )
        return Response({"items": items})


class AdminProductPublishApi(APIView):
    """Force publish a product from the admin console."""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        payload = _validated(sz.ProductForceArchiveSerializer, request.data)
        try:
            product = product_management.admin_publish_product(slug, note=str(payload.get("note", "")))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product)


class AdminProductDeleteApi(APIView):
    """Delete a product from the admin console."""

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, slug: str):
        try:
            product_management.admin_delete_product(slug)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminReviewsApi(APIView):
    """Provide review management list for admins."""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        params = _validated(sz.AdminReviewsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_reviews(
            q=str(params.get("q", "")),
            rating=str(params.get("rating", "")),
        )
        return Response({"items": items})


class AdminReviewDetailApi(APIView):
    """Allow admins to delete a review."""

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, review_id: int):
        try:
            admin_portal.delete_review(review_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminQuestionsApi(APIView):
    """Provide question management list for admins."""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        params = _validated(sz.AdminQuestionsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_questions(
            q=str(params.get("q", "")),
            answered=str(params.get("answered", "")),
        )
        return Response({"items": items})


class AdminQuestionDetailApi(APIView):
    """Allow admins to delete a question."""

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, question_id: int):
        try:
            admin_portal.delete_question(question_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminPostsApi(APIView):
    """Provide post management list for admins."""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        params = _validated(sz.AdminPostsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_posts(
            q=str(params.get("q", "")),
            topic=str(params.get("topic", "")),
        )
        return Response({"items": items})


class AdminPostDetailApi(APIView):
    """Allow admins to delete a forum post."""

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, post_id: int):
        try:
            admin_portal.delete_post(post_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserStatusApi(APIView):
    """提供後台會員狀態更新的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, username: str):
        """更新會員帳號狀態。"""
        payload = _validated(sz.AdminUserStatusUpdateSerializer, request.data)
        try:
            user = auth_demo.update_account_status(username, str(payload["account_status"]))
        except ValueError as exc:
            return _error(str(exc))
        return Response({"detail": "Account status updated.", "user": user})


class RegisterApi(APIView):
    """提供會員註冊的 API。"""

    permission_classes = [AllowAny]

    def post(self, request):
        """註冊新會員並自動登入。"""
        payload = _validated(sz.RegisterRequestSerializer, request.data)
        if payload["password"] != payload["password_confirm"]:
            return _error("Password confirmation does not match.")
        try:
            user = auth_demo.register_user(
                username=str(payload["username"]),
                display_name=str(payload["display_name"]),
                email=str(payload.get("email", "")),
                password=str(payload["password"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        auth_demo.login(request.session, user)
        return Response(
            {"detail": f"Welcome, {user['display_name']}. Your account is ready.", "user": user},
            status=status.HTTP_201_CREATED,
        )


class LoginApi(APIView):
    """提供會員登入的 API。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=sz.LoginRequestSerializer,
        responses={
            200: inline_serializer(
                name="LoginResponse",
                fields={
                    "detail": serializers.CharField(),
                    "user": sz.DemoUserSerializer(),
                },
            ),
            400: OpenApiResponse(description="Invalid username or password."),
        },
    )
    def post(self, request):
        """登入會員並寫入 session。"""
        payload = _validated(sz.LoginRequestSerializer, request.data)
        user = auth_demo.authenticate(str(payload["username"]), str(payload["password"]))
        if not user:
            return _error("Invalid username or password.")
        auth_demo.login(request.session, user)
        return Response({"detail": f"Signed in as {user['display_name']}.", "user": user})


class LogoutApi(APIView):
    """提供會員登出的 API。"""

    permission_classes = [AllowAny]

    def post(self, request):
        """清除登入 session。"""
        auth_demo.logout(request.session)
        return Response({"detail": "Signed out.", "user": None})


class MeProfileApi(APIView):
    """提供會員資料查詢與更新的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳目前會員資料。"""
        return Response({"user": get_demo_user(request)})

    def post(self, request):
        """更新會員資料。"""
        current_user = get_demo_user(request)
        payload = _validated(sz.ProfileUpdateSerializer, request.data)
        new_password = str(payload.get("new_password", ""))
        confirm_password = str(payload.get("confirm_password", ""))
        if new_password and new_password != confirm_password:
            return _error("Password confirmation does not match.")
        try:
            user = auth_demo.update_profile(
                current_user["username"],
                display_name=str(payload["display_name"]),
                email=str(payload.get("email", "")),
                new_password=new_password,
            )
        except ValueError as exc:
            return _error(str(exc))
        auth_demo.login(request.session, user)
        return Response({"detail": "Profile updated.", "user": user})


class MeShippingRulesApi(APIView):
    """Provide seller-level shipping rule read/update APIs."""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """Return current seller shipping rules."""
        user = get_demo_user(request)
        return Response(auth_demo.get_seller_shipping_rules(user["username"]))

    def put(self, request):
        """Update seller shipping rules."""
        user = get_demo_user(request)
        payload = _validated(sz.SellerShippingRulesSerializer, request.data)
        try:
            rules = auth_demo.update_seller_shipping_rules(
                user["username"],
                home_delivery_enabled=bool(payload["home_delivery_enabled"]),
                home_delivery_fee=str(payload["home_delivery_fee"]),
                convenience_store_enabled=bool(payload["convenience_store_enabled"]),
                convenience_store_fee=str(payload["convenience_store_fee"]),
                free_shipping_threshold=str(payload["free_shipping_threshold"]),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response({"detail": "Shipping rules updated.", "rules": rules})


class SellerRequestApi(APIView):
    """提供賣家申請送出的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request):
        """送出賣家申請。"""
        user = get_demo_user(request)
        try:
            updated = auth_demo.request_seller_role(user["username"])
        except ValueError as exc:
            return _error(str(exc))
        auth_demo.login(request.session, updated)
        return Response({"detail": "Seller access request submitted.", "user": updated})


class CartApi(APIView):
    """提供購物車查詢與折扣碼更新的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳購物車內容。"""
        shipping_method = str(
            request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY
        ).strip() or order_service.SHIPPING_METHOD_HOME_DELIVERY
        return Response(_build_cart_response(request.session, shipping_method=shipping_method))

    def post(self, request):
        """套用或清除折扣碼。"""
        payload = _validated(sz.CartCouponSerializer, request.data)
        shipping_method = str(
            request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY
        ).strip() or order_service.SHIPPING_METHOD_HOME_DELIVERY
        code = payload.get("code")
        if code in (None, ""):
            cart_service.apply_coupon(request.session, None)
            return Response(_build_cart_response(request.session, "Coupon removed.", shipping_method=shipping_method))
        applied = cart_service.apply_coupon(request.session, str(code))
        if not applied:
            return _error("Invalid coupon code.")
        return Response(_build_cart_response(request.session, "Coupon applied.", shipping_method=shipping_method))


class CartAddApi(APIView):
    """提供加入購物車的 API。"""

    permission_classes = [AllowAny]

    def post(self, request):
        """加入商品到購物車。"""
        payload = _validated(sz.CartAddSerializer, request.data)
        shipping_method = str(
            request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY
        ).strip() or order_service.SHIPPING_METHOD_HOME_DELIVERY
        product = product_management.get_visible_product(str(payload["slug"]), get_demo_user(request))
        if not product or not product_management.is_public_product(product):
            return _error("Product not found.", status.HTTP_404_NOT_FOUND)

        variant_id = str(payload.get("variant_id", "")).strip()
        qty = int(payload.get("qty", 1))
        variant = None
        price = float(product["price"])
        variant_name = ""
        sku = ""
        if variant_id:
            variant = product_management.get_variant(product, variant_id)
            if not variant:
                return _error("Selected variant is not available.")
            price = float(variant["price"])
            variant_name = str(variant.get("name", ""))
            sku = str(variant.get("sku", ""))
        try:
            cart_service.add_item(
                request.session,
                id=int(product["id"]),
                slug=str(product["slug"]),
                name=str(product["name"]),
                price=price,
                qty=qty,
                variant_id=variant_id,
                variant_name=variant_name,
                sku=sku,
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(_build_cart_response(request.session, "Added to cart.", shipping_method=shipping_method))


class CartItemApi(APIView):
    """提供購物車單項更新與刪除的 API。"""

    permission_classes = [AllowAny]

    def patch(self, request, item_key: str):
        """更新購物車單項數量。"""
        payload = _validated(sz.CartUpdateSerializer, request.data)
        shipping_method = str(
            request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY
        ).strip() or order_service.SHIPPING_METHOD_HOME_DELIVERY
        cart_service.update_qty(request.session, item_key, int(payload["qty"]))
        return Response(_build_cart_response(request.session, "Cart updated.", shipping_method=shipping_method))

    def delete(self, request, item_key: str):
        """刪除購物車單項。"""
        shipping_method = str(
            request.query_params.get("shipping_method") or order_service.SHIPPING_METHOD_HOME_DELIVERY
        ).strip() or order_service.SHIPPING_METHOD_HOME_DELIVERY
        cart_service.remove_item(request.session, item_key)
        return Response(_build_cart_response(request.session, "Item removed.", shipping_method=shipping_method))


class CheckoutPreviewApi(APIView):
    """提供結帳預覽的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳結帳預覽資訊。"""
        return Response(_build_checkout_preview_payload(request))


class CheckoutConfirmApi(APIView):
    """提供確認下單的 API。"""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request):
        """建立訂單並清空購物車。"""
        user = get_demo_user(request)
        payload = _validated(sz.CheckoutConfirmSerializer, request.data)
        try:
            order = order_service.create_order_from_cart(
                request.session,
                user,
                address_id=payload.get("address_id"),
                shipping_method=str(payload.get("shipping_method", order_service.SHIPPING_METHOD_HOME_DELIVERY)),
                pickup_store_brand=str(payload.get("pickup_store_brand", "")),
                pickup_store_code=str(payload.get("pickup_store_code", "")),
                pickup_store_name=str(payload.get("pickup_store_name", "")),
                pickup_store_address=str(payload.get("pickup_store_address", "")),
                payment_method=str(payload.get("payment_method", order_service.PAYMENT_METHOD_NEWEBPAY_CREDIT)),
                buyer_note=str(payload.get("buyer_note", "")),
            )
        except ValueError as exc:
            return _error(str(exc))
        detail = order_service.get_order_detail_for_user(order["id"], user["username"]) or order
        return Response(detail, status=status.HTTP_201_CREATED)


class BuyerCheckoutStoreMapPrepareApi(APIView):
    """Prepare NewebPay store-map form data for checkout."""

    permission_classes = [IsDemoAuthenticated]

    def post(self, request):
        """Return the auto-submit form payload for NewebPay convenience-store selection."""
        user = get_demo_user(request)
        payload = _validated(sz.CheckoutStoreMapPrepareSerializer, request.data)
        try:
            prepared = newebpay_logistics_real_service.prepare_store_map(
                user["username"],
                pickup_store_brand=str(payload.get("pickup_store_brand", "")),
                payment_method=str(payload.get("payment_method", "")),
                return_url=str(payload.get("return_url", "")),
            )
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except newebpay_logistics_real_service.NewebpayLogisticsDependencyError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc))
        newebpay_logistics_real_service.persist_store_map_prepare(prepared)
        return Response(prepared, status=status.HTTP_201_CREATED)


class AdminCheckoutStoreMapDebugApi(APIView):
    """Expose a staff-only debug summary for NewebPay store-map payload generation."""

    permission_classes = [IsAdminDemoUser]

    @extend_schema(
        request=sz.CheckoutStoreMapPrepareSerializer,
        responses={
            200: inline_serializer(
                name="AdminCheckoutStoreMapDebugResponse",
                fields={
                    "provider": serializers.CharField(),
                    "mode": serializers.CharField(),
                    "runtime": serializers.DictField(),
                    "prepared": serializers.DictField(),
                    "checks": serializers.DictField(),
                },
            ),
            400: OpenApiResponse(description="Invalid convenience-store brand or request payload."),
            403: OpenApiResponse(description="Admin session required."),
            503: OpenApiResponse(description="NewebPay logistics configuration or crypto dependency is unavailable."),
        },
    )
    def post(self, request):
        """Return the exact store-map plain params and generated form fields."""
        user = get_demo_user(request)
        payload = _validated(sz.CheckoutStoreMapPrepareSerializer, request.data)
        try:
            debug_payload = newebpay_logistics_real_service.build_store_map_debug_payload(
                user["username"],
                pickup_store_brand=str(payload.get("pickup_store_brand", "")),
                payment_method=str(payload.get("payment_method", "")),
                return_url=str(payload.get("return_url", "")),
            )
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except newebpay_logistics_real_service.NewebpayLogisticsDependencyError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc))
        return Response(debug_payload)


class BuyerCheckoutStoreSelectionApi(APIView):
    """Fetch a previously selected convenience-store for checkout."""

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """Return the selected store details for the current user."""
        user = get_demo_user(request)
        selection_token = str(request.query_params.get("token", "")).strip()
        if not selection_token:
            return _error("Missing store-map token.")
        record = newebpay_logistics_real_service.get_store_selection(selection_token, user["username"])
        if not record:
            return _error("Store-map selection not found.", status.HTTP_404_NOT_FOUND)
        return Response(record)


class NewebpayStoreMapCallbackApi(APIView):
    """Receive the NewebPay convenience-store map callback."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """Persist the selected store so checkout can read it after browser return."""
        payload = _validated(sz.NewebpayStoreMapCallbackSerializer, request.data)
        try:
            record = newebpay_logistics_real_service.handle_store_map_callback(payload)
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc))
        return Response({"detail": "NewebPay store-map callback processed.", "record": record})


class NewebpayStoreMapReturnRelayView(APIView):
    """Relay NewebPay store-map browser return through a short backend URL."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, selection_token: str):
        """Redirect NewebPay back to the final frontend checkout URL."""
        return HttpResponseRedirect(newebpay_logistics_real_service.get_store_map_client_return_url(selection_token))


class SellerProductsApi(APIView):
    """提供賣家商品列表與建立的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """回傳賣家商品列表。"""
        user = get_demo_user(request)
        return Response(
            {
                "items": product_management.list_products_for_user(user["username"]),
                "status_choices": product_management.get_status_choices(user),
            }
        )

    def post(self, request):
        """建立賣家商品。"""
        user = get_demo_user(request)
        payload = _payload_from_request(request)
        files = request.FILES.getlist("images")
        try:
            product = product_management.create_product(user, payload, uploaded_files=files)
        except ValueError as exc:
            return _error(str(exc))
        return Response(product, status=status.HTTP_201_CREATED)


class SellerProductDetailApi(APIView):
    """提供賣家商品明細、更新與刪除的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request, slug: str):
        """回傳賣家商品明細。"""
        user = get_demo_user(request)
        product = _admin_or_owned_product_or_404(user, slug)
        if isinstance(product, Response):
            return product
        return Response(product)

    def put(self, request, slug: str):
        """更新賣家商品。"""
        user = get_demo_user(request)
        payload = _payload_from_request(request)
        files = request.FILES.getlist("images")
        try:
            if auth_demo.is_admin(user):
                product = product_management.admin_update_product(user, slug, payload, uploaded_files=files)
            else:
                product = product_management.update_product(user, slug, payload, uploaded_files=files)
        except ValueError as exc:
            message = str(exc)
            return _error(message, status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST)
        return Response(product)

    def delete(self, request, slug: str):
        """刪除賣家商品。"""
        user = get_demo_user(request)
        try:
            if auth_demo.is_admin(user):
                product_management.admin_delete_product(slug)
            else:
                product_management.delete_product(user, slug)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SellerProductArchiveApi(APIView):
    """提供賣家商品封存的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def post(self, request, slug: str):
        """封存賣家商品。"""
        user = get_demo_user(request)
        try:
            if auth_demo.is_admin(user):
                product = product_management.admin_archive_product(slug)
            else:
                product = product_management.archive_product(user, slug)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product)


class SellerProductDuplicateApi(APIView):
    """提供賣家商品複製的 API。"""

    permission_classes = [IsSellerOrAdminDemoUser]

    def post(self, request, slug: str):
        """複製商品為草稿。"""
        user = get_demo_user(request)
        try:
            product = product_management.duplicate_product_as_draft(user, slug)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product, status=status.HTTP_201_CREATED)


class StaffReviewDashboardApi(APIView):
    """提供後台賣家申請與商品管理的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳賣家申請與目前已上架商品。"""
        return Response(
            {
                "managed_products": product_management.list_moderation_products(),
                "seller_requests": auth_demo.list_seller_requests(),
            }
        )


class SellerRequestReviewApi(APIView):
    """提供賣家申請審核的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, username: str):
        """審核賣家申請。"""
        payload = _validated(sz.SellerRequestDecisionSerializer, request.data)
        try:
            user = auth_demo.review_seller_request(username, bool(payload["approved"]))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"user": user})


class AdminProductArchiveApi(APIView):
    """提供管理者強制下架商品的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        """將指定商品強制下架。"""
        payload = _validated(sz.ProductForceArchiveSerializer, request.data)
        try:
            product = product_management.admin_archive_product(slug, note=str(payload.get("note", "")))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product)


class LegacyProductReviewsApi(ProductReviewsApi):
    """與舊路由相容的商品評論 API alias。"""

    schema = None


class LegacyProductQuestionsApi(ProductQuestionsApi):
    """與舊路由相容的商品問答 API alias。"""

    schema = None


class LegacyProductAnswersApi(ProductAnswersApi):
    """與舊路由相容的商品回答 API alias。"""

    schema = None


class LegacyProductRecommendationsApi(ProductRecommendationsApi):
    """與舊路由相容的商品推薦 API alias。"""

    schema = None


class LegacyCommunityPostsApi(CommunityPostsApi):
    """與舊路由相容的社群文章 API alias。"""

    schema = None


class LegacyCommunityPostDetailApi(CommunityPostDetailApi):
    """與舊路由相容的社群單篇文章 API alias。"""

    schema = None


class LegacyCommunityRepliesApi(CommunityRepliesApi):
    """與舊路由相容的社群回覆 API alias。"""

    schema = None


class LegacyCommunityVoteApi(CommunityVoteApi):
    """與舊路由相容的社群投票 API alias。"""

    schema = None

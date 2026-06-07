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
from ..services import newebpay_logistics_real as newebpay_logistics_real_service
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


# ---------------------------------------------------------------------------
# Helper objects / helper functions
# 這一段屬於 API view 共用工具：
# - 把 request payload 整理成 service 可吃的格式
# - 把 service / repository 回傳的 dict 再整理成 API response
# - 避免每個 APIView 重複寫相同的驗證與序列化邏輯
# ---------------------------------------------------------------------------
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


def _serialize_product_category(category: Dict[str, Any]) -> Dict[str, Any]:
    """將商品分類主表整理成 API 輸出格式。"""
    return {
        "id": int(category.get("id", 0) or 0),
        "slug": str(category.get("slug") or ""),
        "label": str(category.get("name") or ""),
        "description": str(category.get("description") or ""),
        "is_active": bool(category.get("is_active", True)),
        "sort_order": int(category.get("sort_order", 0) or 0),
    }


def _serialize_product_categories(categories: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """批次整理商品分類資料。"""
    return [_serialize_product_category(category) for category in categories]


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
    current_user = get_demo_user(request)
    can_manage = _can_manage_community_post(current_user, item)
    item["can_edit"] = can_manage
    item["can_delete"] = can_manage
    voted_post_ids = community_service.list_voted_post_ids(
        username=(current_user or {}).get("username"),
        user_id=(current_user or {}).get("id"),
    )
    item["has_voted"] = int(item.get("id", 0) or 0) in voted_post_ids
    return item


def _serialize_community_posts(posts: Iterable[Dict[str, Any]], request) -> list[Dict[str, Any]]:
    """批次整理文章列表資料。"""
    current_user = get_demo_user(request)
    voted_post_ids = community_service.list_voted_post_ids(
        username=(current_user or {}).get("username"),
        user_id=(current_user or {}).get("id"),
    )
    items = []
    for post in posts:
        item = dict(post)
        can_manage = _can_manage_community_post(current_user, item)
        item["can_edit"] = can_manage
        item["can_delete"] = can_manage
        item["has_voted"] = int(item.get("id", 0) or 0) in voted_post_ids
        items.append(item)
    return items


def _build_product_list_payload(request, params: Dict[str, Any]) -> Dict[str, Any]:
    """依查詢條件建立商品列表回應。

    這裡集中處理三件事：
    - query string 正規化
    - 商品篩選 / 排序 / 分頁
    - 前端需要的 `facets` 與 `filters` 回顯
    """
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

    # 先取整份公開商品清單，facets 需要基於完整集合計算，不能只看分頁後結果。
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
    # 分頁在 API 層做切片，讓 service 專注於資料篩選與排序。
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
    """把購物車狀態整理成 API 回應格式。

    主要用途：
    - 給購物車頁即時顯示 items / totals
    - 給 checkout 預覽階段重用

    內容包含：
    - 商品清單
    - 折扣碼
    - 依運送方式計算後的 totals
    - 分賣家運費摘要
    """
    cart = cart_service.get_cart(session)
    items = []
    for raw_item in cart.get("items", {}).values():
        item = dict(raw_item)
        # 舊資料可能缺少這些展示欄位，這裡補預設值讓前端不用再做 defensive code。
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
    """建立 checkout 頁需要的完整預覽 payload。

    這個 helper 會把多個 service 的資料彙整成單一回應：
    - 購物車內容
    - 地址簿與預設地址
    - 發票資料
    - 運送 / 付款 / 超商品牌選項
    - 是否可直接送出訂單
    """
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
    # checkout 頁希望一次拿齊地址、發票與選項資料，避免頁面載入後再追多支 API。
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
    payload["selected_payment_method"] = order_service.PAYMENT_METHOD_NEWEBPAY
    payload["user"] = user
    payload["requires_login"] = user is None
    payload["can_confirm"] = bool(
        user and payload["item_count"] > 0 and default_address and not payload.get("detail")
    )
    return payload


def _build_dashboard_payload(user: Dict[str, str], session) -> Dict[str, Any]:
    """建立會員中心儀表板回應。

    來源 service：
    - `profile_service.build_profile_dashboard`

    目的：
    - 把會員中心首頁常用資料先組成固定格式
    - 避免前端需要額外發多支 API 才能畫出 dashboard
    """
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
    """回傳前端啟動畫面常用的全域狀態。

    這支 helper 專門給 app bootstrap / layout header 使用，
    只放「全站共同狀態」，避免把完整會員或訂單資料帶進來。
    """
    user = get_demo_user(request)
    return {
        "user": user,
        "cart_count": cart_service.count_items(request.session),
        "compare_count": len(personalization_service.get_compare_slugs(request.session)),
        "favorite_count": len(personalization_service.get_favorite_slugs(request.session)),
    }


# ---------------------------------------------------------------------------
# Banner / 首頁素材管理
# ---------------------------------------------------------------------------
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
    """提供管理者審核 banner 申請的 API。

    前端使用頁面：
    - staff Banner 管理 / 審核頁

    資料來源：
    - `banner_service.review_banner_application`

    功能：
    - 審核賣家或內部提交的 banner 申請
    - 決定是否核准上架，或寫入退回原因
    """

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
    """提供管理者調整 banner 排序的 API。

    前端使用頁面：
    - staff Banner 管理頁的拖曳排序操作

    資料來源：
    - `banner_service.reorder_banners`

    功能：
    - 依照前端送來的 banner id 清單重寫排序值
    - 讓首頁與其他版位顯示順序與管理端一致
    """

    permission_classes = [IsAdminDemoUser]

    def post(self, request):
        """依照送入 ID 清單更新排序。"""
        payload = _validated(sz.AdminBannerReorderSerializer, request.data)
        return Response({"items": banner_service.reorder_banners(list(payload["ids"]))})


def _parse_order_id_from_merchant_order_no(merchant_order_no: str) -> int | None:
    """從藍新商店訂單編號還原站內訂單 ID。

    來源：
    - `newebpay_payment_real_service.parse_order_id_from_merchant_order_no`

    用途：
    - callback / return 收到 `MerchantOrderNo` 後，找回原本的站內訂單
    - 讓前端瀏覽器導回 `/orders/{id}` 時能落到正確頁面
    """
    return newebpay_payment_real_service.parse_order_id_from_merchant_order_no(merchant_order_no)


def _payload_from_request(request) -> PayloadAdapter:
    """把 DRF request 內容整理成 product service 可直接使用的 payload。

    來源模組：
    - `rest_framework.request.Request`
    - `django.http.QueryDict`

    用途：
    - 商品建立 / 編輯流程目前同時支援 JSON 與 multipart/form-data
    - 這裡統一轉成 `PayloadAdapter`，讓 service 端可以用相同介面讀取多值欄位
    """
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


def _flatten_request_mapping(data: Any) -> Dict[str, Any]:
    """把 QueryDict 風格的 request payload 攤平成一般 dict。

    來源模組：
    - `django.http.QueryDict`

    用途：
    - 藍新 `ReturnURL` / `ClientBackURL` 這類回傳可能混用 GET 與 POST
    - 先把單值欄位還原成純字串，避免後續 callback handler 拿到 list 而驗證失敗
    """
    flattened: Dict[str, Any] = {}
    if isinstance(data, QueryDict):
        for key in data.keys():
            values = data.getlist(key)
            flattened[key] = values if len(values) > 1 else data.get(key)
        return flattened

    for key, value in dict(data).items():
        if isinstance(value, list) and len(value) == 1:
            flattened[key] = value[0]
        else:
            flattened[key] = value
    return flattened


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
    """依目前角色取得可管理的商品。

    規則：
    - 管理者可讀任意商品
    - 賣家只能讀自己的商品

    找不到時直接回傳統一的 404 Response，讓下游 view 不必重複判斷。
    """
    if auth_demo.is_admin(user):
        product = product_management.get_product_for_admin(slug)
    else:
        product = product_management.get_user_product(user["username"], slug)
    if not product:
        return _error("Product not found.", status.HTTP_404_NOT_FOUND)
    return product


# ---------------------------------------------------------------------------
# 公開商品瀏覽 / 商品內容 / 比價 / 推薦
# ---------------------------------------------------------------------------
class ProductListApi(APIView):
    """提供商品列表與條件篩選的 API。

    前端使用頁面：
    - 商品總覽頁
    - 分類頁
    - 搜尋結果頁

    主要流程：
    - 讀取 query string 篩選條件
    - 呼叫 `product_management` 做商品篩選、排序、分頁
    - 回傳商品清單、facets 與目前套用的 filters
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """處理商品列表查詢。"""
        params = _validated(sz.ProductListQuerySerializer, request.query_params)
        return Response(_build_product_list_payload(request, params))


class ProductCategoriesApi(APIView):
    """提供前台可用的商品分類主表。

    前端使用頁面：
    - 商品總覽篩選條件
    - 分類導覽
    - 賣家新增 / 編輯商品時的分類下拉選單

    資料來源：
    - `product_management.list_active_product_categories`
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳啟用中的商品分類清單。"""
        return Response({"items": _serialize_product_categories(product_management.list_active_product_categories())})


class ProductDetailApi(APIView):
    """提供單一商品詳情的 API。

    前端使用頁面：
    - 商品詳情頁

    主要流程：
    - 驗證商品是否公開可見
    - 呼叫 `product_management.prepare_product_for_display`
    - 回傳商品、變體、圖片、價格與個人化狀態
    """

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理商品詳情查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        return Response(_serialize_product(product, request))


class ProductReviewsApi(APIView):
    """提供商品評論查詢與建立的 API。

    前端使用頁面：
    - 商品詳情頁的評論區塊

    讀取：
    - 取得指定商品的公開評論清單

    寫入：
    - 需登入
    - 建立新評論後交給 `review_service`
    """

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
    """提供商品問答查詢與提問的 API。

    前端使用頁面：
    - 商品詳情頁的問答區塊

    讀取：
    - 取得指定商品的問題與回答

    寫入：
    - 需登入
    - 建立新問題後交給 `question_service`
    """

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理問答列表查詢。"""
        current_user = get_demo_user(request)
        product = _product_or_404(slug, current_user)
        if isinstance(product, Response):
            return product
        return Response(
            {
                "items": question_service.list_questions(
                    product["id"],
                    viewer_username=(current_user or {}).get("username"),
                    viewer_user_id=(current_user or {}).get("id"),
                )
            }
        )

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
        items = question_service.list_questions(product["id"], viewer_username=user["username"], viewer_user_id=user["id"])
        created = next((item for item in items if item["id"] == question["id"]), question)
        return Response(created, status=status.HTTP_201_CREATED)


class ProductAnswersApi(APIView):
    """提供商品問答回答建立的 API。

    前端使用頁面：
    - 商品詳情頁問答區塊的回答表單

    功能：
    - 對既有問題新增回答
    - 維持問題與回答的關聯結構
    """

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
            (
                item
                for item in question_service.list_questions(
                    product["id"],
                    viewer_username=user["username"],
                    viewer_user_id=user["id"],
                )
                if item["id"] == question_id
            ),
            None,
        )
        if not updated:
            return _error("Question not found.", status.HTTP_404_NOT_FOUND)
        return Response(updated, status=status.HTTP_201_CREATED)


class ProductRecommendationsApi(APIView):
    """提供商品推薦清單的 API。

    前端使用頁面：
    - 商品詳情頁的「相似商品 / 一起購買」區塊

    資料來源：
    - `recommendation_service`
    - 底層目前以 JSON 設定與 fallback 規則為主
    """

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


# ---------------------------------------------------------------------------
# 社群 / 論壇
# ---------------------------------------------------------------------------
class CommunityPostsApi(APIView):
    """提供社群文章列表與發文的 API。

    前端使用頁面：
    - 社群論壇列表頁

    讀取：
    - 依 topic 篩選文章

    寫入：
    - 需登入
    - 建立文章後交給 `community_service`
    """

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
    """提供社群文章投票的 API。

    前端使用頁面：
    - 社群文章列表
    - 社群文章詳情頁

    資料來源：
    - `community_service.upvote_post`

    功能：
    - 累加文章票數
    - 回傳最新票數，讓前端即時刷新
    """

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, post_id: int):
        """處理文章投票。"""
        user = get_demo_user(request)
        try:
            post = community_service.upvote_post(post_id, username=user["username"], user_id=user["id"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"id": post["id"], "votes": post["votes"], "has_voted": True})


# ---------------------------------------------------------------------------
# Auth / App bootstrap / 個人化
# ---------------------------------------------------------------------------
class MeApi(APIView):
    """提供目前登入會員資料的 API。

    前端使用頁面：
    - 全站 header
    - 首次啟動時判斷登入狀態

    功能：
    - 回傳目前 demo session 對應的會員 snapshot
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳目前 session 會員。"""
        return Response({"user": get_demo_user(request)})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AuthCsrfApi(APIView):
    """提供前端初始化所需的 CSRF cookie。

    前端使用頁面：
    - Next.js app 啟動時
    - 需要先取 CSRF token 才能發 POST / PUT / DELETE 的頁面

    來源模組：
    - Django CSRF middleware / `get_token`

    功能：
    - 提前發出 cookie 與 token，避免前端第一次寫入請求被 CSRF 擋下
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """發出 CSRF cookie 與 token。"""
        return Response({"detail": "CSRF cookie issued.", "csrfToken": get_token(request)})


class AppBootstrapApi(APIView):
    """提供前端 header / session 初始化資料。

    前端使用頁面：
    - Next.js app 啟動時的全域 hydration

    內容包含：
    - 目前登入會員
    - 購物車數量
    - 收藏數量
    - 比較清單數量
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳目前會員與購物車 / 收藏 / 比較數量。"""
        return Response(_build_app_bootstrap_payload(request))


class MeDashboardApi(APIView):
    """提供會員中心儀表板資料的 API。

    前端使用頁面：
    - 會員中心首頁

    資料來源：
    - `profile_service.build_profile_dashboard`

    內容包含：
    - 訂單摘要
    - 收藏 / 最近瀏覽
    - 自己的評論、問答、文章
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳會員中心摘要。"""
        user = get_demo_user(request)
        return Response(_build_dashboard_payload(user, request.session))


class FavoriteToggleApi(APIView):
    """提供商品收藏切換的 API。

    前端使用頁面：
    - 商品卡片
    - 商品詳情頁

    資料來源：
    - `personalization_service`

    目前收藏資料仍以 session / 使用者持久化 bucket 為主。
    """

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
    """提供商品比較切換的 API。

    前端使用頁面：
    - 商品卡片
    - 商品詳情頁

    功能：
    - 切換商品是否在比較清單中
    - 若清單有上限，會回傳被移除的舊 slug
    """

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
    """提供商品比較頁的比較清單。

    前端使用頁面：
    - 商品比較頁

    功能：
    - 依 session / 使用者 bucket 中的 compare slugs
    - 查回實際可展示的商品資料
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """讀取目前 session 的比較商品清單。"""
        user = get_demo_user(request)
        slugs = personalization_service.get_compare_slugs(request.session)
        products = product_management.get_compare_products(slugs, user)
        return Response({"items": _serialize_products(products), "slugs": slugs})


class MeAddressesApi(APIView):
    """提供會員地址簿查詢與建立的 API。

    前端使用頁面：
    - 會員地址管理頁
    - checkout 地址選擇區塊

    功能：
    - 列出會員地址
    - 建立新地址
    """

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
    """提供預設地址設定的 API。

    前端使用頁面：
    - 地址管理頁
    - checkout 預設地址切換

    功能：
    - 把某一筆地址標記成預設地址
    - 讓 checkout 預設帶入該收件資訊
    """

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
    """提供地址刪除的 API。

    前端使用頁面：
    - 地址管理頁

    功能：
    - 刪除會員地址簿中的一筆地址
    - 若刪除的是預設地址，實際處理由 `customer_center` 決定後續狀態
    """

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
    """提供發票資料查詢與更新的 API。

    前端使用頁面：
    - 發票設定頁
    - checkout 發票資訊摘要
    """

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
    """提供買家訂單列表的 API。

    前端使用頁面：
    - 我的訂單列表

    功能：
    - 列出目前會員的訂單摘要
    - 讓前端從列表頁進入明細頁
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳買家訂單列表。"""
        user = get_demo_user(request)
        return Response({"items": order_service.list_orders_for_user(user["username"])})


class BuyerOrderDetailApi(APIView):
    """提供買家訂單明細的 API。

    前端使用頁面：
    - 買家訂單詳情頁

    功能：
    - 取得完整訂單明細
    - 進入明細前先嘗試同步藍新付款狀態
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request, order_id: int):
        """回傳買家訂單明細。"""
        user = get_demo_user(request)
        newebpay_payment_real_service.sync_order_payment_state(order_id)
        order = order_service.get_order_detail_for_user(order_id, user["username"])
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class BuyerCancelRequestApi(APIView):
    """提供買家取消訂單申請的 API。

    前端使用頁面：
    - 買家訂單詳情頁的取消申請操作

    功能：
    - 建立一筆售後服務請求
    - 交由後台或賣家後續審核
    """

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
    """提供買家退款申請的 API。

    前端使用頁面：
    - 買家訂單詳情頁的退款申請操作

    功能：
    - 建立一筆退款類型的售後服務請求
    """

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


class BuyerOrderCompleteApi(APIView):
    """提供買家完成訂單的 API。

    前端使用頁面：
    - 買家訂單詳情頁

    功能：
    - 在賣家已標記出貨後，讓買家確認收貨並完成整筆訂單
    """

    permission_classes = [IsDemoAuthenticated]

    def post(self, request, order_id: int):
        """在買家確認收貨後，將可完成的賣家出貨分組標記為完成。"""
        user = get_demo_user(request)
        try:
            order = order_service.confirm_order_completion(order_id, user["username"])
        except ValueError as exc:
            return _error(str(exc))
        return Response(order)


class BuyerNewebpayPaymentApi(APIView):
    """提供買家訂單最近一次藍新付款紀錄。

    前端使用頁面：
    - 買家訂單詳情頁的付款資訊區塊

    功能：
    - 讀取最近一次藍新 payment record
    - 顯示付款狀態、付款方式、MerchantOrderNo、TradeNo 等資訊
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request, order_id: int):
        """讀取目前訂單最近一次藍新 payment record。"""
        user = get_demo_user(request)
        try:
            record = newebpay_payment_real_service.get_payment_record(order_id, user["username"])
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        if not record:
            return _error("Payment record not found.", status.HTTP_404_NOT_FOUND)
        return Response(record)


class SellerOrdersApi(APIView):
    """提供賣家訂單列表的 API。

    前端使用頁面：
    - 賣家訂單列表頁

    功能：
    - 依日期條件列出賣家可履約的訂單
    - 讓賣家從列表進入出貨明細
    """

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


# ---------------------------------------------------------------------------
# 藍新 sandbox 支付主流程
# ---------------------------------------------------------------------------
class BuyerNewebpaySandboxPaymentPrepareApi(APIView):
    """準備藍新正式 sandbox 支付 form payload。

    這支 API 不直接向藍新送單，而是回傳前端需要 POST 到藍新 gateway 的欄位資料。

    前端使用頁面：
    - 買家訂單詳情頁的「前往付款」

    功能：
    - 依訂單資料組出 TradeInfo / TradeSha
    - 保留送單前的 prepared payload，供 staff debug 檢查
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
    """接收藍新正式 sandbox payment callback。

    來源：
    - 藍新 `NotifyURL`

    功能：
    - 驗證 `TradeSha`
    - 解密 `TradeInfo`
    - 把藍新實際回傳資料落到 payment record / callback log
    """

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
                source="callback",
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
    """處理藍新前台支付完成後回到瀏覽器的導轉。

    來源：
    - 藍新 `ReturnURL`

    功能：
    - 接收瀏覽器帶回來的支付結果
    - 嘗試與 callback 相同地驗證 / 解密
    - 最後重新導向回前端訂單頁
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def _redirect_url(self, order_id: int | None, query: Dict[str, str]) -> str:
        """組出支付完成後要導回前端的訂單頁網址。

        規則：
        - 有 `STORE_FRONTEND_ORIGIN` 時，優先導回前端正式網址
        - 能解析出 `order_id` 時，直接落到單筆訂單頁
        - 否則退回訂單列表頁
        """
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
        """處理藍新前台 return 的共用主流程。

        這裡同時被 GET / POST 共用，目的有兩個：
        - 把不同來源的 payload 正規化成同一套欄位
        - 無論成功或失敗，都回傳可讓瀏覽器前往前端頁面的 redirect
        """
        required = {
            "Status": str(raw_payload.get("Status", "")),
            "MerchantID": str(raw_payload.get("MerchantID", "")),
            "TradeInfo": str(raw_payload.get("TradeInfo", "")),
            "TradeSha": str(raw_payload.get("TradeSha", "")),
        }
        if not all(required.values()):
            return HttpResponseRedirect(self._redirect_url(None, {"payment_callback": "invalid"}))

        try:
            # 前台 return 雖然是瀏覽器導回，但仍走與 NotifyURL 類似的驗證 / 解密流程，
            # 避免前後台對同一筆付款看到不同結果。
            record = newebpay_payment_real_service.handle_callback(
                status=required["Status"],
                merchant_id=required["MerchantID"],
                trade_info=required["TradeInfo"],
                trade_sha=required["TradeSha"],
                source="return",
            )
        except Exception as exc:  # pragma: no cover - redirect fallback
            return HttpResponseRedirect(self._redirect_url(None, {"payment_callback": "failed", "message": str(exc)}))

        newebpay_payment_real_service.persist_callback_record(record)
        decoded = record.get("decoded_payload") or {}
        merchant_order_no = newebpay_payment_real_service.extract_callback_result_fields(decoded)["merchant_order_no"]
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
        return self._handle(_flatten_request_mapping(request.query_params))

    def post(self, request):
        """接受藍新前台支付 POST 回傳。"""
        return self._handle(_flatten_request_mapping(request.data))


# ---------------------------------------------------------------------------
# 訂單 / 賣家履約 / 管理端訂單
# ---------------------------------------------------------------------------
class SellerOrderDetailApi(APIView):
    """提供賣家訂單明細的 API。

    前端使用頁面：
    - 賣家訂單詳情頁

    功能：
    - 顯示收件資訊、出貨分組、付款摘要
    - 進入前先同步藍新付款狀態，讓賣家與買家看到同一份付款資料
    """

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request, order_id: int):
        """回傳賣家訂單明細。"""
        user = get_demo_user(request)
        newebpay_payment_real_service.sync_order_payment_state(order_id)
        order = order_service.get_order_detail_for_seller(order_id, user["username"])
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class SellerOrderUpdateApi(APIView):
    """提供賣家訂單狀態更新的 API。

    前端使用頁面：
    - 賣家訂單詳情頁

    功能：
    - 更新賣家履約狀態
    - 保存物流單號與出貨備註
    """

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
    """提供賣家銷售報表的 API。

    前端使用頁面：
    - 賣家銷售報表頁

    功能：
    - 依日期條件彙整訂單數、銷量、營收、熱賣商品
    """

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
    """提供後台儀表板資料的 API。

    前端使用頁面：
    - staff / admin dashboard

    功能：
    - 彙整使用者、商品、訂單、內容審核的整體統計
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳後台摘要。"""
        return Response(admin_portal.build_dashboard())


class AdminOrdersApi(APIView):
    """提供後台訂單列表的 API。

    前端使用頁面：
    - staff 訂單管理頁

    功能：
    - 以平台視角查詢所有訂單
    - 支援日期、狀態、售後狀態、關鍵字等條件
    """

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
    """提供後台訂單明細的 API。

    前端使用頁面：
    - staff 訂單詳情頁

    功能：
    - 提供平台角度的完整訂單明細
    - 與買家 / 賣家視角不同，不受擁有者限制
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request, order_id: int):
        """回傳後台訂單明細。"""
        order = order_service.get_order_detail_for_admin(order_id)
        if not order:
            return _error("Order not found.", status.HTTP_404_NOT_FOUND)
        return Response(order)


class AdminOrderPaymentDebugApi(APIView):
    """提供管理者查看藍新付款 debug 資訊的 API。

    前端使用頁面：
    - staff / admin 訂單詳情頁的 payment debug 面板

    功能：
    - 顯示 prepared payload
    - 顯示 callback / return event
    - 顯示 query fallback 的錯誤或回應
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request, order_id: int):
        """讀取單筆訂單的付款 debug 資料。

        staff 會用這份 payload 對照：
        - prepare 階段送出了什麼
        - callback / return 回來了什麼
        - query fallback 是否補到狀態
        """
        try:
            payload = newebpay_payment_real_service.get_payment_debug(order_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(payload)


class AdminOrderServiceReviewApi(APIView):
    """提供後台售後審核的 API。

    前端使用頁面：
    - staff 訂單詳情頁

    功能：
    - 審核取消 / 退款申請
    - 將審核結果回寫到訂單售後欄位
    """

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
    """提供後台會員列表的 API。

    前端使用頁面：
    - staff 會員管理頁

    功能：
    - 搜尋會員
    - 依角色與帳號狀態做平台管理
    """

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
    """提供管理者商品列表的 API。

    前端使用頁面：
    - staff 商品管理頁

    功能：
    - 列出全站商品
    - 依狀態 / 關鍵字做平台層級管理
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳平台視角的商品管理列表。"""
        params = _validated(sz.AdminProductsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_products(
            q=str(params.get("q", "")),
            status=str(params.get("status", "")),
            category=str(params.get("category", "")),
            brand=str(params.get("brand", "")),
            owner=str(params.get("owner", "")),
        )
        return Response({"items": items})


class AdminProductPriceCompareSettingsApi(APIView):
    """提供管理者更新單一商品的比價設定。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        """更新商品的比價開關與搜尋關鍵字。"""
        payload = _validated(sz.ProductPriceCompareSettingsSerializer, request.data)
        try:
            product = product_management.admin_update_price_compare_settings(
                slug,
                enabled=bool(payload.get("enabled", False)),
                query=str(payload.get("query", "")),
            )
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response({"detail": "商品比價設定已更新。", "product": product})


class AdminProductCategoriesApi(APIView):
    """提供管理者檢視與建立商品分類主表。

    前端使用頁面：
    - staff 商品分類管理

    功能：
    - 查看所有分類，包含停用項目
    - 建立新的正式分類主表項目
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳所有商品分類，包含停用項目。"""
        return Response({"items": _serialize_product_categories(product_management.list_product_categories(include_inactive=True))})

    def post(self, request):
        """建立新的商品分類。"""
        payload = _validated(sz.ProductCategoryCreateSerializer, request.data)
        try:
            category = product_management.create_product_category(
                name=str(payload.get("name", "")),
                slug=str(payload.get("slug", "")),
                description=str(payload.get("description", "")),
                is_active=bool(payload.get("is_active", True)),
            )
        except ValueError as exc:
            return _error(str(exc))
        return Response(_serialize_product_category(category), status=status.HTTP_201_CREATED)


class AdminProductPublishApi(APIView):
    """提供管理者強制上架商品的 API。

    前端使用頁面：
    - staff 商品管理頁

    資料來源：
    - `product_management.admin_publish_product`

    功能：
    - 平台管理者可直接將指定商品改為上架狀態
    - 可附帶管理端備註，供後續追蹤
    """

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        """將指定商品強制改為上架狀態。"""
        payload = _validated(sz.ProductForceArchiveSerializer, request.data)
        try:
            product = product_management.admin_publish_product(slug, note=str(payload.get("note", "")))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product)


class AdminProductDeleteApi(APIView):
    """提供管理者刪除商品的 API。

    前端使用頁面：
    - staff 商品管理頁

    資料來源：
    - `product_management.admin_delete_product`

    功能：
    - 平台管理者可直接移除不合規或測試商品
    """

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, slug: str):
        """由平台管理者直接刪除商品。"""
        try:
            product_management.admin_delete_product(slug)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminReviewsApi(APIView):
    """提供管理者商品評論管理列表。

    前端使用頁面：
    - staff 評論管理頁

    資料來源：
    - `admin_portal.list_admin_reviews`

    功能：
    - 以平台視角搜尋與篩選評論
    - 供後續刪除或人工巡檢
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳平台評論管理列表。"""
        params = _validated(sz.AdminReviewsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_reviews(
            q=str(params.get("q", "")),
            rating=str(params.get("rating", "")),
        )
        return Response({"items": items})


class AdminReviewDetailApi(APIView):
    """提供管理者刪除單一評論的 API。

    前端使用頁面：
    - staff 評論管理頁

    功能：
    - 刪除違規、測試或需下架的評論內容
    """

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, review_id: int):
        try:
            admin_portal.delete_review(review_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminQuestionsApi(APIView):
    """提供管理者商品問答管理列表。

    前端使用頁面：
    - staff 問答管理頁

    資料來源：
    - `admin_portal.list_admin_questions`

    功能：
    - 搜尋與篩選商品問題
    - 協助平台巡檢未回答或不適當內容
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳平台問答管理列表。"""
        params = _validated(sz.AdminQuestionsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_questions(
            q=str(params.get("q", "")),
            answered=str(params.get("answered", "")),
        )
        return Response({"items": items})


class AdminQuestionDetailApi(APIView):
    """提供管理者刪除單一商品問題的 API。

    前端使用頁面：
    - staff 問答管理頁

    功能：
    - 刪除不適當、重複或測試資料
    """

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, question_id: int):
        try:
            admin_portal.delete_question(question_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminPostsApi(APIView):
    """提供管理者社群文章管理列表。

    前端使用頁面：
    - staff 社群內容管理頁

    資料來源：
    - `admin_portal.list_admin_posts`

    功能：
    - 以主題、關鍵字搜尋論壇文章
    - 協助平台巡檢與內容治理
    """

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳平台社群文章管理列表。"""
        params = _validated(sz.AdminPostsQuerySerializer, request.query_params)
        items = admin_portal.list_admin_posts(
            q=str(params.get("q", "")),
            topic=str(params.get("topic", "")),
        )
        return Response({"items": items})


class AdminPostDetailApi(APIView):
    """提供管理者刪除單篇論壇文章的 API。

    前端使用頁面：
    - staff 社群內容管理頁

    功能：
    - 刪除違規或測試貼文
    """

    permission_classes = [IsAdminDemoUser]

    def delete(self, request, post_id: int):
        try:
            admin_portal.delete_post(post_id)
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserStatusApi(APIView):
    """提供後台會員狀態更新的 API。

    前端使用頁面：
    - staff 會員管理頁

    資料來源：
    - `auth_demo.update_account_status`

    功能：
    - 變更會員帳號狀態，例如正常、停權、待審等
    """

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
    """提供會員註冊的 API。

    前端使用頁面：
    - 註冊頁

    資料來源：
    - `auth_demo.register_user`

    功能：
    - 建立新會員
    - 註冊成功後直接寫入 session，讓前端視同已登入
    """

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
    """提供會員登入的 API。

    前端使用頁面：
    - 登入頁

    資料來源：
    - `auth_demo.authenticate`
    - `auth_demo.login`

    功能：
    - 驗證帳密
    - 將會員 snapshot 寫入目前 session
    """

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
    """提供會員登出的 API。

    前端使用頁面：
    - header 登出按鈕

    資料來源：
    - `auth_demo.logout`

    功能：
    - 清掉目前登入 session
    - 讓前端恢復訪客狀態
    """

    permission_classes = [AllowAny]

    def post(self, request):
        """清除登入 session。"""
        auth_demo.logout(request.session)
        return Response({"detail": "Signed out.", "user": None})


class MeProfileApi(APIView):
    """提供會員資料查詢與更新的 API。

    前端使用頁面：
    - 會員資料頁

    資料來源：
    - `auth_demo.update_profile`

    功能：
    - 讀取目前會員基本資料
    - 更新顯示名稱、Email、密碼
    - 更新後重新寫入 session snapshot
    """

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
    """提供賣家運費規則查詢與更新的 API。

    前端使用頁面：
    - 賣家運費設定頁
    - checkout 運費試算依賴的賣家設定來源

    資料來源：
    - `auth_demo.get_seller_shipping_rules`
    - `auth_demo.update_seller_shipping_rules`

    功能：
    - 讀取目前賣家的宅配 / 超商啟用狀態與費用
    - 更新免運門檻與配送費設定
    """

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """讀取目前賣家的運費規則。"""
        user = get_demo_user(request)
        return Response(auth_demo.get_seller_shipping_rules(user["username"]))

    def put(self, request):
        """更新目前賣家的運費規則。"""
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
    """提供賣家申請送出的 API。

    前端使用頁面：
    - 會員資料 / 會員中心內的賣家申請入口

    功能：
    - 將目前會員標記為已送出賣家申請
    - 更新 session 內的使用者 snapshot
    """

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


# ---------------------------------------------------------------------------
# 購物車 / 結帳 / 超商選店
# ---------------------------------------------------------------------------
class CartApi(APIView):
    """提供購物車查詢與折扣碼更新的 API。

    前端使用頁面：
    - 購物車頁

    功能：
    - 讀取 cart snapshot
    - 套用 / 清除折扣碼
    - 依運送方式重算 totals
    """

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
    """提供加入購物車的 API。

    前端使用頁面：
    - 商品詳情頁
    - 其他有「加入購物車」按鈕的商品卡片

    功能：
    - 驗證商品與變體是否存在
    - 寫入 session cart 或登入會員的持久化 cart
    """

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
    """提供購物車單項更新與刪除的 API。

    前端使用頁面：
    - 購物車頁的數量調整與移除按鈕

    資料來源：
    - `cart_service.update_qty`
    - `cart_service.remove_item`

    功能：
    - 調整單一品項數量
    - 刪除單一購物車項目並重算 totals
    """

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
    """提供結帳預覽的 API。

    前端使用頁面：
    - checkout 頁

    功能：
    - 回傳地址、發票、運費、付款方式、便利商店品牌
    - 組合結帳頁渲染所需的完整 snapshot
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """回傳結帳預覽資訊。"""
        return Response(_build_checkout_preview_payload(request))


class CheckoutConfirmApi(APIView):
    """提供確認下單的 API。

    前端使用頁面：
    - checkout 頁送出訂單

    功能：
    - 依購物車建立訂單
    - 保存收件地址與訂單 snapshot
    - 下單後回傳訂單明細並清空 cart
    """

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
                payment_method=str(payload.get("payment_method", order_service.PAYMENT_METHOD_NEWEBPAY)),
                buyer_note=str(payload.get("buyer_note", "")),
            )
        except ValueError as exc:
            return _error(str(exc))
        detail = order_service.get_order_detail_for_user(order["id"], user["username"]) or order
        return Response(detail, status=status.HTTP_201_CREATED)


class BuyerCheckoutStoreMapPrepareApi(APIView):
    """準備藍新超商選店 store-map 表單資料。

    前端使用頁面：
    - checkout 超商取貨流程

    功能：
    - 回傳前端 auto-submit 到藍新的 store-map payload
    - 寫入 debug 記錄，方便 staff 排查選店流程
    """

    permission_classes = [IsDemoAuthenticated]

    def post(self, request):
        """回傳可 auto-submit 到藍新 store-map 的表單 payload。"""
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
    """提供 staff 檢視 store-map payload 的 debug API。

    前端使用頁面：
    - staff NewebPay store-map debug 面板

    功能：
    - 顯示明文參數、加密後 form fields、runtime 設定與檢查結果
    """

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
        """回傳 store-map 明文參數、加密欄位與 runtime 檢查結果。"""
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
    """讀取目前買家已選擇的超商門市資料。

    前端使用頁面：
    - checkout 選店返回後

    功能：
    - 依 token 讀取先前 callback 寫入的門市資料
    - 讓 checkout 可以回填門市代碼、名稱、地址
    """

    permission_classes = [IsDemoAuthenticated]

    def get(self, request):
        """回傳目前會員最近一次選定的超商門市資料。"""
        user = get_demo_user(request)
        selection_token = str(request.query_params.get("token", "")).strip()
        if not selection_token:
            return _error("Missing store-map token.")
        # callback 先把門市結果落地，checkout 回來後再用 token 查詢，避免直接信任前端 query string。
        record = newebpay_logistics_real_service.get_store_selection(selection_token, user["username"])
        if not record:
            return _error("Store-map selection not found.", status.HTTP_404_NOT_FOUND)
        return Response(record)


class NewebpayStoreMapCallbackApi(APIView):
    """接收藍新超商地圖 callback。

    來源：
    - 藍新物流 / store-map callback

    功能：
    - 保存門市選擇結果
    - 供 checkout 返回後查詢與回填
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        """保存藍新超商地圖選店結果，供 checkout 返回後查詢。"""
        payload = _validated(sz.NewebpayStoreMapCallbackSerializer, request.data)
        try:
            record = newebpay_logistics_real_service.handle_store_map_callback(payload)
        except newebpay_logistics_real_service.NewebpayLogisticsConfigurationError as exc:
            return _error(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except ValueError as exc:
            return _error(str(exc))
        return Response({"detail": "NewebPay store-map callback processed.", "record": record})


class NewebpayStoreMapReturnRelayView(APIView):
    """中繼藍新超商選店完成後的瀏覽器返回。

    功能：
    - 把藍新返回的短 backend URL 再轉向到前端 checkout 完成頁
    - 避免前端直接暴露複雜的 callback relay 細節
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, selection_token: str):
        """把藍新返回的 backend relay URL 再導回前端 checkout 頁。"""
        return HttpResponseRedirect(newebpay_logistics_real_service.get_store_map_client_return_url(selection_token))


# ---------------------------------------------------------------------------
# 賣家商品管理 / 平台內容審核
# ---------------------------------------------------------------------------
class SellerProductsApi(APIView):
    """提供賣家商品列表與建立的 API。

    前端使用頁面：
    - 賣家商品列表
    - 賣家新增商品頁

    功能：
    - 列出賣家自己的商品
    - 建立新商品，交由 `product_management` 處理圖片與變體
    """

    permission_classes = [IsSellerOrAdminDemoUser]

    def get(self, request):
        """回傳賣家商品列表與可用狀態選單。

        `status_choices` 會跟著目前使用者角色變化，
        讓賣家端與管理端共用同一份頁面時仍能顯示正確操作選項。
        """
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
        # 商品建立仍同時支援 multipart 與 JSON，先轉成 service 可共用的 payload。
        payload = _payload_from_request(request)
        files = request.FILES.getlist("images")
        try:
            product = product_management.create_product(user, payload, uploaded_files=files)
        except ValueError as exc:
            return _error(str(exc))
        return Response(product, status=status.HTTP_201_CREATED)


class SellerProductDetailApi(APIView):
    """提供賣家商品明細、更新與刪除的 API。

    前端使用頁面：
    - 賣家商品編輯頁

    功能：
    - 讀取單一商品
    - 更新商品主資料、圖片、變體
    - 刪除或管理者代編輯
    """

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
            # 管理者可代替賣家編修商品，所以依角色切到不同 service 入口。
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
    """提供賣家商品下架 / 封存的 API。

    前端使用頁面：
    - 賣家商品列表
    - 賣家商品編輯頁

    資料來源：
    - `product_management.archive_product`
    - 管理者可改走 `product_management.admin_archive_product`

    功能：
    - 將商品改為封存 / 下架狀態
    - 讓前台商品總覽不再顯示該商品
    """

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
    """提供賣家商品複製成草稿的 API。

    前端使用頁面：
    - 賣家商品列表

    資料來源：
    - `product_management.duplicate_product_as_draft`

    功能：
    - 以既有商品為範本快速建立草稿
    - 方便複製相近商品後再局部修改
    """

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
    """提供後台賣家申請與商品審核首頁資料。

    前端使用頁面：
    - staff 審核中心 / moderation dashboard

    資料來源：
    - `product_management.list_moderation_products`
    - `auth_demo.list_seller_requests`

    功能：
    - 同時顯示待關注商品與賣家申請
    - 作為管理端審核工作的首頁摘要
    """

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
    """提供賣家申請審核的 API。

    前端使用頁面：
    - staff 審核中心

    資料來源：
    - `auth_demo.review_seller_request`

    功能：
    - 核准或拒絕會員成為賣家
    - 將審核結果回寫到會員帳號角色 / 狀態
    """

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
    """提供管理者強制下架商品的 API。

    前端使用頁面：
    - staff 商品管理頁
    - staff 審核中心

    功能：
    - 平台可直接把指定商品改為下架 / 封存
    - 可附帶管理備註，供後續審核追蹤
    """

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        """將指定商品強制下架。"""
        payload = _validated(sz.ProductForceArchiveSerializer, request.data)
        try:
            product = product_management.admin_archive_product(slug, note=str(payload.get("note", "")))
        except ValueError as exc:
            return _error(str(exc), status.HTTP_404_NOT_FOUND)
        return Response(product)


# ---------------------------------------------------------------------------
# Legacy alias views
# 保留舊 route 對應，避免舊頁面或文件連結直接失效。
# 實際邏輯仍委派給 canonical DRF API view。
# ---------------------------------------------------------------------------
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

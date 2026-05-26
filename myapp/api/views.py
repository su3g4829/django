"""DRF API 視圖層。

這個模組負責把 HTTP 請求轉交給既有 service / repository，
並使用 DRF `Response` 回傳統一的 JSON 格式。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional

from django.middleware.csrf import get_token
from django.http import QueryDict
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..repositories import local_store
from ..services import admin_portal
from ..services import auth_demo
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

PAGE_SIZE = 2


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


def _serialize_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """將商品整理成 API 輸出格式。"""
    return product_management.prepare_product_for_display(product)


def _serialize_products(products: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """批次整理商品資料。"""
    return [_serialize_product(item) for item in products]


def _build_product_list_payload(params: Dict[str, Any]) -> Dict[str, Any]:
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
        "items": _serialize_products(items),
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


def _build_cart_response(session, detail: str = "") -> Dict[str, Any]:
    """把 session 購物車整理成 API 回應格式。"""
    cart = cart_service.get_cart(session)
    items = []
    for raw_item in cart.get("items", {}).values():
        item = dict(raw_item)
        item.setdefault("key", cart_service.make_item_key(item.get("slug", ""), item.get("variant_id", "")))
        item.setdefault("display_name", item.get("name", ""))
        item["line_total"] = round(float(item["price"]) * int(item["qty"]), 2)
        items.append(item)
    payload = {
        "items": items,
        "coupon": cart.get("coupon"),
        "item_count": cart_service.count_items(session),
        "totals": cart_service.compute_totals(session),
    }
    if detail:
        payload["detail"] = detail
    return payload


def _build_checkout_preview_payload(request) -> Dict[str, Any]:
    """建立結帳預覽回應。"""
    user = get_demo_user(request)
    payload = _build_cart_response(request.session)
    payload["default_address"] = customer_center.get_default_address(user["username"]) if user else None
    payload["invoice_profile"] = customer_center.get_invoice_profile(user["username"]) if user else {}
    payload["user"] = user
    payload["requires_login"] = user is None
    payload["can_confirm"] = bool(user and payload["item_count"] > 0)
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


class ProductListApi(APIView):
    """提供商品列表與條件篩選的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """處理商品列表查詢。"""
        params = _validated(sz.ProductListQuerySerializer, request.query_params)
        return Response(_build_product_list_payload(params))


class ProductDetailApi(APIView):
    """提供單一商品詳情的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, slug: str):
        """處理商品詳情查詢。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        return Response(product)


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
        """讀取單一商品的模擬比價結果。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        return Response(price_compare_service.get_price_comparison(product))


class ProductPriceCompareRefreshApi(APIView):
    """模擬重新抓價 API。

    這支 API 不會真的連外抓資料，而是：
    - 更新 mock 抓價時間
    - 微調 mock 價格

    目的在於讓前端能展示「重新抓價」這個操作流程。
    """

    permission_classes = [AllowAny]

    def post(self, request, slug: str):
        """模擬重新抓取單一商品的外站價格。"""
        product = _product_or_404(slug, get_demo_user(request))
        if isinstance(product, Response):
            return product
        result = price_compare_service.refresh_mock_price_comparison(product)
        return Response(
            {
                "detail": "模擬抓價已更新。",
                "result": result,
            }
        )


class CommunityPostsApi(APIView):
    """提供社群文章列表與發文的 API。"""

    permission_classes = [AllowAny]

    def get(self, request):
        """處理文章列表查詢。"""
        topic = str(request.query_params.get("topic", "")).strip().lower() or None
        return Response({"items": community_service.list_posts(topic)})

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
        return Response(detail, status=status.HTTP_201_CREATED)


class CommunityPostDetailApi(APIView):
    """提供社群單篇文章詳情的 API。"""

    permission_classes = [AllowAny]

    def get(self, request, post_id: int):
        """處理單篇文章查詢。"""
        post = community_service.get_post_detail(post_id)
        if not post:
            return _error("Post not found.", status.HTTP_404_NOT_FOUND)
        return Response(post)


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
        return Response(detail, status=status.HTTP_201_CREATED)


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
        return Response({"active": active, "slug": slug})


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
        return Response(newebpay_payment_real_service.get_runtime_summary())

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
        return Response({"detail": "NewebPay sandbox payment callback processed.", "record": record})


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
        return Response(_build_cart_response(request.session))

    def post(self, request):
        """套用或清除折扣碼。"""
        payload = _validated(sz.CartCouponSerializer, request.data)
        code = payload.get("code")
        if code in (None, ""):
            cart_service.apply_coupon(request.session, None)
            return Response(_build_cart_response(request.session, "Coupon removed."))
        applied = cart_service.apply_coupon(request.session, str(code))
        if not applied:
            return _error("Invalid coupon code.")
        return Response(_build_cart_response(request.session, "Coupon applied."))


class CartAddApi(APIView):
    """提供加入購物車的 API。"""

    permission_classes = [AllowAny]

    def post(self, request):
        """加入商品到購物車。"""
        payload = _validated(sz.CartAddSerializer, request.data)
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
        return Response(_build_cart_response(request.session, "Added to cart."))


class CartItemApi(APIView):
    """提供購物車單項更新與刪除的 API。"""

    permission_classes = [AllowAny]

    def patch(self, request, item_key: str):
        """更新購物車單項數量。"""
        payload = _validated(sz.CartUpdateSerializer, request.data)
        cart_service.update_qty(request.session, item_key, int(payload["qty"]))
        return Response(_build_cart_response(request.session, "Cart updated."))

    def delete(self, request, item_key: str):
        """刪除購物車單項。"""
        cart_service.remove_item(request.session, item_key)
        return Response(_build_cart_response(request.session, "Item removed."))


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
        try:
            order = order_service.create_order_from_cart(request.session, user)
        except ValueError as exc:
            return _error(str(exc))
        detail = order_service.get_order_detail_for_user(order["id"], user["username"]) or order
        return Response(detail, status=status.HTTP_201_CREATED)


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
        product = _owned_product_or_404(user, slug)
        if isinstance(product, Response):
            return product
        return Response(product)

    def put(self, request, slug: str):
        """更新賣家商品。"""
        user = get_demo_user(request)
        payload = _payload_from_request(request)
        files = request.FILES.getlist("images")
        try:
            product = product_management.update_product(user, slug, payload, uploaded_files=files)
        except ValueError as exc:
            message = str(exc)
            return _error(message, status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST)
        return Response(product)

    def delete(self, request, slug: str):
        """刪除賣家商品。"""
        user = get_demo_user(request)
        try:
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
    """提供後台審核儀表板的 API。"""

    permission_classes = [IsAdminDemoUser]

    def get(self, request):
        """回傳待審商品與賣家申請。"""
        return Response(
            {
                "pending_products": product_management.list_pending_products(),
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


class ProductReviewDecisionApi(APIView):
    """提供商品審核決策的 API。"""

    permission_classes = [IsAdminDemoUser]

    def post(self, request, slug: str):
        """審核商品上架申請。"""
        payload = _validated(sz.ProductReviewDecisionSerializer, request.data)
        try:
            product = product_management.review_product(
                slug,
                approved=bool(payload["approved"]),
                note=str(payload.get("note", "")),
            )
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

"""Django é é¢å±¤èç¸å®¹è·¯ç±å
¥å£ã

éåæ¨¡çµè² è²¬ï¼
1. æ¥æ¶ Django HTML é é¢è«æ±ã
2. å¼å« service / repository åå¾ææ´æ°è³æã
3. åå³æ¨¡æ¿é é¢ãJSON ç¸å®¹åææ CSV å¯åºã
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import csv
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from django.views.decorators.http import require_POST, require_http_methods

from .repositories import local_store
from .api.html_write_registry import HTML_WRITE_MIGRATIONS
from .api.route_registry import API_ROUTE_GROUPS
from .services import auth_demo
from .services import admin_portal
from .services import cart as cart_service
from .services import community as community_service
from .services import customer_center
from .services import orders as order_service
from .services import personalization as personalization_service
from .services import product_management
from .services import profile as profile_service
from .services import questions as question_service
from .services import recommendations as recommendation_service
from .services import reviews as review_service

PRODUCTS_PER_PAGE = 2


def _build_login_redirect(next_url: str):
    """å»ºç«ç»å
¥å°åç¶²åï¼ä¸¦ä¿ç `next` åæ¸ã

    Args:
        next_url: ç»å
¥å®æå¾è¦è¿åçç¶²åã
    """
    query = urlencode({"next": next_url})
    return redirect(f"/login/?{query}")


def _require_html_user(request) -> Optional[Dict[str, str]]:
    """è¦æ±ç®åè«æ±å¿
é å·²æç»å
¥æå¡ï¼ä¾ HTML é é¢ä½¿ç¨ã

    Args:
        request: Django `HttpRequest`ï¼æå¾ session è®åæå¡è³è¨ã
    """
    user = auth_demo.get_current_user(request.session)
    if user:
        return user
    messages.error(request, "Please log in first.")
    return None


def _require_api_user(request):
    """è¦æ±ç®åè«æ±å¿
é å·²æç»å
¥æå¡ï¼ä¾ API / JSON åæä½¿ç¨ã

    è¥å°æªç»å
¥ï¼åå³ `403` JSON é¯èª¤ã

    Args:
        request: Django `HttpRequest`ï¼æå¾ session è®åæå¡è³è¨ã
    """
    user = auth_demo.get_current_user(request.session)
    if user:
        return user, None
    return None, JsonResponse({"ok": False, "error": "Please log in first."}, status=403)


def _current_user(request) -> Optional[Dict[str, str]]:
    """å¾ session ååºç®åç»å
¥æå¡ã

    Args:
        request: Django `HttpRequest`ã
    """
    return auth_demo.get_current_user(request.session)


def _require_seller_user(request, next_url: str) -> Optional[Dict[str, str]]:
    """è¦æ±ç®åæå¡å
·åè³£å®¶æ¬éã

    Args:
        request: Django `HttpRequest`ã
        next_url: è¥æªç»å
¥æï¼ç»å
¥å¾è¦è¿åçç¶²åã
    """
    user = _require_html_user(request)
    if not user:
        return None
    if product_management.can_sell(user):
        return user
    messages.error(request, "Seller access is required. Please request seller approval first.")
    return None


def _require_admin_user(request, next_url: str) -> Optional[Dict[str, str]]:
    """è¦æ±ç®åæå¡å
·åç®¡çå¡æ¬éã

    Args:
        request: Django `HttpRequest`ã
        next_url: è¥æªç»å
¥æï¼ç»å
¥å¾è¦è¿åçç¶²åã
    """
    user = _require_html_user(request)
    if not user:
        return None
    if auth_demo.is_admin(user):
        return user
    messages.error(request, "Admin review access is required.")
    return None


def _parse_decimal(value: str) -> Decimal | None:
    """å°å­ä¸²è½æ `Decimal`ï¼å¤±ææåå³ `None`ã

    Args:
        value: ä¾èª query string æè¡¨å®çæå­æ¸å¼ã
    """
    if not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError):
        return None


def _format_datetime(value: str) -> str:
    """å° ISO æ¥ææéå­ä¸²æ ¼å¼åçºæ¬å°å¯è®æå­ã

    Args:
        value: ISO æ ¼å¼æ¥ææéå­ä¸²ã

    Returns:
        str: ä¾å¦ `2026-05-17 14:30` çæ¬å°åæå­ï¼è¥ç¡æ³è§£æååå³ç©ºå­ä¸²ã
    """
    parsed = parse_datetime(value) if value else None
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M") if parsed else ""


def _csv_response(filename: str):
    """å»ºç« Excel ååç CSV åæç©ä»¶ã

    Args:
        filename: ä¸è¼æé¡¯ç¤ºç CSV æªåã

    Returns:
        tuple[HttpResponse, csv.writer]: CSV response èå°æ writerã
    """
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response, lineterminator="\r\n")
    return response, writer


def _csv_text(value: Any) -> str:
    """å°ä»»æå¼è½æé©åå¯«å
¥ CSV çæå­ã

    Args:
        value: ä»»ä½è¦è¼¸åºçå¼ã

    Returns:
        str: é©åå¯«å
¥ CSV çæå­å
§å®¹ã
    """
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def api_route_record_view(request):
    """é¡¯ç¤º API è·¯ç±ç´éé ã

    Args:
        request: Django `HttpRequest`ã
    """
    summary = {
        "canonical_count": sum(1 for group in API_ROUTE_GROUPS for route in group["routes"] if route["status"] == "canonical"),
        "aliased_count": sum(1 for group in API_ROUTE_GROUPS for route in group["routes"] if route["status"] == "aliased"),
    }
    return render(
        request,
        "docs/api_route_record.html",
        {
            "route_groups": API_ROUTE_GROUPS,
            "summary": summary,
        },
    )


def html_write_migration_record_view(request):
    """é¡¯ç¤º HTML å¯«å
¥æµç¨é·ç§»ç´éé ã

    Args:
        request: Django `HttpRequest`ã
    """
    summary = {
        "migration_count": sum(len(group["items"]) for group in HTML_WRITE_MIGRATIONS),
        "group_count": len(HTML_WRITE_MIGRATIONS),
        "removed_count": sum(
            1
            for group in HTML_WRITE_MIGRATIONS
            for item in group["items"]
            if item.get("router_status") == "removed"
        ),
    }
    return render(
        request,
        "docs/html_write_migration.html",
        {
            "migration_groups": HTML_WRITE_MIGRATIONS,
            "summary": summary,
        },
    )


def _catalog_filters_from_request(request) -> Dict[str, Any]:
    """å¾åååè¡¨ request ä¸­æ´çç¯©é¸æ¢ä»¶ã

    Args:
        request: Django `HttpRequest`ï¼æè®å query string åæ¸ã

    Returns:
        dict: å¾çºç¯©é¸èæåºæç¨å°çæ¢ä»¶éåã
    """
    q = request.GET.get("q", "").strip().lower()
    category = request.GET.get("category", "").strip().lower()
    brand = request.GET.get("brand", "").strip().lower()
    tag = request.GET.get("tag", "").strip().lower()
    color = request.GET.get("color", request.GET.get("attr_color", "")).strip()
    size = request.GET.get("size", request.GET.get("attr_size", "")).strip()
    sort = request.GET.get("sort", "featured").strip().lower() or "featured"
    min_price = _parse_decimal(request.GET.get("min_price", ""))
    max_price = _parse_decimal(request.GET.get("max_price", ""))
    return {
        "q": q,
        "category": category,
        "brand": brand,
        "tag": tag,
        "color": color,
        "size": size,
        "sort": sort,
        "min_price": min_price,
        "max_price": max_price,
    }


def _render_product_catalog(
    request,
    *,
    base_products: list[Dict[str, Any]] | None = None,
    page_title: str = "ååç®é",
    page_intro: str = "ä½ å¯ä»¥å¨éè£¡çè¦½ååãå¥ç¨æ¢ä»¶ç¯©é¸ï¼ä¸¦æ¾å°é©åçååã",
    active_brand: str = "",
    active_category: str = "",
    template_name: str = "products/list.html",
):
    """ä¾ç
§ç¯©é¸æ¢ä»¶çµåååç®éé é¢ã

    Args:
        request: Django `HttpRequest`ã
        base_products: å¯é¸çåºç¤ååæ¸
å®ã
        page_title: é é¢æ¨é¡ã
        page_intro: é é¢ç°¡ä»æå­ã
        active_brand: ç¶åéå®çåçåç¨±ã
        active_category: ç¶åéå®çåé¡åç¨±ã
        template_name: è¦æ¸²æçæ¨¡æ¿è·¯å¾ã
    """
    products = list(base_products if base_products is not None else product_management.list_public_products())
    filters = _catalog_filters_from_request(request)
    if active_brand:
        filters["brand"] = active_brand.lower()
    if active_category:
        filters["category"] = active_category.lower()

    facets = product_management.build_catalog_facets(products)
    products = product_management.filter_products(
        products,
        q=filters["q"],
        category=filters["category"],
        brand=filters["brand"],
        tag=filters["tag"],
        min_price=filters["min_price"],
        max_price=filters["max_price"],
        color=filters["color"],
        size=filters["size"],
    )
    products = product_management.sort_products(products, filters["sort"])

    paginator = Paginator(products, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", "1"))

    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_string = query_params.urlencode()

    context: Dict[str, Any] = {
        "products": list(page_obj.object_list),
        "page_obj": page_obj,
        "q": filters["q"],
        "filters": {
            "category": filters["category"],
            "brand": filters["brand"],
            "tag": filters["tag"],
            "color": filters["color"],
            "size": filters["size"],
            "sort": filters["sort"],
            "min_price": request.GET.get("min_price", "").strip(),
            "max_price": request.GET.get("max_price", "").strip(),
        },
        "categories": facets["categories"],
        "brands": facets["brands"],
        "tags": facets["tags"],
        "colors": facets["colors"],
        "sizes": facets["sizes"],
        "query_string": query_string,
        "favorite_slugs": set(personalization_service.get_favorite_slugs(request.session)),
        "compare_slugs": set(personalization_service.get_compare_slugs(request.session)),
        "can_sell_products": product_management.can_sell(_current_user(request)),
        "page_title": page_title,
        "page_intro": page_intro,
        "current_brand_slug": slugify(active_brand) if active_brand else "",
        "current_category_slug": slugify(active_category) if active_category else "",
    }
    return render(request, template_name, context)


def product_list(request):
    """é¡¯ç¤ºååç®éé ã

    Args:
        request: Django `HttpRequest`ã
    """
    return _render_product_catalog(request)


def brand_detail(request, brand_slug: str):
    """?????????????

    Args:
        request: Django `HttpRequest`?
        brand_slug: ?? slug?
    """
    brand_name = product_management.get_brand_by_slug(brand_slug)
    if not brand_name:
        raise Http404("Brand not found")
    products = [
        product
        for product in product_management.list_public_products()
        if str(product.get("brand", "")).lower() == brand_name.lower()
    ]
    return _render_product_catalog(
        request,
        base_products=products,
        page_title=f"{brand_name} ????",
        page_intro=f"???? {brand_name} ????????????????????????",
        active_brand=brand_name,
    )


def category_detail(request, category_slug: str):
    """?????????????

    Args:
        request: Django `HttpRequest`?
        category_slug: ?? slug?
    """
    category_name = product_management.get_category_by_slug(category_slug)
    if not category_name:
        raise Http404("Category not found")
    products = [
        product
        for product in product_management.list_public_products()
        if str(product.get("category", "")).lower() == category_name.lower()
    ]
    return _render_product_catalog(
        request,
        base_products=products,
        page_title=f"{category_name.title()} ????",
        page_intro=f"?????? {category_name} ????????????????????",
        active_category=category_name,
    )


def product_compare_view(request):
    """é¡¯ç¤ºååæ¯è¼é ã

    Args:
        request: Django `HttpRequest`ã
    """
    compare_products = product_management.get_compare_products(
        personalization_service.get_compare_slugs(request.session),
    """é¡¯ç¤ºååè©³æé ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        }
    )
    spec_rows = [
        {
            "label": key,
            "values": [((product.get("specs", {}) if isinstance(product.get("specs"), dict) else {}).get(key, "-")) for product in compare_products],
        }
        for key in spec_keys
    ]
    context = {
        "products": compare_products,
        "spec_rows": spec_rows,
    }
    return render(request, "products/compare.html", context)


def product_detail(request, slug: str):
    """
    ??????????????????????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _current_user(request)
    product = product_management.get_visible_product(slug, user)
    if not product:
        raise Http404("Product not found")

    personalization_service.record_recent_view(request.session, product)
    selected_variant_id = request.GET.get("variant", "").strip()
    selected_variant = product_management.get_variant(product, selected_variant_id) if selected_variant_id else product.get("default_variant")
    selected_variant_stock = product_management.available_stock(product, (selected_variant or {}).get("id", ""))
    selected_image = (selected_variant or {}).get("image") or product.get("primary_image", "")
    display_images = []
    for image in [selected_image, *product.get("images", [])]:
        if image and image not in display_images:
            display_images.append(image)
    """é¡¯ç¤ºãæçå§å®¹ãåè¡¨æ¿é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        "reviews": review_service.list_reviews(product["id"]),
        "review_summary": review_service.summarize_reviews(product["id"]),
        "recommendations": recommendation_service.get_product_recommendations(product),
        "questions": question_service.list_questions(product["id"]),
        "question_summary": question_service.summarize_questions(product["id"]),
        "is_favorite": personalization_service.is_favorite(request.session, product["slug"]),
        "is_in_compare": personalization_service.is_in_compare(request.session, product["slug"]),
        "can_manage_product": product_management.can_manage_product(user, product),
        "is_public_product": product_management.is_public_product(product),
        "can_review_product": product_management.can_review_product(user),
        "available_stock": product_management.available_stock(product),
        "brand_slug": slugify(str(product.get("brand", ""))),
        "category_slug": slugify(str(product.get("category", ""))),
    }
    return render(request, "products/detail.html", context)
    """å»ºç«ååè¡¨å®é è¨­å¼èé¡¯ç¤ºè³æã
    
        Args:
            product: ååè³æå­å¸ã
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/")
    user_record = local_store.get_user_by_username(user["username"]) or {}
    context = {
        "dashboard": profile_service.build_profile_dashboard(user, request.session),
        "user_record": user_record,
        "addresses": customer_center.list_addresses(user["username"]),
        "invoice_profile": customer_center.get_invoice_profile(user["username"]),
        "seller_orders": order_service.list_orders_for_seller(user["username"]) if product_management.can_sell(user) else [],
    }
    return render(request, "me/dashboard.html", context)


def _build_product_form_payload(product: Dict[str, Any], request) -> Dict[str, Any]:
    """
    ????????????????????????

    ???
    - product??????????????????
    - request?Django ? HttpRequest ???????? session???????????
    """
    variants_text = "\n".join(
        "|".join(
            [
                str(item.get("name", "")),
                str(item.get("sku", "")),
                str(item.get("price", "")),
                str(item.get("stock", 0)),
                str((item.get("attributes", {}) or {}).get("color", "")),
                str((item.get("attributes", {}) or {}).get("size", "")),
                str(item.get("image_index", "") or ""),
            ]
    """é¡¯ç¤ºè³£å®¶çååç®¡çé ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        "compare_at_price": request.POST.get("compare_at_price", product.get("compare_at_price", "") or ""),
        "brand": request.POST.get("brand", product.get("brand", "")),
        "category": request.POST.get("category", product.get("category", "")),
        "tags": request.POST.get("tags", ", ".join(product.get("tags", [])) if isinstance(product.get("tags"), list) else product.get("tags", "")),
        "status": request.POST.get("status", product.get("status", "draft")),
        "specs_text": request.POST.get(
            "specs",
            "\n".join(f"{key}:{value}" for key, value in product.get("specs", {}).items()),
        ),
        "variants_text": request.POST.get("variants", variants_text),
        "slug": product.get("slug", ""),
        "stock": request.POST.get("stock", product.get("stock", 0)),
        "images": product.get("images", []),
        "review_note": product.get("review_note", ""),
    }


    """é¡¯ç¤ºååå»ºç«é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    """
    user = _require_seller_user(request, "/me/products/")
    if not user:
        return _build_login_redirect("/me/profile/") if not _current_user(request) else redirect("profile_edit")
    products = []
    for product in product_management.list_products_for_user(user["username"]):
        item = dict(product)
        item["created_at_display"] = _format_datetime(item.get("created_at", ""))
        item["updated_at_display"] = _format_datetime(item.get("updated_at", ""))
        products.append(item)
    context = {
        "products": products,
    }
    return render(request, "me/products.html", context)


@require_http_methods(["GET"])
    """é¡¯ç¤ºååç·¨è¼¯é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    user = _require_seller_user(request, "/me/products/create/")
    if not user:
        return _build_login_redirect("/me/products/create/") if not _current_user(request) else redirect("profile_edit")

    context = {
        "form_mode": "create",
        "form_title": "å»ºç«åå",
        "submit_label": "å²å­åå",
        "status_choices": product_management.get_status_choices(user),
        "product": _build_product_form_payload({}, request),
        "can_admin_review": auth_demo.is_admin(user),
    }
    return render(request, "products/form.html", context)


@require_http_methods(["GET"])
def product_edit_view(request, slug: str):
    """
    ????????????

    ???
    """å°ååè¨­çºå°å­çæã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    product = product_management.get_user_product(user["username"], slug)
    if not product:
        raise Http404("Product not found")

    context = {
        "form_mode": "edit",
        "form_title": f"ç·¨è¼¯ååï¼{product['name']}",
        "submit_label": "æ´æ°åå",
        "status_choices": product_management.get_status_choices(user),
        "product": _build_product_form_payload(product, request),
        "can_admin_review": auth_demo.is_admin(user),
    }
    return render(request, "products/form.html", context)
    """åªé¤è³£å®¶çååã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _require_seller_user(request, f"/me/products/{slug}/edit/")
    if not user:
        return _build_login_redirect(f"/me/products/{slug}/edit/") if not _current_user(request) else redirect("profile_edit")
    try:
        product = product_management.archive_product(user, slug)
    except ValueError:
        raise Http404("Product not found")
    messages.info(request, f"Product {product['name']} archived.")
    return redirect("my_products")
    """è¤è£½ååçºæ°èç¨¿ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _require_seller_user(request, f"/me/products/{slug}/edit/")
    if not user:
        return _build_login_redirect(f"/me/products/{slug}/edit/") if not _current_user(request) else redirect("profile_edit")
    try:
        product_management.delete_product(user, slug)
    except ValueError:
        raise Http404("Product not found")
    messages.info(request, "Product deleted.")
    """é¡¯ç¤ºå¾å°å¯©æ ¸åè¡¨æ¿ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ?????????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _require_seller_user(request, f"/me/products/{slug}/edit/")
    if not user:
        return _build_login_redirect(f"/me/products/{slug}/edit/") if not _current_user(request) else redirect("profile_edit")
    try:
        duplicate = product_management.duplicate_product_as_draft(user, slug)
    except ValueError:
        raise Http404("Product not found")
    messages.success(request, f"Draft copy created: {duplicate['name']}.")
    return redirect("my_products")

    """æäº¤è³£å®¶ç³è«ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_admin_user(request, "/staff/reviews/")
    if not user:
        return _build_login_redirect("/staff/reviews/") if not _current_user(request) else redirect("me")
    context = {
        "pending_products": product_management.list_pending_products(),
        "seller_requests": auth_demo.list_seller_requests(),
    }
    return render(request, "staff/review_dashboard.html", context)


# Deprecated HTML write handlers:
# - Retained for backward compatibility and existing tests/incoming links
    """èçè³£å®¶ç³è«å¯©æ ¸ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            username: æå¡å¸³èã
            action: æä½åç¨±æå¯©æ ¸åä½ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/profile/")
    try:
        auth_demo.request_seller_role(user["username"])
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Seller access request submitted.")
    return redirect("profile_edit")


@require_POST
def seller_request_review_view(request, username: str, action: str):
    """
    """èçååå¯©æ ¸æ±ºç­ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
            action: æä½åç¨±æå¯©æ ¸åä½ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    if not user:
        return _build_login_redirect("/staff/reviews/") if not _current_user(request) else redirect("me")
    if action not in {"approve", "reject"}:
        raise Http404("Unknown action")
    approved = action == "approve"
    try:
        reviewed_user = auth_demo.review_seller_request(username, approved=approved)
    except ValueError:
        raise Http404("User not found")
    message = f"Seller request for {reviewed_user['display_name']} {'approved' if approved else 'rejected'}."
    messages.success(request, message)
    return redirect("staff_review_dashboard")


@require_POST
def product_review_decision_view(request, slug: str, action: str):
    """
    """é¡¯ç¤ºè¨»åé é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    """
    user = _require_admin_user(request, "/staff/reviews/")
    if not user:
        return _build_login_redirect("/staff/reviews/") if not _current_user(request) else redirect("me")
    if action not in {"approve", "reject"}:
        raise Http404("Unknown action")
    """é¡¯ç¤ºæå¡è³æç·¨è¼¯é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    messages.success(request, message)
    return redirect("staff_review_dashboard")


@require_http_methods(["GET"])
def register_view(request):
    """
    ???????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    next_url = request.GET.get("next") or "/"
    """é¡¯ç¤ºæå¡å°åç°¿é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ?????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/profile/")

    context = {
        "profile_user": auth_demo.get_current_user(request.session),
        "user_record": local_store.get_user_by_username(user["username"]) or {},
    """åªé¤æå®å°åã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            address_id: å°å IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ?????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/addresses/")

    context = {
        "addresses": customer_center.list_addresses(user["username"]),
    }
    return render(request, "me/addresses.html", context)

    """è¨­å®é è¨­å°åã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            address_id: å°å IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - request?Django ? HttpRequest ???????? session???????????
    - address_id???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/addresses/")
    try:
        customer_center.remove_address(user["username"], address_id)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.info(request, "Address deleted.")
    return redirect("address_book")

    """é¡¯ç¤ºç¼ç¥¨è³æé é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    - address_id???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/addresses/")
    try:
        customer_center.set_default_address(user["username"], address_id)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
    """åæååæ¶èçæã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/me/invoice/")

    context = {
        "invoice_profile": customer_center.get_invoice_profile(user["username"]),
    }
    return render(request, "me/invoice.html", context)
    """åæååæ¯è¼çæã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product:
        raise Http404("Product not found")
    active = personalization_service.toggle_favorite(request.session, product)
    if active:
        messages.success(request, f"Saved {product['name']} to favorites.")
    else:
        messages.info(request, f"Removed {product['name']} from favorites.")
    return redirect("product_detail", slug=slug)


@require_POST
def product_compare_toggle(request, slug: str):
    """
    """é¡¯ç¤ºç»å¥é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product or not product_management.is_public_product(product):
        raise Http404("Product not found")
    active, removed_slug = personalization_service.toggle_compare(request.session, product)
    if active:
        messages.success(request, f"Added {product['name']} to compare.")
    """å·è¡ç»åºä¸¦å°åé¦é ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        return redirect(next_url)
    return redirect("product_detail", slug=slug)


@require_http_methods(["GET"])
def login_view(request):
    """é¡¯ç¤ºç¤¾ç¾¤æç« åè¡¨é ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    next_url = request.GET.get("next") or "/"
    return render(request, "auth/login.html", {"next_url": next_url})


@require_POST
def logout_view(request):
    """
    ??????????? HTML ?????

    ???
    """é¡¯ç¤ºç¤¾ç¾¤æç« è©³æé ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
        """
def community_list(request):
    """
    ???????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    """é¡¯ç¤ºè²·å®¶è¨å®åè¡¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    return render(request, "community/list.html", context)


def community_post_detail(request, post_id: int):
    """
    ?????????????????

    ???
    """é¡¯ç¤ºè²·å®¶è¨å®æç´°ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
        """


def order_list(request):
    """
    ????????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
    """æäº¤è¨å®åæ¶ç³è«ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - order_id?????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect(f"/orders/{order_id}/")
    order = order_service.get_order_detail_for_user(order_id, user["username"])
    if not order:
        raise Http404("Order not found")
    return render(request, "orders/detail.html", {"order": order})


@require_POST
def order_cancel_request_view(request, order_id: int):
    """
    ????????????? HTML ?????
    """æäº¤è¨å®éæ¬¾ç³è«ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        return _build_login_redirect(f"/orders/{order_id}/")
    try:
        order_service.request_order_service(
            order_id,
            user["username"],
            request_type=order_service.SERVICE_REQUEST_CANCEL,
            reason=request.POST.get("reason", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Cancellation request submitted.")
    return redirect("order_detail", order_id=order_id)


@require_POST
def order_refund_request_view(request, order_id: int):
    """
    """é¡¯ç¤ºè³£å®¶è¨å®åè¡¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect(f"/orders/{order_id}/")
    try:
        order_service.request_order_service(
            order_id,
            user["username"],
            request_type=order_service.SERVICE_REQUEST_REFUND,
            reason=request.POST.get("reason", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    """é¡¯ç¤ºè³£å®¶è¨å®æç´°ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
        """
    ?????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_seller_user(request, "/me/sales/")
    if not user:
        return _build_login_redirect("/me/sales/") if not _current_user(request) else redirect("profile_edit")
    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
    }
    orders = order_service.list_orders_for_seller(user["username"], **filters)
    return render(request, "seller/orders_list.html", {"orders": orders, "filters": filters})

    """æ´æ°è³£å®¶å±¥ç´çæèåºè²¨è³è¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
        """
    - order_id?????????
    """
    user = _require_seller_user(request, f"/me/sales/{order_id}/")
    if not user:
        return _build_login_redirect(f"/me/sales/{order_id}/") if not _current_user(request) else redirect("profile_edit")
    order = order_service.get_order_detail_for_seller(order_id, user["username"])
    if not order:
        raise Http404("Order not found")
    context = {
        "order": order,
        "seller_status_choices": order_service.SELLER_STATUS_CHOICES,
    }
    return render(request, "seller/order_detail.html", context)


@require_POST
def seller_order_update(request, order_id: int):
    """
    ??????????????????????? HTML ?????
    """é¡¯ç¤ºè³£å®¶é·å®å ±è¡¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    if not user:
        return _build_login_redirect(f"/me/sales/{order_id}/") if not _current_user(request) else redirect("profile_edit")
    try:
        order = order_service.update_seller_order(
            order_id,
            user["username"],
            seller_status=request.POST.get("seller_status", ""),
            shipping_note=request.POST.get("shipping_note", ""),
            tracking_number=request.POST.get("tracking_number", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Seller order #{order['id']} updated.")
    """é¡¯ç¤ºå¹³å°å¾å°åè¡¨æ¿ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_seller_user(request, "/me/sales/report/")
    if not user:
        return _build_login_redirect("/me/sales/report/") if not _current_user(request) else redirect("profile_edit")
    """é¡¯ç¤ºå¾å°è¨å®åè¡¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    }
    return render(request, "seller/report.html", context)


def admin_dashboard_view(request):
    """
    ?????????????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_admin_user(request, "/staff/dashboard/")
    if not user:
        return _build_login_redirect("/staff/dashboard/") if not _current_user(request) else redirect("me")
    return render(request, "staff/dashboard.html", {"dashboard": admin_portal.build_dashboard()})
    """é¡¯ç¤ºå¾å°è¨å®æç´°ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_admin_user(request, "/staff/orders/")
    if not user:
        return _build_login_redirect("/staff/orders/") if not _current_user(request) else redirect("me")
    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
        "status": request.GET.get("status", "").strip(),
        "service_status": request.GET.get("service_status", "").strip(),
        "q": request.GET.get("q", "").strip(),
    """èçå¾å°å®å¾å¯©æ ¸ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            order_id: è¨å® IDã
            action: æä½åç¨±æå¯©æ ¸åä½ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - order_id?????????
    """
    user = _require_admin_user(request, f"/staff/orders/{order_id}/")
    if not user:
        return _build_login_redirect(f"/staff/orders/{order_id}/") if not _current_user(request) else redirect("me")
    order = order_service.get_order_detail_for_admin(order_id)
    if not order:
        raise Http404("Order not found")
    return render(request, "staff/order_detail.html", {"order": order})


@require_POST
    """é¡¯ç¤ºæå¡åè¡¨èæå°çµæã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - order_id?????????
    - action???????? approve / reject?
    """
    user = _require_admin_user(request, f"/staff/orders/{order_id}/")
    if not user:
        return _build_login_redirect(f"/staff/orders/{order_id}/") if not _current_user(request) else redirect("me")
    if action not in {"approve", "reject"}:
        raise Http404("Unknown action")
    try:
        order_service.review_service_request(order_id, approved=action == "approve", note=request.POST.get("note", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Service request updated.")
    """æ´æ°æå¡åç¨æåæ¬çæã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            username: æå¡å¸³èã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_admin_user(request, "/staff/users/")
    if not user:
        return _build_login_redirect("/staff/users/") if not _current_user(request) else redirect("me")
    filters = {
        "q": request.GET.get("q", "").strip(),
        "role": request.GET.get("role", "").strip(),
        "account_status": request.GET.get("account_status", "").strip(),
    }
    users = auth_demo.list_users(search=filters["q"], role=filters["role"], account_status=filters["account_status"])
    return render(request, "staff/users.html", {"users": users, "filters": filters})
    """å¯åºè³£å®¶è¨å® CSVã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - username????????
    """
    user = _require_admin_user(request, "/staff/users/")
    if not user:
        return _build_login_redirect("/staff/users/") if not _current_user(request) else redirect("me")
    try:
        auth_demo.update_account_status(username, request.POST.get("account_status", ""))
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Account status updated for {username}.")
    return redirect("admin_user_list")


def seller_orders_csv(request):
    """
    ???????????? CSV?

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_seller_user(request, "/me/sales/")
    if not user:
        return _build_login_redirect("/me/sales/") if not _current_user(request) else redirect("profile_edit")
    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
    }
    orders = order_service.list_orders_for_seller(user["username"], **filters)

    response, writer = _csv_response("seller-orders.csv")
    writer.writerow(
        [
            "order_id",
            "buyer",
            "created_at",
            "seller_status",
            "product",
            "qty",
    """å¯åºè³£å®¶å ±è¡¨ CSVã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
        for item in order["items"]:
            writer.writerow(
                [
                    _csv_text(order["id"]),
                    _csv_text(order["display_name"]),
                    _csv_text(order["created_at_display"]),
                    _csv_text(item["seller_status_label"]),
                    _csv_text(item["name"]),
                    _csv_text(item["qty"]),
                    _csv_text(item["line_total"]),
                    _csv_text(item["tracking_number"]),
                    _csv_text(item["shipping_note"]),
                ]
            )
    return response


def seller_report_csv(request):
    """
    ???????????? CSV?

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_seller_user(request, "/me/sales/report/")
    if not user:
        return _build_login_redirect("/me/sales/report/") if not _current_user(request) else redirect("profile_edit")
    filters = {
    """å»ºç«ç¤¾ç¾¤æç« ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
        """
    writer.writerow(["metric", "value"])
    writer.writerow(["date_from", _csv_text(report["filters"]["date_from"])])
    writer.writerow(["date_to", _csv_text(report["filters"]["date_to"])])
    writer.writerow(["order_count", _csv_text(report["order_count"])])
    writer.writerow(["units_sold", _csv_text(report["units_sold"])])
    writer.writerow(["revenue", _csv_text(report["revenue"])])
    writer.writerow(["pending_orders", _csv_text(report["status_counts"]["pending"])])
    writer.writerow(["shipped_orders", _csv_text(report["status_counts"]["shipped"])])
    writer.writerow(["completed_orders", _csv_text(report["status_counts"]["completed"])])
    writer.writerow([])
    writer.writerow(["top_product", "qty", "revenue"])
    for item in report["top_products"]:
        writer.writerow([_csv_text(item["name"]), _csv_text(item["qty"]), _csv_text(item["revenue"])])
    return response


@require_POST
def community_post_create(request):
    """
    ??????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """å»ºç«ç¤¾ç¾¤åè¦ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
        """
            topic=request.POST.get("topic", ""),
            author=user["display_name"],
            title=request.POST.get("title", ""),
            body=request.POST.get("body", ""),
            tags=request.POST.get("tags", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("community_list")

    messages.success(request, "Post submitted.")
    return redirect("community_post_detail", post_id=post["id"])


@require_POST
def community_reply_create(request, post_id: int):
    """
    ????????????? HTML ?????

    """èçç¤¾ç¾¤æç« æç¥¨ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
        """

    try:
        community_service.create_reply(
            post_id=post_id,
            author=user["display_name"],
            body=request.POST.get("body", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Reply submitted.")
    return redirect("community_post_detail", post_id=post_id)


    """å»ºç«ååè©è«ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    - post_id???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect(f"/community/{post_id}/")

    try:
        community_service.upvote_post(post_id)
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Post upvoted.")
    return redirect("community_post_detail", post_id=post_id)


@require_POST
def product_review_create(request, slug: str):
    """
    ??????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect(f"/products/{slug}/")

    product = product_management.get_visible_product(slug, user)
    if not product:
        raise Http404("Product not found")

    """å»ºç«åååé¡ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
            product_id=product["id"],
            author=user["display_name"],
            rating=rating,
            title=request.POST.get("title", ""),
            body=request.POST.get("body", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Review submitted.")

    return redirect("product_detail", slug=slug)


@require_POST
def product_question_create(request, slug: str):
    """
    ??????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    user = _require_html_user(request)
    if not user:
    """å»ºç«åååé¡åè¦ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
            question_id: åé¡ IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
            product_id=product["id"],
            author=user["display_name"],
            title=request.POST.get("title", ""),
            body=request.POST.get("body", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Question submitted.")

    return redirect("product_detail", slug=slug)


@require_POST
def product_answer_create(request, slug: str, question_id: int):
    """
    ????????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    - question_id???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect(f"/products/{slug}/")

    product = product_management.get_visible_product(slug, user)
    if not product:
        raise Http404("Product not found")
    """æä¾ååè©è«ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
            author_username=user["username"],
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Answer submitted.")

    return redirect("product_detail", slug=slug)


# Deprecated legacy JSON APIs.
# These functions are no longer wired in urls.py.
# Canonical and legacy-alias API traffic now goes through DRF views under:
# - /api/v1/... (canonical)
# - /api/... (legacy aliases routed to DRF)
@require_http_methods(["GET", "POST"])
def product_reviews_api(request, slug: str):
    """
    ?????????? legacy JSON API ????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product:
        raise Http404("Product not found")

    if request.method == "POST":
        user, error = _require_api_user(request)
        if error:
            return error

        try:
            rating = int(request.POST.get("rating", "0"))
        except ValueError:
            rating = 0

        try:
            review = review_service.create_review(
                product_id=product["id"],
                author=user["display_name"],
    """æä¾åååç­ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

        return JsonResponse({"ok": True, "review": review}, status=201)

    payload = {
        "product": {
            "id": product["id"],
            "slug": product["slug"],
            "name": product["name"],
        },
        "summary": review_service.summarize_reviews(product["id"]),
        "reviews": review_service.list_reviews(product["id"]),
    }
    return JsonResponse(payload)


@require_http_methods(["GET", "POST"])
def product_questions_api(request, slug: str):
    """
    ?????????? legacy JSON API ????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product:
        raise Http404("Product not found")

    if request.method == "POST":
        user, error = _require_api_user(request)
        if error:
            return error

        try:
            question = question_service.create_question(
                product_id=product["id"],
    """æä¾åååç­ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
            question_id: åé¡ IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        return JsonResponse({"ok": True, "question": question}, status=201)

    payload = {
        "product": {
            "id": product["id"],
            "slug": product["slug"],
            "name": product["name"],
        },
        "summary": question_service.summarize_questions(product["id"]),
        "questions": question_service.list_questions(product["id"]),
    }
    return JsonResponse(payload)


@require_POST
def product_answers_api(request, slug: str, question_id: int):
    """
    ???????????? legacy JSON API ????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    - question_id???????????
    """
    """æä¾ååæ¨è¦ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

    try:
        answer = question_service.create_answer(
            product_id=product["id"],
            question_id=question_id,
            author=user["display_name"],
            body=request.POST.get("body", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({"ok": True, "answer": answer}, status=201)


@require_http_methods(["GET"])
def product_recommendations_api(request, slug: str):
    """æä¾ç¤¾ç¾¤æç« åè¡¨ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product:
        raise Http404("Product not found")

    payload = {
        "product": {
            "id": product["id"],
            "slug": product["slug"],
            "name": product["name"],
        },
        "recommendations": recommendation_service.get_product_recommendations(product),
    }
    return JsonResponse(payload)


@require_http_methods(["GET", "POST"])
def community_posts_api(request):
    """
    ????????????????? legacy JSON API ????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    if request.method == "POST":
        user, error = _require_api_user(request)
        if error:
            return error

        try:
    """æä¾ç¤¾ç¾¤æç« è©³æç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        return JsonResponse({"ok": True, "post": post}, status=201)

    topic = request.GET.get("topic", "").strip().lower() or None
    return JsonResponse(
    """æä¾ç¤¾ç¾¤åè¦ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
@require_http_methods(["GET"])
def community_post_detail_api(request, post_id: int):
    """
    ?????????????? legacy JSON API ????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - post_id???????????
    """
    post = community_service.get_post_detail(post_id)
    if not post:
        raise Http404("Post not found")
    return JsonResponse({"post": post})


@require_POST
def community_replies_api(request, post_id: int):
    """
    ???????????? legacy JSON API ????
    """æä¾ç¤¾ç¾¤æç¥¨ç legacy JSON APIã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            post_id: ç¤¾ç¾¤æç«  IDã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        return error

    try:
        reply = community_service.create_reply(
            post_id=post_id,
            author=user["display_name"],
            body=request.POST.get("body", ""),
            author_username=user["username"],
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({"ok": True, "reply": reply}, status=201)

    """é¡¯ç¤ºè³¼ç©è»é é¢ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    - post_id???????????
    """
    user, error = _require_api_user(request)
    if error:
        return error

    try:
        post = community_service.upvote_post(post_id)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse({"ok": True, "votes": post["votes"]})


@require_http_methods(["GET"])
def cart_view(request):
    """å°ååå å¥è³¼ç©è»ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

    items = list(cart.get("items", {}).values())
    for item in items:
        item.setdefault("key", cart_service.make_item_key(item.get("slug", ""), item.get("variant_id", "")))
        item.setdefault("display_name", item.get("name", ""))
        item["line_total"] = item["price"] * item["qty"]

    context = {
        "items": items,
        "totals": cart_service.compute_totals(request.session),
        "coupon": cart.get("coupon"),
    }
    return render(request, "cart/cart.html", context)


@require_POST
def cart_add(request, slug: str):
    """
    ????????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    product = product_management.get_visible_product(slug, _current_user(request))
    if not product or not product_management.is_public_product(product):
        raise Http404("Product not found")

    try:
        qty = int(request.POST.get("qty", 1))
    except ValueError:
        qty = 1
    qty = max(1, qty)
    variant_id = request.POST.get("variant_id", "").strip()
    variant = product_management.get_variant(product, variant_id) if variant_id else None
    if product.get("has_variants") and not variant:
        messages.error(request, "Please choose a variant before adding this product.")
        return redirect("product_detail", slug=slug)

    stock = product_management.available_stock(product, variant_id)
    if stock is not None and qty > stock:
        label = variant["name"] if variant else product["name"]
        messages.error(request, f"Only {stock} units available for {label}.")
    """æ´æ°è³¼ç©è»é ç®æ¸éã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
        request.session,
        id=product["id"],
        slug=product["slug"],
        name=product["name"],
        price=(variant or product)["price"],
        qty=qty,
        variant_id=variant_id,
        variant_name=(variant or {}).get("name", ""),
        sku=(variant or {}).get("sku", ""),
    )
    added_label = f"{product['name']} - {variant['name']}" if variant else product["name"]
    messages.success(request, f"Added {added_label} x {qty} to cart.")
    """å¾è³¼ç©è»ç§»é¤ååã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
            slug: åå slugã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    try:
        qty = int(request.POST.get("qty", 1))
    """é¡¯ç¤ºçµå¸³é è¦½é ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """


@require_POST
def cart_remove(request, slug: str):
    """
    ???????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    - slug???? slug??????????????????
    """
    cart_service.remove_item(request.session, slug)
    messages.info(request, "Item removed from cart.")
    return redirect("cart")

    """ç¢ºèªä¸¦å»ºç«è¨å®ã
    
        Args:
            request: Django `HttpRequest` æ DRF request ç©ä»¶ã
    
        Returns:
            HttpResponse | JsonResponse: ?????? API ???
        """
    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    cart = cart_service.get_cart(request.session)
    items = list(cart.get("items", {}).values())
    totals = cart_service.compute_totals(request.session)
    user = _current_user(request)
    context = {
        "items": items,
        "totals": totals,
        "default_address": customer_center.get_default_address(user["username"]) if user else None,
        "invoice_profile": customer_center.get_invoice_profile(user["username"]) if user else {},
    }
    return render(request, "checkout/preview.html", context)


@require_POST
def checkout_confirm(request):
    """
    ??????????????? HTML ?????

    ???
    - request?Django ? HttpRequest ???????? session???????????
    """
    user = _require_html_user(request)
    if not user:
        return _build_login_redirect("/checkout/preview/")
    try:
        order = order_service.create_order_from_cart(request.session, user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("cart")
    return render(request, "checkout/confirm.html", {"order": order})

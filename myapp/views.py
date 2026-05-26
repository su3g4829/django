"""
myapp/views.py
---------------

這個模組現在只保留 Django 在前後端分離架構下仍需承擔的頁面職責：

- 舊 HTML 路由轉址到 Next.js 前端
- 後端文件頁
- 後端健康檢查之外的 CSV 匯出

買家 / 賣家 / 管理者的互動畫面已由 `frontend/` 下的 Next.js 負責，
不再由 Django template render。
"""
from __future__ import annotations

import csv
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.generic import RedirectView

from .api.html_write_registry import HTML_WRITE_MIGRATIONS
from .api.route_registry import API_ROUTE_GROUPS
from .services import auth_demo
from .services import orders as order_service
from .services import product_management


class FrontendRedirectView(RedirectView):
    """將舊的 Django 頁面路由轉址到 Next.js 前端路由。"""

    permanent = False
    query_string = True
    frontend_path = "/"

    def get_redirect_url(self, *args, **kwargs):
        """組合前端目標網址，並保留原本 query string。"""
        target_path = self.frontend_path.format(**kwargs)
        url = f"{settings.FRONTEND_ORIGIN}{target_path}"
        query = self.request.META.get("QUERY_STRING", "")
        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{query}"
        return url


def _build_login_redirect(next_url: str):
    """建立登入轉址，未登入者仍先走既有 Django 路由入口。"""
    return redirect(f"/login/?{urlencode({'next': next_url})}")


def _current_user(request):
    """從 session 取得目前 demo auth 使用者。"""
    return auth_demo.get_current_user(request.session)


def _require_user_page(request, next_url: str):
    """要求使用者先登入，否則導向登入頁。"""
    user = _current_user(request)
    if user:
        return user, None
    return None, _build_login_redirect(next_url)


def _require_seller_page(request, next_url: str):
    """要求使用者具備 seller 權限，否則導回會員資料頁。"""
    user, response = _require_user_page(request, next_url)
    if response:
        return None, response
    if product_management.can_sell(user):
        return user, None
    messages.error(request, "Seller access is required.")
    return None, redirect("profile_edit")


def _csv_response(filename: str):
    """建立 Excel 友善的 UTF-8 BOM CSV 回應。"""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response, lineterminator="\r\n")
    return response, writer


def _csv_text(value: Any) -> str:
    """將值轉成穩定的 CSV 文字格式。"""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def seller_orders_csv(request):
    """匯出賣家訂單明細 CSV。"""
    user, response = _require_seller_page(request, "/me/sales/")
    if response:
        return response

    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
    }
    orders = order_service.list_orders_for_seller(user["username"], **filters)
    response, writer = _csv_response("seller-orders.csv")
    writer.writerow(
        ["order_id", "buyer", "created_at", "seller_status", "product", "qty", "line_total", "tracking_number", "shipping_note"]
    )
    for order in orders:
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
    """匯出賣家銷售報表 CSV。"""
    user, response = _require_seller_page(request, "/me/sales/report/")
    if response:
        return response

    filters = {
        "date_from": request.GET.get("date_from", "").strip(),
        "date_to": request.GET.get("date_to", "").strip(),
    }
    report = order_service.build_sales_report(user["username"], **filters)
    response, writer = _csv_response("seller-report.csv")
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


def api_route_record_view(request):
    """顯示 DRF canonical / legacy API 對照文件頁。"""
    summary = {
        "canonical_count": sum(1 for group in API_ROUTE_GROUPS for route in group["routes"] if route.get("status") == "canonical"),
        "aliased_count": sum(1 for group in API_ROUTE_GROUPS for route in group["routes"] if route.get("legacy")),
    }
    return render(request, "docs/api_route_record.html", {"route_groups": API_ROUTE_GROUPS, "summary": summary})


def html_write_migration_record_view(request):
    """顯示舊 HTML write routes 已切換到 DRF 的遷移記錄頁。"""
    items = [item for group in HTML_WRITE_MIGRATIONS for item in group["items"]]
    summary = {
        "migration_count": len(items),
        "group_count": len(HTML_WRITE_MIGRATIONS),
        "removed_count": sum(1 for item in items if item.get("router_status") == "removed"),
    }
    return render(
        request,
        "docs/html_write_migration.html",
        {"migration_groups": HTML_WRITE_MIGRATIONS, "summary": summary},
    )

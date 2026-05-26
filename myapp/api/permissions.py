"""DRF 權限類別。

這個專案目前不是 Django 內建 `auth` + 資料庫會員系統，
而是用 demo session 保存目前登入會員。

因此這裡的 permission 類別，主要是把「目前 session 裡有沒有會員」
以及「會員角色是否符合需求」封裝成 DRF 可重用的權限判斷。
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from ..services import auth_demo


def get_demo_user(request):
    """
    從 request 的 session 取出目前登入會員。

    Args:
        request: DRF request 物件，可透過 `request.session` 讀取 demo 會員快照。

    Returns:
        dict | None: 若已登入則回傳會員資料，否則回傳 `None`。
    """
    return auth_demo.get_current_user(request.session)


class IsDemoAuthenticated(BasePermission):
    """
    要求使用者必須先登入 demo session。

    這個權限適合用在一般會員功能，例如：
    - 評論
    - 問答
    - 訂單查詢
    - 會員中心
    """

    message = "Please log in first."

    def has_permission(self, request, view):
        """
        判斷目前 request 是否已有登入會員。

        Args:
            request: DRF request。
            view: 目前執行中的 DRF view。

        Returns:
            bool: 已登入回傳 `True`，否則回傳 `False`。
        """
        return bool(get_demo_user(request))


class IsSellerOrAdminDemoUser(BasePermission):
    """
    要求使用者角色必須是賣家或管理員。

    這個權限適合用在：
    - 賣家商品管理
    - 賣家訂單中心
    - 少量允許管理員代看賣家頁面的情境
    """

    message = "Seller access is required."

    def has_permission(self, request, view):
        """
        判斷目前登入會員是否具有賣家或管理員身分。

        Args:
            request: DRF request。
            view: 目前執行中的 DRF view。

        Returns:
            bool: 角色符合時回傳 `True`。
        """
        return auth_demo.is_seller(get_demo_user(request))


class IsAdminDemoUser(BasePermission):
    """
    要求使用者角色必須是平台管理員。

    這個權限適合用在：
    - 後台儀表板
    - 會員管理
    - 商品審核
    - 售後審核
    """

    message = "Admin access is required."

    def has_permission(self, request, view):
        """
        判斷目前登入會員是否為管理員。

        Args:
            request: DRF request。
            view: 目前執行中的 DRF view。

        Returns:
            bool: 為管理員回傳 `True`，否則回傳 `False`。
        """
        return auth_demo.is_admin(get_demo_user(request))

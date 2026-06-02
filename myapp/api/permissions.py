"""DRF 權限檢查與 demo session 取用工具。

這個模組屬於 `myapp.api` 層，建立在 Django REST Framework 的
`rest_framework.permissions` 之上。

主要責任有兩個：
1. 從 request / session 取出目前 demo 登入會員。
2. 提供 APIView 可直接掛載的 permission class，統一限制：
   - 需登入
   - 需賣家或管理者
   - 需管理者

這一層本身不處理帳號資料邏輯，實際的 session 判斷仍委派給
`myapp.services.auth_demo`。
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from ..services import auth_demo


def get_demo_user(request):
    """從 DRF request 對應的 session 取回目前登入會員。

    來源模組：
    - `myapp.services.auth_demo.get_current_user`

    功能：
    - 讓 API view / permission 不必直接理解 session 內部結構
    - 統一回傳目前登入會員的 snapshot dict；未登入則回傳 `None`
    """
    return auth_demo.get_current_user(request.session)


class IsDemoAuthenticated(BasePermission):
    """DRF 權限類別：限制必須已有 demo session。

    來源模組：
    - `rest_framework.permissions.BasePermission`

    功能：
    - 保護需要登入後才能操作的 API
    - 例如會員中心、地址簿、發票、訂單、收藏、購物車結帳
    """

    message = "Please log in first."

    def has_permission(self, request, view):
        """檢查 request 是否已有可辨識的 demo 使用者。"""
        return bool(get_demo_user(request))


class IsSellerOrAdminDemoUser(BasePermission):
    """DRF 權限類別：限制必須為賣家或管理者。

    來源模組：
    - `rest_framework.permissions.BasePermission`
    - `myapp.services.auth_demo.is_seller`

    功能：
    - 保護賣家端 API
    - 同時允許管理者以較高權限檢視或操作賣家資料
    """

    message = "Seller access is required."

    def has_permission(self, request, view):
        """檢查目前登入會員是否具有賣家以上權限。"""
        return auth_demo.is_seller(get_demo_user(request))


class IsAdminDemoUser(BasePermission):
    """DRF 權限類別：限制必須為管理者。

    來源模組：
    - `rest_framework.permissions.BasePermission`
    - `myapp.services.auth_demo.is_admin`

    功能：
    - 保護 staff / admin 路由
    - 例如平台訂單、內容審核、使用者管理、Banner 管理
    """

    message = "Admin access is required."

    def has_permission(self, request, view):
        """檢查目前登入會員是否具有管理者權限。"""
        return auth_demo.is_admin(get_demo_user(request))

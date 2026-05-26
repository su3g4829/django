"""
專案最外層 URL 路由設定。

這個檔案負責把整個站台的入口分流到不同子系統：
- `/api/v1/`：新版 DRF API
- `/`：一般 HTML 頁面與少量舊 alias 路由
- `/admin/`：Django 內建後台
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Canonical versioned DRF API endpoints.
    path("api/v1/", include("myapp.api.urls")),
    # HTML pages plus legacy /api/... aliases defined inside myapp.urls.
    path("", include("myapp.urls")),
    path("admin/", admin.site.urls),
]

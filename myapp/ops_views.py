"""
`myapp.ops_views`
=================

這個模組放的是偏營運與基礎設施的頁面/端點，不處理商業交易流程。

目前提供三類功能：
1. 健康檢查端點：給本機開發、反向代理或部署平台做 liveness / readiness probe。
2. no-DB 基礎設施說明頁：整理目前在「不接資料庫」前提下，專案已補上的上線級設定。
3. 內部檢查 helper：檢查 `data/`、cache 與上傳目錄是否可正常使用。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def health_live(request):
    """
    回傳服務是否存活的 liveness probe。

    這個端點只回答「程式目前有沒有正常跑起來」，不檢查資料目錄或 cache。

    Args:
        request: Django `HttpRequest`，主要用來帶出 middleware 注入的 `request_id`。

    Returns:
        JsonResponse: 基本存活資訊，包含狀態、服務名稱、時間與 request id。
    """
    return JsonResponse(
        {
            "status": "ok",
            "service": "store-demo",
            "time": timezone.now().isoformat(),
            "request_id": getattr(request, "request_id", ""),
        }
    )


def health_ready(request):
    """
    回傳服務是否準備就緒的 readiness probe。

    這個端點會額外檢查：
    - `data/` 與必要 JSON 檔是否存在
    - cache 是否可讀寫
    - 商品上傳目錄是否存在

    Args:
        request: Django `HttpRequest`，主要用來帶出 middleware 注入的 `request_id`。

    Returns:
        JsonResponse: readiness 狀態與各項檢查結果；若有任何檢查失敗會回傳 503。
    """
    checks = {
        "data_dir": _data_dir_check(),
        "cache": _cache_check(),
        "uploads_dir": _uploads_dir_check(),
    }
    is_ready = all(check["ok"] for check in checks.values())
    payload = {
        "status": "ok" if is_ready else "degraded",
        "service": "store-demo",
        "time": timezone.now().isoformat(),
        "request_id": getattr(request, "request_id", ""),
        "checks": checks,
    }
    return JsonResponse(payload, status=200 if is_ready else 503)


def no_db_infrastructure_view(request):
    """
    顯示「不接資料庫也能先做的上線級基礎設施」說明頁。

    這個頁面主要整理目前專案已補上的：
    - 環境變數化設定
    - cache / rate limit
    - session 與安全 cookie
    - health check
    - log / cache 目錄

    Args:
        request: Django `HttpRequest`。

    Returns:
        HttpResponse: `templates/docs/no_db_infrastructure.html` 頁面。
    """
    env_items = [
        {"name": "STORE_ENV", "default": "development", "purpose": "切換目前執行環境名稱。"},
        {"name": "DJANGO_DEBUG", "default": "1 in development", "purpose": "控制是否開啟 Django debug 模式。"},
        {"name": "DJANGO_ALLOWED_HOSTS", "default": "127.0.0.1,localhost,testserver", "purpose": "限制可接受的 Host header。"},
        {"name": "DJANGO_CSRF_TRUSTED_ORIGINS", "default": "", "purpose": "設定反向代理或正式網域的 CSRF 信任來源。"},
        {"name": "STORE_CACHE_BACKEND", "default": "locmem", "purpose": "可改成 filebased；未來也可替換成 Redis。"},
        {"name": "STORE_RATE_LIMIT_ENABLED", "default": "1", "purpose": "是否啟用基於 cache 的寫入限流。"},
        {"name": "STORE_RATE_LIMIT_AUTH_LIMIT", "default": "30", "purpose": "登入 / 註冊等認證操作每分鐘次數上限。"},
        {"name": "STORE_RATE_LIMIT_WRITE_LIMIT", "default": "240", "purpose": "一般 API 寫入操作每分鐘次數上限。"},
        {"name": "SESSION_COOKIE_SECURE", "default": "0 in development", "purpose": "是否只在 HTTPS 下傳送 session cookie。"},
        {"name": "CSRF_COOKIE_SECURE", "default": "0 in development", "purpose": "是否只在 HTTPS 下傳送 CSRF cookie。"},
        {"name": "SECURE_SSL_REDIRECT", "default": "0", "purpose": "是否強制把 HTTP 導向 HTTPS。"},
        {"name": "SECURE_HSTS_SECONDS", "default": "0 in development", "purpose": "是否送出 HSTS header 與其秒數。"},
    ]
    context = {
        "summary": {
            "environment": settings.APP_ENV,
            "debug": settings.DEBUG,
            "cache_backend": settings.CACHES["default"]["BACKEND"],
            "rate_limit_enabled": settings.RATE_LIMIT_ENABLED,
            "session_engine": settings.SESSION_ENGINE,
            "log_dir": str(settings.LOG_DIR),
            "cache_dir": str(settings.CACHE_DIR),
        },
        "env_items": env_items,
        "health_routes": [
            {"path": "/health/live/", "purpose": "存活檢查（liveness probe）"},
            {"path": "/health/ready/", "purpose": "就緒檢查（readiness probe）"},
        ],
    }
    return render(request, "docs/no_db_infrastructure.html", context)


def _data_dir_check() -> dict[str, Any]:
    """
    檢查 `data/` 與必要 JSON 檔是否存在。

    Returns:
        dict[str, Any]: 包含檢查結果、目錄路徑與缺少的檔案名稱。
    """
    data_dir = Path(settings.BASE_DIR) / "data"
    required_files = [
        "products.json",
        "users.json",
        "orders.json",
        "reviews.json",
        "questions.json",
        "posts.json",
        "recommendations.json",
    ]
    missing = [name for name in required_files if not (data_dir / name).exists()]
    return {
        "ok": not missing and data_dir.exists(),
        "path": str(data_dir),
        "missing_files": missing,
    }


def _cache_check() -> dict[str, Any]:
    """
    檢查 Django cache 是否可正常寫入與讀回。

    Returns:
        dict[str, Any]: 包含檢查結果與目前使用的 cache backend。
    """
    key = "healthcheck:ready"
    value = timezone.now().isoformat()
    cache.set(key, value, timeout=10)
    read_back = cache.get(key)
    return {
        "ok": read_back == value,
        "backend": settings.CACHES["default"]["BACKEND"],
    }


def _uploads_dir_check() -> dict[str, Any]:
    """
    檢查商品圖片上傳目錄是否存在。

    若目錄不存在，這裡會順手建立，避免部署後第一次上傳失敗。

    Returns:
        dict[str, Any]: 包含檢查結果與上傳目錄路徑。
    """
    upload_dir = Path(settings.BASE_DIR) / "static" / "uploads" / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return {
        "ok": upload_dir.exists() and upload_dir.is_dir(),
        "path": str(upload_dir),
    }

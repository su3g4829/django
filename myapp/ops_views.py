"""營運健康檢查與基礎設施說明頁。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone


def health_live(request):
    """回傳最輕量的 liveness probe 結果。"""
    return JsonResponse(
        {
            "status": "ok",
            "service": "store-demo",
            "time": timezone.now().isoformat(),
            "request_id": getattr(request, "request_id", ""),
        }
    )


def health_ready(request):
    """檢查目前正式環境仍依賴的基礎設施是否可用。"""
    checks = {
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
    """顯示基礎設施與運行設定頁。

    保留原本 `/docs/no-db-infrastructure/` 路徑，避免舊文件或書籤失效，
    但頁面內容已更新為目前 DB-first 架構下仍適用的營運設定說明。
    """
    env_items = [
        {"name": "STORE_ENV", "default": "development", "purpose": "標示目前執行環境，例如 development 或 production。"},
        {"name": "DJANGO_DEBUG", "default": "1 in development", "purpose": "控制 Django debug 模式，正式環境應關閉。"},
        {
            "name": "DJANGO_ALLOWED_HOSTS",
            "default": "127.0.0.1,localhost,testserver",
            "purpose": "允許的 Host 清單，避免非法 Host header 請求。",
        },
        {
            "name": "DJANGO_CSRF_TRUSTED_ORIGINS",
            "default": "",
            "purpose": "跨來源表單提交時可信任的來源網址清單。",
        },
        {
            "name": "STORE_CACHE_BACKEND",
            "default": "locmem",
            "purpose": "快取後端設定，之後可由 locmem 切換到 Redis。",
        },
        {
            "name": "STORE_RATE_LIMIT_ENABLED",
            "default": "1",
            "purpose": "控制是否啟用 rate limiting。",
        },
        {
            "name": "STORE_RATE_LIMIT_AUTH_LIMIT",
            "default": "30",
            "purpose": "登入、註冊、重設密碼等敏感操作的每分鐘限制。",
        },
        {
            "name": "STORE_RATE_LIMIT_WRITE_LIMIT",
            "default": "240",
            "purpose": "寫入型 API 的每分鐘限制。",
        },
        {
            "name": "SESSION_COOKIE_SECURE",
            "default": "0 in development",
            "purpose": "是否要求 session cookie 只能透過 HTTPS 傳送。",
        },
        {
            "name": "CSRF_COOKIE_SECURE",
            "default": "0 in development",
            "purpose": "是否要求 CSRF cookie 只能透過 HTTPS 傳送。",
        },
        {"name": "SECURE_SSL_REDIRECT", "default": "0", "purpose": "是否將 HTTP 自動轉導到 HTTPS。"},
        {
            "name": "SECURE_HSTS_SECONDS",
            "default": "0 in development",
            "purpose": "正式環境用來啟用 HSTS header。",
        },
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
            {"path": "/health/live/", "purpose": "最輕量的存活檢查。"},
            {"path": "/health/ready/", "purpose": "檢查 cache 與上傳目錄是否可正常使用。"},
        ],
    }
    return render(request, "docs/no_db_infrastructure.html", context)


def _cache_check() -> dict[str, Any]:
    """檢查 Django cache 是否能成功寫入並讀回同一個值。"""
    key = "healthcheck:ready"
    value = timezone.now().isoformat()
    cache.set(key, value, timeout=10)
    read_back = cache.get(key)
    return {
        "ok": read_back == value,
        "backend": settings.CACHES["default"]["BACKEND"],
    }


def _uploads_dir_check() -> dict[str, Any]:
    """確認商品上傳目錄存在，且可由應用程式建立。"""
    upload_dir = Path(settings.BASE_DIR) / "static" / "uploads" / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return {
        "ok": upload_dir.exists() and upload_dir.is_dir(),
        "path": str(upload_dir),
    }

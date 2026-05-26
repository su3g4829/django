"""專案中介層模組。

這個檔案集中放與請求基礎設施相關的 middleware，例如：
- request id 注入
- access log 紀錄
- API / 寫入操作的 rate limit
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse


access_logger = logging.getLogger("store.access")


class RequestContextMiddleware:
    """替每個請求附加 request id，並輸出 access log。

    這個 middleware 不依賴資料庫，適合目前 JSON-backed prototype
    的架構使用。
    """

    def __init__(self, get_response):
        """保存 Django 傳入的下一個 request handler。"""
        self.get_response = get_response

    def __call__(self, request):
        """包裝整個 request/response 生命週期。

        參數:
            request: Django 的 HttpRequest 物件。

        回傳:
            Django HttpResponse 物件，並在 header 中帶上 request id。
        """
        started_at = time.monotonic()
        header_name = getattr(settings, "REQUEST_ID_HEADER", "X-Request-ID")
        incoming_request_id = request.headers.get(header_name, "").strip()
        request.request_id = incoming_request_id or uuid.uuid4().hex

        response = self.get_response(request)
        response[header_name] = request.request_id

        if getattr(settings, "ACCESS_LOG_ENABLED", True):
            duration_ms = int((time.monotonic() - started_at) * 1000)
            access_logger.info(
                "request_id=%s method=%s path=%s status=%s duration_ms=%s ip=%s",
                request.request_id,
                request.method,
                request.path,
                getattr(response, "status_code", "-"),
                duration_ms,
                _client_ip(request),
            )
        return response


class RateLimitMiddleware:
    """針對登入與 API 寫入操作做快取式限流。

    目前使用 Django cache 作為計數桶，不需要額外資料表即可運作。
    """

    AUTH_PREFIXES = (
        "/api/v1/auth/login/",
        "/api/v1/auth/register/",
    )
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, get_response):
        """保存 Django 傳入的下一個 request handler。"""
        self.get_response = get_response

    def __call__(self, request):
        """在進入 view 前檢查是否超過限流門檻。

        參數:
            request: Django 的 HttpRequest 物件。

        回傳:
            若未超限則回傳下游 response；超限時直接回傳 429。
        """
        if not getattr(settings, "RATE_LIMIT_ENABLED", False):
            return self.get_response(request)

        if request.method not in self.WRITE_METHODS:
            return self.get_response(request)

        bucket = self._bucket_for_request(request)
        if not bucket:
            return self.get_response(request)

        allowed, retry_after = self._consume_token(request, bucket)
        if allowed:
            return self.get_response(request)

        detail = f"Too many {bucket} requests. Retry later."
        if request.path.startswith("/api/"):
            response = JsonResponse({"detail": detail, "request_id": getattr(request, "request_id", "")}, status=429)
        else:
            response = HttpResponse(detail, status=429, content_type="text/plain; charset=utf-8")
        response["Retry-After"] = str(retry_after)
        return response

    def _bucket_for_request(self, request) -> Optional[str]:
        """依請求路徑判斷應套用哪一種限流桶。"""
        if request.path.startswith(self.AUTH_PREFIXES):
            return "auth"
        if request.path.startswith("/api/v1/"):
            return "write"
        return None

    def _consume_token(self, request, bucket: str) -> tuple[bool, int]:
        """消耗當前 IP 在指定桶中的一次請求額度。"""
        limit = self._limit_for_bucket(bucket)
        window = int(getattr(settings, "RATE_LIMIT_WINDOW_SECONDS", 60))
        cache_key = f"ratelimit:{bucket}:{_client_ip(request)}"
        if cache.add(cache_key, 1, timeout=window):
            current = 1
        else:
            try:
                current = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, timeout=window)
                current = 1
        return current <= limit, window

    @staticmethod
    def _limit_for_bucket(bucket: str) -> int:
        """依桶類型回傳對應的每分鐘上限。"""
        if bucket == "auth":
            return int(getattr(settings, "RATE_LIMIT_AUTH_LIMIT", 30))
        return int(getattr(settings, "RATE_LIMIT_WRITE_LIMIT", 240))


def _client_ip(request) -> str:
    """從 request 中取出最可信的客戶端 IP。"""
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")

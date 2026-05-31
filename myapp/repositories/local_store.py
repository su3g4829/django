"""本地 JSON 資料存取層。

這個模組集中管理 `data/*.json` 的讀寫，讓 service / API 層不用直接碰檔案。
目前專案仍採用 JSON-backed prototype，因此這裡會額外做：

- 短時間快取，減少重複 I/O
- 統一欄位預設值，讓後續轉移到資料庫更容易
- 寫入後自動清除快取
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from django.conf import settings

_TTL_SECONDS = 5
_cache: Dict[str, dict] = {}
_lock = threading.Lock()


def _data_dir() -> Path:
    """回傳本地 JSON 資料夾位置。"""
    return Path(settings.BASE_DIR) / "data"


def _load_json(name: str) -> Any:
    """讀取指定 JSON 檔案並回傳 Python 物件。"""
    path = _data_dir() / name
    with path.open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def _write_json(name: str, data: Any) -> None:
    """將 Python 物件寫回指定 JSON 檔案。"""
    path = _data_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _cached(key: str, loader):
    """讀取快取；若快取過期則重新載入。"""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit["ts"] < _TTL_SECONDS:
            return hit["val"]

    value = loader()

    with _lock:
        _cache[key] = {"val": value, "ts": now}
    return value


def _invalidate(key: str) -> None:
    """清除單一快取鍵值。"""
    with _lock:
        _cache.pop(key, None)


def clear_cache() -> None:
    """清除所有本地資料快取。"""
    with _lock:
        _cache.clear()


def _default_invoice_profile() -> Dict[str, Any]:
    """提供固定欄位的發票資料預設值。"""
    return {
        "invoice_type": "personal",
        "carrier_code": "",
        "company_name": "",
        "tax_id": "",
        "updated_at": "",
    }


def _default_shipping_rules() -> Dict[str, Any]:
    """Return seller-level shipping defaults for marketplace checkout."""
    return {
        "home_delivery_enabled": True,
        "home_delivery_fee": "80.00",
        "convenience_store_enabled": True,
        "convenience_store_fee": "60.00",
        "free_shipping_threshold": "1200.00",
    }


def _normalize_user_record(user: Dict[str, Any]) -> Dict[str, Any]:
    """統一本地會員資料結構，方便未來移轉到 ORM。"""
    normalized = dict(user)
    username = str(normalized.get("username", "")).strip().lower()
    normalized["username"] = username
    normalized["display_name"] = str(normalized.get("display_name") or username)
    normalized["role"] = str(normalized.get("role") or "member")
    normalized["account_status"] = str(normalized.get("account_status") or "active")
    normalized["seller_request_status"] = str(normalized.get("seller_request_status") or "")
    normalized["email"] = str(normalized.get("email") or "")
    normalized["created_at"] = str(normalized.get("created_at") or "")
    normalized["updated_at"] = str(normalized.get("updated_at") or normalized["created_at"] or "")
    normalized["last_login_at"] = str(normalized.get("last_login_at") or "")
    normalized["seller_requested_at"] = str(normalized.get("seller_requested_at") or "")
    normalized["seller_reviewed_at"] = str(normalized.get("seller_reviewed_at") or "")
    normalized["account_status_updated_at"] = str(normalized.get("account_status_updated_at") or "")
    addresses = normalized.get("addresses")
    normalized["addresses"] = addresses if isinstance(addresses, list) else []
    normalized["default_address_id"] = normalized.get("default_address_id")
    invoice_profile = normalized.get("invoice_profile")
    merged_invoice = _default_invoice_profile()
    if isinstance(invoice_profile, dict):
        merged_invoice.update(invoice_profile)
    normalized["invoice_profile"] = merged_invoice
    shipping_rules = normalized.get("shipping_rules")
    merged_shipping_rules = _default_shipping_rules()
    if isinstance(shipping_rules, dict):
        merged_shipping_rules.update(shipping_rules)
    normalized["shipping_rules"] = merged_shipping_rules
    return normalized


def get_products() -> List[Dict[str, Any]]:
    """讀取全部商品。"""
    return _cached("products", lambda: _load_json("products.json"))


def get_product_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """依商品 slug 取得商品。"""
    for product in get_products():
        if product.get("slug") == slug:
            return product
    return None


def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    """依商品 ID 取得商品。"""
    for product in get_products():
        if product.get("id") == product_id:
            return product
    return None


def save_products(products: List[Dict[str, Any]]) -> None:
    """儲存商品資料。"""
    _write_json("products.json", products)
    _invalidate("products")


def get_reviews() -> List[Dict[str, Any]]:
    """讀取全部評論。"""
    try:
        return _cached("reviews", lambda: _load_json("reviews.json"))
    except FileNotFoundError:
        return []


def get_reviews_by_product_id(product_id: int) -> List[Dict[str, Any]]:
    """依商品 ID 取得評論列表。"""
    reviews = [review for review in get_reviews() if review.get("product_id") == product_id]
    return sorted(reviews, key=lambda item: item.get("created_at", ""), reverse=True)


def save_reviews(reviews: List[Dict[str, Any]]) -> None:
    """儲存評論資料。"""
    _write_json("reviews.json", reviews)
    _invalidate("reviews")


def get_recommendations() -> List[Dict[str, Any]]:
    """讀取推薦設定。"""
    try:
        return _cached("recommendations", lambda: _load_json("recommendations.json"))
    except FileNotFoundError:
        return []


def get_recommendation_config(product_id: int) -> Optional[Dict[str, Any]]:
    """依商品 ID 取得推薦設定。"""
    for item in get_recommendations():
        if item.get("product_id") == product_id:
            return item
    return None


def get_questions() -> List[Dict[str, Any]]:
    """讀取全部商品問答。"""
    try:
        return _cached("questions", lambda: _load_json("questions.json"))
    except FileNotFoundError:
        return []


def get_questions_by_product_id(product_id: int) -> List[Dict[str, Any]]:
    """依商品 ID 取得問答列表。"""
    questions = [item for item in get_questions() if item.get("product_id") == product_id]
    return sorted(questions, key=lambda item: item.get("created_at", ""), reverse=True)


def save_questions(questions: List[Dict[str, Any]]) -> None:
    """儲存商品問答資料。"""
    _write_json("questions.json", questions)
    _invalidate("questions")


def get_competitor_prices() -> List[Dict[str, Any]]:
    """讀取模擬比價資料。

    這份資料用來示範「外站價格抓取 / 爬蟲結果」的後續呈現流程，
    目前來源不是即時爬蟲，而是本地 JSON 假資料。
    """
    try:
        return _cached("competitor_prices", lambda: _load_json("competitor_prices.json"))
    except FileNotFoundError:
        return []


def save_competitor_prices(items: List[Dict[str, Any]]) -> None:
    """儲存模擬比價資料並清除快取。"""
    _write_json("competitor_prices.json", items)
    _invalidate("competitor_prices")

def get_newebpay_payment_logs() -> List[Dict[str, Any]]:
    """讀取藍新支付 mock 測試紀錄。

    目前專案尚未導入正式資料庫，先以本地 JSON 保存支付交易建立、
    callback 回傳與狀態變更，方便先完成 API 串接與測試架構。
    """
    try:
        return _cached("newebpay_payment_logs", lambda: _load_json("newebpay_payment_logs.json"))
    except FileNotFoundError:
        return []


def save_newebpay_payment_logs(items: List[Dict[str, Any]]) -> None:
    """寫回藍新支付 mock 測試紀錄。"""
    _write_json("newebpay_payment_logs.json", items)
    _invalidate("newebpay_payment_logs")


def get_newebpay_logistics_logs() -> List[Dict[str, Any]]:
    """讀取藍新物流 mock 測試紀錄。"""
    try:
        return _cached("newebpay_logistics_logs", lambda: _load_json("newebpay_logistics_logs.json"))
    except FileNotFoundError:
        return []


def save_newebpay_logistics_logs(items: List[Dict[str, Any]]) -> None:
    """寫回藍新物流 mock 測試紀錄。"""
    _write_json("newebpay_logistics_logs.json", items)
    _invalidate("newebpay_logistics_logs")


def get_newebpay_store_map_selections() -> List[Dict[str, Any]]:
    """Return persisted NewebPay convenience-store map selections."""
    try:
        return _cached("newebpay_store_map_selections", lambda: _load_json("newebpay_store_map_selections.json"))
    except FileNotFoundError:
        return []


def save_newebpay_store_map_selections(items: List[Dict[str, Any]]) -> None:
    """Persist NewebPay convenience-store map selections."""
    _write_json("newebpay_store_map_selections.json", items)
    _invalidate("newebpay_store_map_selections")


def get_posts() -> List[Dict[str, Any]]:
    """讀取論壇文章。"""
    try:
        return _cached("posts", lambda: _load_json("posts.json"))
    except FileNotFoundError:
        return []


def get_post_by_id(post_id: int) -> Optional[Dict[str, Any]]:
    """依文章 ID 取得論壇文章。"""
    for post in get_posts():
        if post.get("id") == post_id:
            return post
    return None


def save_posts(posts: List[Dict[str, Any]]) -> None:
    """儲存論壇文章資料。"""
    _write_json("posts.json", posts)
    _invalidate("posts")


def get_banners() -> List[Dict[str, Any]]:
    """讀取首頁 banner 設定。"""
    try:
        return _cached("banners", lambda: _load_json("banners.json"))
    except FileNotFoundError:
        return []


def save_banners(banners: List[Dict[str, Any]]) -> None:
    """儲存首頁 banner 設定。"""
    _write_json("banners.json", banners)
    _invalidate("banners")


def get_users() -> List[Dict[str, Any]]:
    """讀取會員資料，並補齊後續轉資料庫需要的欄位。"""
    try:
        return _cached("users", lambda: [_normalize_user_record(item) for item in _load_json("users.json")])
    except FileNotFoundError:
        return []


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """依 username 取得會員資料。"""
    clean_username = username.strip().lower()
    for user in get_users():
        if user.get("username") == clean_username:
            return user
    return None


def save_users(users: List[Dict[str, Any]]) -> None:
    """儲存會員資料，寫入前先做欄位正規化。"""
    normalized = [_normalize_user_record(item) for item in users]
    _write_json("users.json", normalized)
    _invalidate("users")


def get_orders() -> List[Dict[str, Any]]:
    """讀取全部訂單。"""
    try:
        return _cached("orders", lambda: _load_json("orders.json"))
    except FileNotFoundError:
        return []


def get_order_by_id(order_id: int) -> Optional[Dict[str, Any]]:
    """依訂單 ID 取得訂單。"""
    for order in get_orders():
        if order.get("id") == order_id:
            return order
    return None


def get_orders_by_username(username: str) -> List[Dict[str, Any]]:
    """依買家 username 取得訂單列表。"""
    orders = [order for order in get_orders() if order.get("username") == username]
    return sorted(orders, key=lambda item: item.get("created_at", ""), reverse=True)


def save_orders(orders: List[Dict[str, Any]]) -> None:
    """儲存訂單資料。"""
    _write_json("orders.json", orders)
    _invalidate("orders")

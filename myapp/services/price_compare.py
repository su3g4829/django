"""模擬比價 / 模擬爬蟲結果服務。

這個模組的目的不是做真正的外站爬蟲，而是先把「比價功能」需要的
資料流、API、前端呈現方式定義好。

目前資料來源：
- `data/competitor_prices.json`

未來若要接正式來源，可把這個模組內部替換成：
- 官方 API
- 合作 feed
- 真正的 crawler pipeline

對外介面盡量維持不變，這樣前端與 DRF API 不需要重寫。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from django.utils import timezone

from ..repositories import local_store

DEFAULT_COMPETITOR_SITES = [
    {
        "site": "momo",
        "site_label": "momo 購物網",
        "currency": "TWD",
        "status": "matched",
        "note": "模擬資料：示範比價來源。",
        "price_multiplier": Decimal("0.96"),
    },
    {
        "site": "pchome",
        "site_label": "PChome 24h",
        "currency": "TWD",
        "status": "matched",
        "note": "模擬資料：示範比價來源。",
        "price_multiplier": Decimal("1.05"),
    },
]


def _format_datetime(value: str) -> str:
    """將 ISO 時間字串轉成較適合前端顯示的格式。"""
    try:
        parsed = timezone.datetime.fromisoformat(value)
    except ValueError:
        return value
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M")


def _to_decimal(value: Any) -> Decimal:
    """將輸入值轉為兩位小數 Decimal。"""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _build_default_entry(product: Dict[str, Any]) -> Dict[str, Any]:
    """為尚未配置比價資料的商品建立一份預設 mock 紀錄。"""
    now = timezone.now().isoformat()
    base_price = _to_decimal(product["price"])
    competitors = []
    for site in DEFAULT_COMPETITOR_SITES:
        competitor_price = (base_price * site["price_multiplier"]).quantize(Decimal("0.01"))
        competitors.append(
            {
                "site": site["site"],
                "site_label": site["site_label"],
                "title": f"{product['name']} - {site['site_label']} 模擬結果",
                "url": f"https://example.com/{site['site']}/{product['slug']}",
                "price": float(competitor_price),
                "currency": site["currency"],
                "captured_at": now,
                "status": site["status"],
                "note": site["note"],
                "mock_rank": len(competitors) + 1,
            }
        )
    return {
        "our_product_slug": product["slug"],
        "our_product_name": product["name"],
        "our_product_id": product["id"],
        "competitors": competitors,
        "last_refreshed_at": now,
        "source_type": "mock",
    }


def _ensure_entry(product: Dict[str, Any]) -> Dict[str, Any]:
    """確保指定商品一定有一筆模擬比價資料。"""
    items = local_store.get_competitor_prices()
    for item in items:
        if item.get("our_product_slug") == product["slug"]:
            return item

    new_item = _build_default_entry(product)
    local_store.save_competitor_prices(items + [new_item])
    return new_item


def _serialize_entry(product: Dict[str, Any], raw_entry: Dict[str, Any]) -> Dict[str, Any]:
    """把原始 mock 資料整理成前端可直接顯示的 payload。"""
    our_price = _to_decimal(product["price"])
    items: List[Dict[str, Any]] = []

    for competitor in raw_entry.get("competitors", []):
        competitor_price = _to_decimal(competitor["price"])
        diff_amount = (competitor_price - our_price).quantize(Decimal("0.01"))
        diff_percent = Decimal("0.00")
        if our_price > 0:
            diff_percent = ((diff_amount / our_price) * Decimal("100")).quantize(Decimal("0.01"))

        items.append(
            {
                "site": competitor.get("site", ""),
                "site_label": competitor.get("site_label") or competitor.get("site", ""),
                "title": competitor.get("title", ""),
                "url": competitor.get("url", ""),
                "price": float(competitor_price),
                "currency": competitor.get("currency", "TWD"),
                "captured_at": competitor.get("captured_at", ""),
                "captured_at_display": _format_datetime(competitor.get("captured_at", "")),
                "status": competitor.get("status", "matched"),
                "note": competitor.get("note", ""),
                "diff_amount": float(diff_amount),
                "diff_percent": float(diff_percent),
                "is_cheaper_than_our_price": competitor_price < our_price,
                "is_same_as_our_price": competitor_price == our_price,
            }
        )

    lowest_price = min([_to_decimal(item["price"]) for item in items] + [our_price])
    return {
        "our_product_slug": product["slug"],
        "our_product_name": product["name"],
        "our_product_id": product["id"],
        "our_price": float(our_price),
        "currency": "TWD",
        "is_mock": True,
        "source_type": raw_entry.get("source_type", "mock"),
        "last_refreshed_at": raw_entry.get("last_refreshed_at", ""),
        "last_refreshed_at_display": _format_datetime(raw_entry.get("last_refreshed_at", "")),
        "lowest_price": float(lowest_price),
        "our_store_is_lowest": our_price <= lowest_price,
        "items": items,
    }


def get_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    """取得單一商品的模擬比價結果。"""
    entry = _ensure_entry(product)
    return _serialize_entry(product, entry)


def refresh_mock_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    """模擬重新抓價。

    這個動作會：
    - 更新抓取時間
    - 依來源站點做微小價格浮動

    目的不是模擬真實市場，而是讓前端可以演示：
    - 手動刷新
    - 更新時間改變
    - 比價結果重新計算
    """
    items = local_store.get_competitor_prices()
    target = None
    for item in items:
        if item.get("our_product_slug") == product["slug"]:
            target = item
            break

    if target is None:
        target = _build_default_entry(product)
        items.append(target)

    now = timezone.now().isoformat()
    our_price = _to_decimal(product["price"])
    for index, competitor in enumerate(target.get("competitors", []), start=1):
        current_price = _to_decimal(competitor.get("price", product["price"]))
        # 這裡做極小幅 mock 浮動，方便示範「重新抓價」效果。
        step = Decimal("0.50") * Decimal(index)
        next_price = current_price + step if current_price <= our_price else current_price - step
        if next_price <= 0:
            next_price = current_price
        competitor["price"] = float(next_price.quantize(Decimal("0.01")))
        competitor["captured_at"] = now

    target["last_refreshed_at"] = now
    local_store.save_competitor_prices(items)
    return _serialize_entry(product, target)

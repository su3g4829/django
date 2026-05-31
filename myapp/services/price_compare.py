from __future__ import annotations

import re
from decimal import Decimal
from html.parser import HTMLParser
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.utils import timezone


SUPPORTED_PRODUCTS: dict[str, dict[str, str]] = {
    "new-forcepolo": {
        "momo_url": (
            "https://www.momoshop.com.tw/goods/GoodsDetail.jsp"
            "?i_code=15219838&Area=search&mdiv=403&oid=1_1"
            "&cid=index&kw=%E4%B8%8A%E8%A1%A3"
        ),
        "pchome_url": "https://24h.pchome.com.tw/prod/DIAIYD-A900K04WD",
    }
}


class ProductPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.meta: Dict[str, str] = {}
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "title":
            self._in_title = True
            return
        if tag == "meta":
            key = attr_map.get("property") or attr_map.get("name")
            value = attr_map.get("content")
            if key and value:
                self.meta[key] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def supports_price_comparison(product: Dict[str, Any] | str) -> bool:
    slug = product if isinstance(product, str) else str(product.get("slug", ""))
    return slug in SUPPORTED_PRODUCTS


def _require_supported_product(product: Dict[str, Any]) -> dict[str, str]:
    slug = str(product.get("slug", ""))
    config = SUPPORTED_PRODUCTS.get(slug)
    if not config:
        raise ValueError("Price comparison is not enabled for this product.")
    return config


def _clean_price(value: str) -> str:
    return value.replace(",", "").replace("$", "").strip()


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _format_datetime(value: str) -> str:
    try:
        parsed = timezone.datetime.fromisoformat(value)
    except ValueError:
        return value
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return timezone.localtime(parsed).strftime("%Y-%m-%d %H:%M")


def _fetch_html(url: str) -> str:
    hostname = (urlparse(url).hostname or "").lower()
    referer = "https://www.momoshop.com.tw/" if "momoshop.com.tw" in hostname else "https://24h.pchome.com.tw/"
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Referer": referer,
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _parse_meta(html: str) -> ProductPageParser:
    parser = ProductPageParser()
    parser.feed(html)
    return parser


def _first_match(pattern: str, text: str, flags: int = 0) -> str:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else ""


def _extract_momo(html: str, url: str) -> Dict[str, Any]:
    parser = _parse_meta(html)
    title = (parser.meta.get("og:title") or parser.title or "").split("-momo")[0].strip()
    sale_price = _clean_price(parser.meta.get("product:price:amount", ""))
    if not sale_price:
        sale_price = _clean_price(_first_match(r"salePrice\s*=\s*'([0-9,]+)'", html, re.I))
    original_price = _clean_price(
        _first_match(r"<li class='' priceTitle='[^']*' price='([0-9,]+)'>", html, re.I)
    )
    return {
        "site": "momo",
        "site_label": "momo",
        "title": title,
        "url": url,
        "original_price": original_price,
        "sale_price": sale_price,
        "currency": "TWD",
        "note": "Fetched from fixed momo product URL.",
    }


def _extract_pchome(html: str, url: str) -> Dict[str, Any]:
    parser = _parse_meta(html)
    title = (parser.meta.get("og:title") or parser.title or "").replace(" - PChome 24h購物", "").strip()
    sale_price = _clean_price(_first_match(r'o-prodPrice__price[^>]*>\$([0-9,]+)</div>', html, re.I))
    original_price = _clean_price(_first_match(r'o-prodPrice__originalPrice[^>]*>\$([0-9,]+)</div>', html, re.I))
    return {
        "site": "pchome",
        "site_label": "PChome 24h",
        "title": title,
        "url": url,
        "original_price": original_price,
        "sale_price": sale_price,
        "currency": "TWD",
        "note": "Fetched from fixed PChome 24h product URL.",
    }


def _safe_scrape(site: str, url: str) -> Dict[str, Any]:
    now = timezone.now().isoformat()
    try:
        html = _fetch_html(url)
        raw = _extract_momo(html, url) if site == "momo" else _extract_pchome(html, url)
        raw["status"] = "matched"
        raw["captured_at"] = now
        return raw
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        return {
            "site": site,
            "site_label": "momo" if site == "momo" else "PChome 24h",
            "title": "",
            "url": url,
            "original_price": "",
            "sale_price": "",
            "currency": "TWD",
            "status": "failed",
            "captured_at": now,
            "note": f"Fetch failed: {exc}",
        }


def _build_competitors(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = _require_supported_product(product)
    return [
        _safe_scrape("momo", config["momo_url"]),
        _safe_scrape("pchome", config["pchome_url"]),
    ]


def _serialize_item(our_price: Decimal, competitor: Dict[str, Any]) -> Dict[str, Any]:
    sale_price_text = competitor.get("sale_price", "")
    original_price_text = competitor.get("original_price", "")
    sale_price = _to_decimal(sale_price_text) if sale_price_text else Decimal("0.00")
    diff_amount = (sale_price - our_price).quantize(Decimal("0.01")) if sale_price_text else Decimal("0.00")
    diff_percent = Decimal("0.00")
    if sale_price_text and our_price > 0:
        diff_percent = ((diff_amount / our_price) * Decimal("100")).quantize(Decimal("0.01"))
    return {
        "site": competitor.get("site", ""),
        "site_label": competitor.get("site_label", ""),
        "title": competitor.get("title", ""),
        "url": competitor.get("url", ""),
        "price": float(sale_price) if sale_price_text else 0.0,
        "original_price": float(_to_decimal(original_price_text)) if original_price_text else None,
        "sale_price": float(sale_price) if sale_price_text else None,
        "currency": competitor.get("currency", "TWD"),
        "captured_at": competitor.get("captured_at", ""),
        "captured_at_display": _format_datetime(competitor.get("captured_at", "")),
        "status": competitor.get("status", "matched"),
        "note": competitor.get("note", ""),
        "diff_amount": float(diff_amount),
        "diff_percent": float(diff_percent),
        "is_cheaper_than_our_price": bool(sale_price_text and sale_price < our_price),
        "is_same_as_our_price": bool(sale_price_text and sale_price == our_price),
    }


def _serialize_payload(product: Dict[str, Any], competitors: List[Dict[str, Any]]) -> Dict[str, Any]:
    our_price = _to_decimal(product["price"])
    items = [_serialize_item(our_price, competitor) for competitor in competitors]
    valid_prices = [Decimal(str(item["sale_price"])) for item in items if item.get("sale_price") is not None]
    lowest_price = min(valid_prices + [our_price]) if valid_prices else our_price
    last_refreshed_at = max((competitor.get("captured_at", "") for competitor in competitors), default="")
    return {
        "our_product_slug": product["slug"],
        "our_product_name": product["name"],
        "our_product_id": product["id"],
        "our_price": float(our_price),
        "currency": "TWD",
        "is_mock": False,
        "source_type": "fixed_live_urls",
        "last_refreshed_at": last_refreshed_at,
        "last_refreshed_at_display": _format_datetime(last_refreshed_at) if last_refreshed_at else "",
        "lowest_price": float(lowest_price),
        "our_store_is_lowest": our_price <= lowest_price,
        "items": items,
    }


def get_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    return _serialize_payload(product, _build_competitors(product))


def refresh_mock_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    return _serialize_payload(product, _build_competitors(product))


def scrape_test_competitors(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    return _build_competitors(product)

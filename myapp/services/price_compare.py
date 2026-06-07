"""Live product price comparison via site search results."""

from __future__ import annotations

import html
import json
import re
from decimal import Decimal
from hashlib import sha1
from time import sleep
from typing import Any, Callable, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from django.core.cache import cache
from django.utils import timezone


SearchResult = Dict[str, Any]
CACHE_TTL_SECONDS = 600
STALE_CACHE_TTL_SECONDS = 3600

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def supports_price_comparison(product: Dict[str, Any] | str) -> bool:
    """Return whether price comparison is enabled for a product."""
    if isinstance(product, str):
        return False
    return bool(product.get("price_compare_enabled", False))


def _require_supported_product(product: Dict[str, Any]) -> str:
    """Return the query keyword when price comparison is enabled."""
    if not supports_price_comparison(product):
        raise ValueError("Price comparison is not enabled for this product.")
    query = str(product.get("price_compare_query") or product.get("name") or "").strip()
    if not query:
        raise ValueError("Price comparison query is missing for this product.")
    return query


def _clean_price(value: str) -> str:
    return value.replace(",", "").replace("$", "").strip()


def _clean_query_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


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


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", html.unescape(str(value)).lower())


def _decode_json_text(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    try:
        return str(json.loads(f'"{raw}"'))
    except json.JSONDecodeError:
        return html.unescape(raw.replace("\\/", "/"))


def _query_terms(query: str) -> List[str]:
    terms = [_normalize_match_text(part) for part in re.findall(r"[0-9A-Za-z\u4e00-\u9fff]+", query)]
    return [term for term in terms if term]


def _build_query_candidates(product: Dict[str, Any]) -> List[str]:
    configured_query = _clean_query_text(product.get("price_compare_query") or "")
    product_name = _clean_query_text(product.get("name") or "")
    headline = re.sub(r"[（(].*?[)）]", "", product_name).strip()
    core_headline = re.split(r"\s*[-－]\s*", headline, maxsplit=1)[0].strip()
    candidates = [core_headline, headline, configured_query, product_name]
    if configured_query:
        configured_score = len(_normalize_match_text(configured_query))
        core_score = len(_normalize_match_text(core_headline))
        if configured_score >= core_score and configured_query not in {core_headline, headline, product_name}:
            candidates = [configured_query, core_headline, headline, product_name]
    deduped: List[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = _clean_query_text(candidate)
        if not cleaned:
            continue
        normalized = _normalize_match_text(cleaned)
        if not normalized or normalized in seen:
            continue
        deduped.append(cleaned)
        seen.add(normalized)
    return deduped


def _title_match_score(title: str, query: str) -> tuple[int, int]:
    normalized_title = _normalize_match_text(title)
    normalized_query = _normalize_match_text(query)
    if not normalized_title or not normalized_query:
        return (0, 0)
    if normalized_query in normalized_title:
        return (10_000, len(normalized_query))
    terms = _query_terms(query)
    if not terms:
        return (0, 0)
    matched_terms = [term for term in terms if term in normalized_title]
    if not matched_terms:
        return (0, 0)
    return (len(matched_terms), sum(len(term) for term in matched_terms))


def _fetch_html(url: str, *, referer: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer,
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, *, referer: str) -> Dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Referer": referer,
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8", errors="replace")
    return json.loads(payload)


def _cache_key(site: str, query: str) -> str:
    digest = sha1(query.encode("utf-8")).hexdigest()
    return f"price-compare:{site}:{digest}"


def _load_cached_result(site: str, query: str) -> SearchResult | None:
    cached = cache.get(_cache_key(site, query))
    return dict(cached) if isinstance(cached, dict) else None


def _store_cached_result(site: str, query: str, result: SearchResult) -> None:
    cache.set(_cache_key(site, query), dict(result), timeout=STALE_CACHE_TTL_SECONDS)


def _pick_cheapest_result(candidates: List[SearchResult], query: str) -> SearchResult:
    matched = [
        item
        for item in candidates
        if item.get("sale_price") not in (None, "")
    ]
    if not matched:
        raise ValueError("No matching results found.")
    scored: List[tuple[tuple[int, int], SearchResult]] = []
    for item in matched:
        score = _title_match_score(str(item.get("title") or ""), query)
        if score <= (0, 0):
            continue
        scored.append((score, item))
    if not scored:
        raise ValueError("No matching results found.")
    best_score = max(score for score, _ in scored)
    best_items = [item for score, item in scored if score == best_score]
    best_items.sort(key=lambda item: _to_decimal(item["sale_price"]))
    return best_items[0]


def _search_momo(query: str) -> SearchResult:
    search_url = f"https://m.momoshop.com.tw/search.momo?searchKeyword={quote_plus(query)}"
    html_text = _fetch_html(search_url, referer="https://m.momoshop.com.tw/")
    anchor = html_text.find('goodsInfoList\\":[')
    if anchor >= 0:
        html_text = html_text[anchor : anchor + 160000]
    pattern = re.compile(
        r'\\"goodsCode\\":\\"(?P<code>[^"]+)\\"'
        r'.{0,600}?\\"goodsName\\":\\"(?P<name>.*?)\\"'
        r'.{0,600}?\\"goodsPrice\\":\\"\$\$(?P<price>[0-9,]+)\\"'
        r'(?:.{0,400}?\\"goodsPriceOri\\":\\"\$\$(?P<original>[0-9,]+))?',
        re.S,
    )
    candidates: List[SearchResult] = []
    for match in pattern.finditer(html_text):
        code = str(match.group("code") or "").strip()
        title = _decode_json_text(match.group("name") or "").strip()
        price = _clean_price(match.group("price") or "")
        original_price = _clean_price(match.group("original") or "")
        if not code or not title or not price:
            continue
        candidates.append(
            {
                "site": "momo",
                "site_label": "momo",
                "title": title,
                "url": f"https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code={code}",
                "original_price": original_price,
                "sale_price": price,
                "currency": "TWD",
                "note": f'Keyword search: "{query}"',
            }
        )
    return _pick_cheapest_result(candidates, query)


def _search_pchome(query: str) -> SearchResult:
    search_url = (
        "https://ecshweb.pchome.com.tw/search/v4.3/all/results"
        f"?q={quote_plus(query)}&page=1&sort=rnk/dc"
    )
    payload = _fetch_json(search_url, referer="https://24h.pchome.com.tw/")
    products = payload.get("Prods") or payload.get("prods") or []
    candidates: List[SearchResult] = []
    for product in products:
        product_id = str(product.get("Id") or product.get("id") or "").strip()
        title = _clean_query_text(product.get("Name") or product.get("name") or "")
        price = _clean_price(str(product.get("Price") or product.get("price") or ""))
        original_price = _clean_price(
            str(
                product.get("OriginPrice")
                or product.get("originPrice")
                or product.get("MPrice")
                or product.get("mprice")
                or ""
            )
        )
        if not title or not price or not product_id:
            continue
        candidates.append(
            {
                "site": "pchome",
                "site_label": "PChome 24h",
                "title": title,
                "url": f"https://24h.pchome.com.tw/prod/{product_id}",
                "original_price": original_price,
                "sale_price": price,
                "currency": "TWD",
                "note": f'Keyword search: "{query}"',
            }
        )
    return _pick_cheapest_result(candidates, query)


def _safe_search(site: str, query: str, fetcher: Callable[[str], SearchResult], *, force: bool = False) -> SearchResult:
    now = timezone.now().isoformat()
    cached = None if force else _load_cached_result(site, query)
    if cached:
        cached["captured_at"] = str(cached.get("captured_at") or now)
        cached["status"] = "matched"
        cached["note"] = str(cached.get("note") or "")
        return cached
    try:
        result = dict(fetcher(query))
        result["status"] = "matched"
        result["captured_at"] = now
        _store_cached_result(site, query, result)
        return result
    except HTTPError as exc:
        if exc.code == 429:
            sleep(1)
            try:
                result = dict(fetcher(query))
                result["status"] = "matched"
                result["captured_at"] = now
                result["note"] = f'{result.get("note", "")} (retried after 429)'.strip()
                _store_cached_result(site, query, result)
                return result
            except (HTTPError, URLError, TimeoutError, ValueError):
                cached = _load_cached_result(site, query)
                if cached:
                    cached["status"] = "matched"
                    cached["note"] = f'{cached.get("note", "")} | Using cached result because live fetch hit 429.'.strip(" |")
                    return cached
        return {
            "site": site,
            "site_label": "momo" if site == "momo" else "PChome 24h",
            "title": "",
            "url": "",
            "original_price": "",
            "sale_price": "",
            "currency": "TWD",
            "status": "failed",
            "captured_at": now,
            "note": str(exc),
        }
    except (URLError, TimeoutError, ValueError) as exc:
        cached = _load_cached_result(site, query)
        if cached:
            cached["status"] = "matched"
            cached["note"] = f'{cached.get("note", "")} | Using cached result because live fetch failed.'.strip(" |")
            return cached
        return {
            "site": site,
            "site_label": "momo" if site == "momo" else "PChome 24h",
            "title": "",
            "url": "",
            "original_price": "",
            "sale_price": "",
            "currency": "TWD",
            "status": "failed",
            "captured_at": now,
            "note": str(exc),
        }


def _search_with_candidates(
    site: str,
    queries: List[str],
    fetcher: Callable[[str], SearchResult],
    *,
    force: bool = False,
) -> SearchResult:
    failures: List[SearchResult] = []
    for query in queries:
        result = _safe_search(site, query, fetcher, force=force)
        if result.get("status") == "matched" and result.get("sale_price"):
            base_note = str(result.get("note") or "").strip()
            query_note = f'Search query: "{query}"'
            if query_note not in base_note:
                result["note"] = f"{base_note} | {query_note}".strip(" |")
            return result
        failures.append(result)
    if failures:
        return failures[0]
    return {
        "site": site,
        "site_label": "momo" if site == "momo" else "PChome 24h",
        "title": "",
        "url": "",
        "original_price": "",
        "sale_price": "",
        "currency": "TWD",
        "status": "failed",
        "captured_at": timezone.now().isoformat(),
        "note": "No query candidates were available.",
    }


def _build_competitors(product: Dict[str, Any], *, force: bool = False) -> List[SearchResult]:
    _require_supported_product(product)
    queries = _build_query_candidates(product)
    return [
        _search_with_candidates("momo", queries, _search_momo, force=force),
        _search_with_candidates("pchome", queries, _search_pchome, force=force),
    ]


def _serialize_item(our_price: Decimal, competitor: SearchResult) -> Dict[str, Any]:
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


def _serialize_payload(product: Dict[str, Any], competitors: List[SearchResult]) -> Dict[str, Any]:
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
        "query": _require_supported_product(product),
        "is_mock": False,
        "source_type": "live_search",
        "last_refreshed_at": last_refreshed_at,
        "last_refreshed_at_display": _format_datetime(last_refreshed_at) if last_refreshed_at else "",
        "lowest_price": float(lowest_price),
        "our_store_is_lowest": our_price <= lowest_price,
        "items": items,
    }


def get_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    return _serialize_payload(product, _build_competitors(product))


def refresh_mock_price_comparison(product: Dict[str, Any]) -> Dict[str, Any]:
    return _serialize_payload(product, _build_competitors(product, force=True))


def scrape_test_competitors(product: Dict[str, Any]) -> List[SearchResult]:
    return _build_competitors(product)

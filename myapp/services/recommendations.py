"""商品推薦服務模組。

根據推薦設定、分類與標籤關聯，提供商品詳情頁可用的推薦清單。
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..repositories import local_store
from . import product_management


def _collect_products(product_ids: List[int], exclude_product_id: int, limit: int) -> List[Dict[str, Any]]:
    """依條件收集 商品推薦 流程需要的資料集合。

    參數:
        product_ids: 推薦設定中的商品編號集合。
        exclude_product_id: 推薦時需要排除的商品編號。
        limit: 最多回傳幾筆資料。

    回傳:
        依函式用途回傳對應資料。
    """
    seen = set()
    results: List[Dict[str, Any]] = []

    for product_id in product_ids:
        if product_id == exclude_product_id or product_id in seen:
            continue
        product = local_store.get_product_by_id(product_id)
        if not product or not product_management.is_public_product(product):
            continue
        seen.add(product_id)
        results.append(product)
        if len(results) >= limit:
            break
    return results


def _same_category_products(product: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """處理 商品推薦 相關流程。

    參數:
        product: 單一商品資料字典。
        limit: 最多回傳幾筆資料。

    回傳:
        依函式用途回傳對應資料。
    """
    category_slug = product_management._product_category_slug(product)
    if not category_slug:
        return []
    matches = []
    for candidate in local_store.get_products():
        if candidate.get("id") == product.get("id"):
            continue
        if not product_management.is_public_product(candidate):
            continue
        if product_management._product_category_slug(candidate) == category_slug:
            matches.append(candidate)
        if len(matches) >= limit:
            break
    return matches


def _shared_tag_products(product: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    """處理 商品推薦 相關流程。

    參數:
        product: 單一商品資料字典。
        limit: 最多回傳幾筆資料。

    回傳:
        依函式用途回傳對應資料。
    """
    tags = set(product.get("tags", []))
    if not tags:
        return []
    matches = []
    for candidate in local_store.get_products():
        if candidate.get("id") == product.get("id"):
            continue
        if not product_management.is_public_product(candidate):
            continue
        candidate_tags = set(candidate.get("tags", []))
        if tags & candidate_tags:
            matches.append(candidate)
        if len(matches) >= limit:
            break
    return matches


def get_product_recommendations(product: Dict[str, Any], limit: int = 4) -> Dict[str, List[Dict[str, Any]]]:
    """依商品內容與推薦設定回傳推薦商品集合。

    參數:
        product: 單一商品資料字典。
        limit: 最多回傳幾筆資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    config = local_store.get_recommendation_config(product["id"]) or {}

    similar = _collect_products(config.get("similar_ids", []), product["id"], limit)
    if len(similar) < limit:
        for fallback_group in (_same_category_products(product, limit), _shared_tag_products(product, limit)):
            for candidate in fallback_group:
                if candidate["id"] == product["id"]:
                    continue
                if any(existing["id"] == candidate["id"] for existing in similar):
                    continue
                similar.append(candidate)
                if len(similar) >= limit:
                    break
            if len(similar) >= limit:
                break

    also_bought = _collect_products(config.get("also_bought_ids", []), product["id"], 3)

    return {
        "similar": similar[:limit],
        "also_bought": also_bought,
    }

"""商品推薦 service。

優先讀取 ORM 的 `product_recommendations` 關聯資料；若資料不足，
再退回用同分類與共享標籤做簡單 fallback，最後統一回傳：
`{"similar": [...], "also_bought": [...]}`
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import Product as ProductModel
from ..models import ProductRecommendation as ProductRecommendationModel
from . import product_management


def _db_recommendations_enabled() -> bool:
    # 推薦資料表存在且可查詢時，商品頁就能走 ORM 推薦而不是純 fallback 規則。
    try:
        ProductRecommendationModel.objects.count()
        ProductModel.objects.count()
        return True
    except Exception:
        return False


def _fetch_product_by_id(product_id: int) -> Dict[str, Any] | None:
    # 某些推薦流程只拿得到 product_id，這裡補成前端既有的商品 dict 結構。
    if _db_recommendations_enabled():
        product = ProductModel.objects.filter(id=product_id).first()
        if product:
            record = product_management._product_record_from_model(product)
            if product_management.is_public_product(record):
                return product_management.prepare_product_for_display(record)
    return None


def _same_category_products(product: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    # 當 ORM 沒有足夠推薦資料時，先用同分類商品補齊「相似商品」區塊。
    category_slug = product_management._product_category_slug(product)
    if not category_slug:
        return []
    matches = []
    for candidate in product_management.list_public_products():
        if candidate.get("id") == product.get("id"):
            continue
        if product_management._product_category_slug(candidate) == category_slug:
            matches.append(candidate)
        if len(matches) >= limit:
            break
    return matches


def _shared_tag_products(product: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    # 第二層 fallback 用共享標籤擴充候選，避免同分類不足時整塊推薦變空白。
    tags = set(product.get("tags", []))
    if not tags:
        return []
    matches = []
    for candidate in product_management.list_public_products():
        if candidate.get("id") == product.get("id"):
            continue
        candidate_tags = set(candidate.get("tags", []))
        if tags & candidate_tags:
            matches.append(candidate)
        if len(matches) >= limit:
            break
    return matches


def _orm_recommendation_group(product_id: int, reason: str, limit: int) -> List[Dict[str, Any]]:
    # ORM 推薦關聯以 score 排序，這裡依 reason 拿出單一群組供商品頁顯示。
    if not _db_recommendations_enabled():
        return []
    results: List[Dict[str, Any]] = []
    queryset = (
        ProductRecommendationModel.objects.filter(source_product_id=product_id, reason=reason)
        .select_related("recommended_product")
        .order_by("-score", "id")
    )
    for relation in queryset:
        record = product_management._product_record_from_model(relation.recommended_product)
        if not product_management.is_public_product(record):
            continue
        results.append(product_management.prepare_product_for_display(record))
        if len(results) >= limit:
            break
    return results


def get_product_recommendations(product: Dict[str, Any], limit: int = 4) -> Dict[str, List[Dict[str, Any]]]:
    # 商品詳情頁需要分組後的推薦 payload；similar 會盡量補滿，also_bought 只吃 ORM 結果。
    if _db_recommendations_enabled():
        similar = _orm_recommendation_group(int(product["id"]), "similar", limit)
        also_bought = _orm_recommendation_group(int(product["id"]), "also_bought", 3)
    else:
        similar = []
        also_bought = []

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

    return {
        "similar": similar[:limit],
        "also_bought": also_bought,
    }

"""商品與賣家上架管理服務模組。

負責商品建立、編輯、審核、變體、圖片與庫存等核心商業邏輯。
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.contrib.auth.hashers import make_password
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from ..models import AppUser as AppUserModel
from ..models import Brand as BrandModel
from ..models import Category as CategoryModel
from ..models import Product as ProductModel
from ..models import ProductImage as ProductImageModel
from ..models import ProductTagRelation as ProductTagRelationModel
from ..models import ProductVariant as ProductVariantModel
from ..models import Tag as TagModel
from . import auth_demo
from . import cloud_storage as cloud_storage_service

# 商品 service 是整個商城後端的核心資料層。
# 這裡統一處理分類、商品、變體、圖片、標籤、運費設定與權限判斷，
# 並維持前端可直接使用的統一 payload。

# 這支 service 同時負責：
# - 商品分類主表
# - 前台商品瀏覽 / 篩選 / facets
# - 賣家商品建立、編輯、封存、複製
# - 管理端商品審核、上架、刪除
# - 庫存預留與回補

PUBLIC_STATUSES = {"active"}
SELLER_FORM_STATUSES = {"draft", "active"}
ADMIN_FORM_STATUSES = {"draft", "active", "archived"}
ARCHIVED_STATUS = "archived"
REJECTED_STATUS = "rejected"
PENDING_STATUS = "pending"
ACTIVE_STATUS = "active"
DRAFT_STATUS = "draft"
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
FILTERABLE_ATTRIBUTE_KEYS = ("color", "size")
FILTERABLE_ATTRIBUTE_ALIASES = {
    "color": ("color", "顏色", "颜色"),
    "size": ("size", "尺寸"),
}
STANDARD_SIZE_ORDER = ("XS", "S", "M", "L", "XL", "XXL", "F")
SIZE_ORDER_INDEX = {size: index for index, size in enumerate(STANDARD_SIZE_ORDER)}

DEFAULT_PRODUCT_SHIPPING_PROFILE = {
    "use_seller_rules": True,
    "allow_home_delivery": True,
    "allow_convenience_store": True,
    "override_home_delivery_fee": None,
    "override_convenience_store_fee": None,
}

# ---------------------------------------------------------------------------
# 商品分類主表
# 這一段負責正式分類主表的讀取、驗證、slug 對應與管理端新增。
# 前端會用在：
# - 賣家新增商品頁的分類選單
# - 商品總覽頁的分類 facets
# - `/categories/[slug]` 這類分類頁
# ---------------------------------------------------------------------------
def _category_sort_key(category: Dict[str, Any]) -> tuple[int, str]:
    # 分類列表優先依 sort_order 排，再用名稱穩定排序，方便導覽與後台維護。
    return int(category.get("sort_order") or 0), str(category.get("name") or "")


def _ensure_db_user_from_snapshot(snapshot: Dict[str, Any]) -> AppUserModel:
    # 商品 owner 可能來自 session / JSON snapshot；寫 ORM 商品前先補成可關聯的 `AppUser`。
    """Create or refresh the ORM user row for a JSON/session user snapshot."""
    username = str(snapshot.get("username") or "").strip()
    if not username:
        raise ValueError("Owner username is required.")
    email = str(snapshot.get("email") or "").strip() or f"{username}@seed.local"
    password_hash = str(snapshot.get("password_hash") or "").strip()
    if not password_hash:
        legacy_password = str(snapshot.get("password") or "").strip()
        if legacy_password:
            password_hash = make_password(legacy_password)
    user, created = AppUserModel.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "password_hash": password_hash,
            "display_name": str(snapshot.get("display_name") or username),
            "role": str(snapshot.get("role") or "seller"),
            "account_status": str(snapshot.get("account_status") or "active"),
            "seller_request_status": str(snapshot.get("seller_request_status") or "none"),
        },
    )
    if created:
        return user

    updated_fields: List[str] = []
    display_name = str(snapshot.get("display_name") or username)
    role = str(snapshot.get("role") or user.role or "seller")
    account_status = str(snapshot.get("account_status") or user.account_status or "active")
    seller_request_status = str(snapshot.get("seller_request_status") or user.seller_request_status or "none")
    if user.email != email:
        user.email = email
        updated_fields.append("email")
    if user.display_name != display_name:
        user.display_name = display_name
        updated_fields.append("display_name")
    if user.role != role:
        user.role = role
        updated_fields.append("role")
    if user.account_status != account_status:
        user.account_status = account_status
        updated_fields.append("account_status")
    if user.seller_request_status != seller_request_status:
        user.seller_request_status = seller_request_status
        updated_fields.append("seller_request_status")
    if password_hash and user.password_hash != password_hash:
        user.password_hash = password_hash
        updated_fields.append("password_hash")
    if updated_fields:
        user.save(update_fields=updated_fields + ["updated_at"])
    return user


def _db_categories_enabled() -> bool:
    # 分類表可查詢時，分類與 category filter 就優先走 ORM。
    """Return True when the ORM category table is available, even if it is currently empty."""
    try:
        CategoryModel.objects.count()
        return True
    except Exception:
        return False


def _db_products_enabled() -> bool:
    # 商品表可查詢時，商品詳情、列表與管理功能都優先走 ORM。
    """Return True when the ORM product table is available, even if it is currently empty."""
    try:
        ProductModel.objects.count()
        return True
    except Exception:
        return False


def _category_record_from_model(category: CategoryModel) -> Dict[str, Any]:
    # ORM 分類 row 轉回前端與舊 service 既有的 category payload 形狀。
    """Serialize ORM category rows into the same shape the JSON service already returns."""
    return {
        "id": category.id,
        "slug": category.slug.strip().lower(),
        "name": category.name.strip(),
        "label": category.name.strip(),
        "description": (category.description or "").strip(),
        "is_active": bool(category.is_active),
        "sort_order": 0,
        "created_at": category.created_at.isoformat() if category.created_at else "",
        "updated_at": category.updated_at.isoformat() if category.updated_at else "",
    }


def _product_variant_record_from_model(variant: ProductVariantModel) -> Dict[str, Any]:
    # 變體資料會直接被商品頁與購物車使用，所以這裡維持舊 dict 結構不變。
    """Serialize ORM variants into the legacy dict shape used by prepare_product_for_display."""
    return {
        "id": variant.id,
        "external_variant_id": variant.external_variant_id,
        "name": variant.name,
        "sku": variant.sku,
        "price": float(variant.price),
        "compare_at_price": float(variant.compare_at_price) if variant.compare_at_price is not None else None,
        "stock": int(variant.stock),
        "attributes": dict(variant.attributes or {}),
        "image": variant.image.file_path if variant.image_id and variant.image else "",
        "image_path_snapshot": variant.image_path_snapshot,
        "image_index": variant.image.sort_order if variant.image_id and variant.image else None,
    }


def _product_record_from_model(product: ProductModel) -> Dict[str, Any]:
    # ORM 商品 row 轉成 canonical product payload，圖片、變體與標籤在這裡一併展開。
    """Serialize ORM product rows into the canonical product payload shape."""
    images = [
        image.file_path
        for image in sorted(product.images.all(), key=lambda item: (item.sort_order, item.id))
        if image.file_path
    ]
    variants = [
        _product_variant_record_from_model(variant)
        for variant in sorted(product.variants.all(), key=lambda item: item.id)
    ]
    tags = sorted(
        {
            relation.tag.name
            for relation in product.producttagrelation_set.all()
            if relation.tag_id and relation.tag and relation.tag.name
        }
    )
    owner_username = product.owner.username if product.owner_id and product.owner else ""
    owner_display_name = product.owner.display_name if product.owner_id and product.owner else ""
    category_name = product.category.name if product.category_id and product.category else ""
    category_slug = product.category.slug if product.category_id and product.category else ""
    brand_name = product.brand.name if product.brand_id and product.brand else ""
    return {
        "id": product.id,
        "slug": product.slug,
        "name": product.name,
        "description": product.description or "",
        "price": float(product.price),
        "compare_at_price": float(product.compare_at_price) if product.compare_at_price is not None else None,
        "stock": int(product.stock),
        "price_compare_enabled": bool(product.price_compare_enabled),
        "price_compare_query": str(product.price_compare_query or ""),
        "specs": dict(product.specs or {}),
        "status": product.status,
        "review_note": product.review_note or "",
        "reviewed_at": product.reviewed_at.isoformat() if product.reviewed_at else "",
        "reviewed_by": product.reviewed_by.username if product.reviewed_by_id and product.reviewed_by else "",
        "owner_user_id": product.owner_id,
        "owner_username": owner_username,
        "owner_username_snapshot": product.owner_username_snapshot or owner_username,
        "owner_display_name_snapshot": product.owner_display_name_snapshot or owner_display_name,
        "owner_display_name": owner_display_name,
        "brand": brand_name,
        "brand_slug": slugify(brand_name),
        "category": category_name,
        "category_slug": category_slug,
        "images": images,
        "primary_image_index": product.primary_image_index,
        "variants": variants,
        "tags": tags,
        "shipping_profile": deepcopy(DEFAULT_PRODUCT_SHIPPING_PROFILE),
        "created_at": product.created_at.isoformat() if product.created_at else "",
        "updated_at": product.updated_at.isoformat() if product.updated_at else "",
    }


def _merge_product_records(
    preferred_record: Dict[str, Any],
    fallback_record: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # 以主要資料為準，必要時只補上缺少的相容欄位。
    """Merge product payloads while keeping the preferred record authoritative."""
    merged = deepcopy(fallback_record or {})
    merged.update(deepcopy(preferred_record))
    if fallback_record and fallback_record.get("shipping_profile") is not None:
        merged["shipping_profile"] = _normalize_shipping_profile(fallback_record.get("shipping_profile"))
    else:
        merged["shipping_profile"] = _normalize_shipping_profile(merged.get("shipping_profile"))
    return merged


def _db_products_queryset():
    # 商品相關頁面幾乎都會用到品牌、分類、圖片、變體與 tag，這裡集中定義預抓關聯。
    """Return the ORM queryset with the relations needed by catalog reads prefetched."""
    return (
        ProductModel.objects.select_related("brand", "category", "owner", "reviewed_by")
        .prefetch_related(
            Prefetch("images", queryset=ProductImageModel.objects.order_by("sort_order", "id")),
            Prefetch("variants", queryset=ProductVariantModel.objects.select_related("image").order_by("id")),
            Prefetch(
                "producttagrelation_set",
                queryset=ProductTagRelationModel.objects.select_related("tag"),
            ),
        )
        .order_by("id")
    )


def _merged_category_records(*, include_inactive: bool) -> List[Dict[str, Any]]:
    # 分類目前直接以 ORM 為主資料源。
    """Return category payloads from ORM, optionally including inactive rows."""
    queryset = CategoryModel.objects.all().order_by("name")
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return sorted([_category_record_from_model(category) for category in queryset], key=_category_sort_key)


def _merged_public_product_records() -> List[Dict[str, Any]]:
    # 商城前台只讀可公開商品，這裡回傳已 prepare 過、可直接給商品卡與列表頁的資料。
    """Return public product payloads for storefront reads."""
    records: List[Dict[str, Any]] = []
    for product in _db_products_queryset():
        record = _product_record_from_model(product)
        if is_public_product(record):
            records.append(record)
    return [prepare_product_for_display(product) for product in records]


def _all_product_records_for_slug_generation() -> List[Dict[str, Any]]:
    # 建立新 slug 前先蒐集所有既有 slug，避免撞名。
    """Collect current product slugs before generating a new one."""
    return [{"slug": product.slug, "id": product.id} for product in ProductModel.objects.only("id", "slug")]


def _db_products_for_owner(username: str) -> List[Dict[str, Any]]:
    # 賣家中心列表讀自己名下商品時，這裡提供 ORM -> legacy payload 的統一入口。
    """Return ORM-backed seller products serialized into the legacy dict shape."""
    queryset = _db_products_queryset().filter(owner__username=username)
    return [_product_record_from_model(product) for product in queryset]


def _json_product_by_slug(slug: str) -> Dict[str, Any] | None:
    # 保留舊命名的相容入口，實際上仍回傳 canonical product payload。
    """Return the canonical product payload for a slug."""
    return _db_product_record_by_slug(slug)


def _db_product_record_by_slug(slug: str) -> Dict[str, Any] | None:
    # ORM 模式下依 slug 讀單一商品，回傳 canonical payload 給上層共用。
    """Return the ORM-backed product payload for a slug when the database is enabled."""
    product = _db_products_queryset().filter(slug=slug).first()
    return _product_record_from_model(product) if product else None


def _merged_product_record_by_slug(slug: str) -> Dict[str, Any] | None:
    # 單商品查詢的統一入口；前台詳情、後台管理與比較功能都會用到。
    """Return one canonical product payload by slug."""
    return _db_product_record_by_slug(slug)


def _save_product_record_to_json(product: Dict[str, Any]) -> Dict[str, Any]:
    # 保留舊介面的相容 hook；目前正式資料不會回寫本地 JSON。
    """Keep the compatibility hook as an in-memory no-op."""
    return deepcopy(product)


def _persist_product_record(
    product: Dict[str, Any],
    *,
    previous_slug: str = "",
) -> Dict[str, Any]:
    # 商品寫入一律先整理成 canonical payload；ORM 可用時先落 ORM，再回傳 prepare 過的最終結果。
    """Persist one canonical product payload into ORM first, then backfill JSON compatibility."""
    orm_payload = deepcopy(product)
    owner_snapshot = {
        "username": str(orm_payload.get("owner_username") or orm_payload.get("owner_username_snapshot") or ""),
        "display_name": str(
            orm_payload.get("owner_display_name")
            or orm_payload.get("owner_display_name_snapshot")
            or ""
        ),
    }
    orm_payload = _sync_product_record_to_orm(
        orm_payload,
        owner_snapshot=owner_snapshot,
        previous_slug=previous_slug or str(product.get("slug") or ""),
    )
    canonical = _merge_product_records(orm_payload, product)
    previous_slug = str(previous_slug or "").strip()
    current_slug = str(canonical.get("slug") or "").strip()
    if previous_slug and current_slug and previous_slug != current_slug:
        from . import banners as banner_service

        banner_service.update_product_banner_links(previous_slug, current_slug)
    return prepare_product_for_display(canonical)


def list_product_categories(*, include_inactive: bool = False) -> List[Dict[str, Any]]:
    # 商品表單、catalog facets 與分類導覽都共用這個分類列表入口。
    """讀取商品分類主表。"""
    return _merged_category_records(include_inactive=include_inactive)


def list_active_product_categories() -> List[Dict[str, Any]]:
    # 前台只需要啟用中的分類，這個 helper 是最常用的窄化版本。
    """讀取啟用中的商品分類，供賣家表單與前台篩選使用。"""
    return list_product_categories(include_inactive=False)


def get_product_category_by_slug(category_slug: str, *, include_inactive: bool = True) -> Dict[str, Any] | None:
    # 依 slug 找分類是商品表單回填與分類頁路由的主要查詢方式。
    """依 slug 查詢單一商品分類主表項目。"""
    clean_slug = str(category_slug or "").strip().lower()
    if not clean_slug:
        return None
    for category in list_product_categories(include_inactive=include_inactive):
        if category["slug"] == clean_slug:
            return category
    return None


def _resolve_product_category_record(product: Dict[str, Any]) -> Dict[str, Any] | None:
    # 商品資料可能只存 category 名稱或 slug；這裡把它解析成完整分類 record。
    """把商品上既有的分類欄位對應回分類主表。"""
    stored_slug = str(product.get("category_slug") or "").strip().lower()
    if stored_slug:
        category = get_product_category_by_slug(stored_slug, include_inactive=True)
        if category:
            return category

    raw_category = str(product.get("category") or "").strip()
    if not raw_category:
        return None

    lowered_name = raw_category.lower()
    for category in list_product_categories(include_inactive=True):
        if category["name"] == raw_category or category["slug"] == lowered_name:
            return category
        if slugify(category["name"]) and slugify(category["name"]) == lowered_name:
            return category
    return None


def _product_category_slug(product: Dict[str, Any]) -> str:
    # catalog filter 與分類頁路由都依賴 canonical category slug。
    """取得商品分類的 canonical slug，供 catalog filter 使用。"""
    category = _resolve_product_category_record(product)
    if category:
        return category["slug"]
    stored_slug = str(product.get("category_slug") or "").strip().lower()
    if stored_slug:
        return stored_slug
    return slugify(str(product.get("category") or "").strip())


def _product_category_label(product: Dict[str, Any]) -> str:
    # 商品卡片與詳情頁顯示分類名稱時，優先用解析後的正式分類名稱。
    """取得商品分類顯示名稱。"""
    category = _resolve_product_category_record(product)
    if category:
        return category["name"]
    return str(product.get("category") or "").strip()


def _require_product_category(category_value: str) -> Dict[str, Any]:
    # 建立 / 編輯商品時，必須把表單的 category 值驗證成目前可用分類。
    """驗證送入的分類值是否存在於分類主表。"""
    clean_value = str(category_value or "").strip().lower()
    if not clean_value:
        raise ValueError("Category is required.")
    for category in list_product_categories(include_inactive=False):
        if category["slug"] == clean_value:
            return category
        if str(category["name"]).strip().lower() == clean_value:
            return category
        if slugify(str(category["name"])) == clean_value:
            return category
    raise ValueError("Selected category is not available.")


def _next_category_id(categories: List[Dict[str, Any]]) -> int:
    # 以記憶體 payload 操作分類時，仍需要穩定遞增 id。
    return max((int(item.get("id") or 0) for item in categories), default=0) + 1


def _generate_category_slug(name: str, categories: List[Dict[str, Any]], *, requested_slug: str = "") -> str:
    # 分類 slug 允許自訂，但若撞名就自動加序號避開重複。
    """為管理端新增分類產生唯一 slug。"""
    base = slugify(requested_slug.strip() or name.strip()) or "category"
    existing = {str(item.get("slug") or "").strip().lower() for item in categories}
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_product_category(
    *,
    name: str,
    slug: str = "",
    description: str = "",
    is_active: bool = True,
) -> Dict[str, Any]:
    # 後台建立分類入口；ORM 可用時直接寫資料庫，否則退回 JSON snapshot。
    """由管理端建立新的商品分類主表項目。"""
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Category name is required.")

    categories = _merged_category_records(include_inactive=True)
    if any(str(item.get("name") or "").strip() == clean_name for item in categories):
        raise ValueError("Category name already exists.")

    now = timezone.now().isoformat()
    next_id = _next_category_id(categories)
    slug_value = _generate_category_slug(clean_name, categories, requested_slug=str(slug or ""))
    category = {
        "id": next_id,
        "slug": slug_value,
        "name": clean_name,
        "description": str(description or "").strip(),
        "is_active": bool(is_active),
        "sort_order": len(categories) + 1,
        "created_at": now,
        "updated_at": now,
    }
    category_model = CategoryModel.objects.create(
        slug=slug_value,
        name=clean_name,
        description=str(description or "").strip(),
        is_active=bool(is_active),
    )
    category["id"] = category_model.id
    category["created_at"] = category_model.created_at.isoformat() if category_model.created_at else now
    category["updated_at"] = category_model.updated_at.isoformat() if category_model.updated_at else now
    return get_product_category_by_slug(category["slug"], include_inactive=True) or category


# ---------------------------------------------------------------------------
# 商品可見性 / 權限判斷
# 這一段決定：
# - 哪些商品能在前台看見
# - 賣家能不能管理自己的商品
# - staff / admin 能不能審核與檢視
# ---------------------------------------------------------------------------
def is_public_product(product: Dict[str, Any]) -> bool:
    # 前台是否可見只看 canonical status，避免舊資料大小寫或別名造成判斷不一致。
    """判斷 商品管理 條件是否成立。

    參數:
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return _canonical_status(product.get("status")) in PUBLIC_STATUSES


def can_manage_product(user: Dict[str, str] | None, product: Dict[str, Any]) -> bool:
    # 商品擁有者可管理自己的商品，這是賣家中心的最基本權限判斷。
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return bool(user and product.get("owner_username") == user["username"])


def can_review_product(user: Dict[str, str] | None) -> bool:
    # 只有 admin / staff 能做商品審核相關操作。
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return auth_demo.is_admin(user)


def can_sell(user: Dict[str, str] | None) -> bool:
    # 賣家、admin、staff 都可進入商品建立與編輯流程。
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return auth_demo.is_seller(user)


def can_view_product(user: Dict[str, str] | None, product: Dict[str, Any]) -> bool:
    # 前台可見性 = 公開商品，或是商品本人 / 審核者可看見未公開內容。
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return is_public_product(product) or can_manage_product(user, product) or can_review_product(user)


# ---------------------------------------------------------------------------
# 商品查詢主流程
# 這一段提供前台、賣家、管理端各自的商品清單與單筆查詢。
# ---------------------------------------------------------------------------
def list_public_products() -> List[Dict[str, Any]]:
    # 商城首頁、分類頁與搜尋結果都走這個公共商品列表入口。
    """列出前台可見商品。"""
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    return _merged_public_product_records()


def list_products_for_user(username: str) -> List[Dict[str, Any]]:
    # 賣家中心列出某位使用者名下商品，並依更新時間倒序排列。
    """列出指定賣家名下商品。"""
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    ordered = sorted(
        _db_products_for_owner(username),
        key=lambda item: item.get("updated_at", item.get("created_at", "")),
        reverse=True,
    )
    return [prepare_product_for_display(product) for product in ordered]


def list_pending_products() -> List[Dict[str, Any]]:
    # 管理端審核頁會讀 pending 商品列表。
    """列出待審核商品。"""
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    products = [_product_record_from_model(product) for product in _db_products_queryset().filter(status=PENDING_STATUS)]
    ordered = sorted(products, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return [prepare_product_for_display(product) for product in ordered]


def list_moderation_products() -> List[Dict[str, Any]]:
    # 已公開商品也可能需要審核 / 管理檢視，這裡回傳 active 商品總表。
    """列出後台審核中心需要關注的商品。"""
    """列出目前已上架的商品，供管理者進行強制下架。"""
    products = [_product_record_from_model(product) for product in _db_products_queryset().filter(status=ACTIVE_STATUS)]
    ordered = sorted(products, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return [prepare_product_for_display(product) for product in ordered]


def list_products_for_admin() -> List[Dict[str, Any]]:
    # 後台商品總表不做可見性過濾，需看得到所有狀態的商品。
    """列出管理端可見的全站商品，讀取時以 ORM 為主、JSON 為相容補充。"""
    products = [_product_record_from_model(product) for product in _db_products_queryset()]
    return [prepare_product_for_display(product) for product in products]


def get_user_product(username: str, slug: str) -> Dict[str, Any] | None:
    # 賣家編輯頁只允許讀自己名下的商品，這裡先做 owner 篩選。
    """讀取賣家自己的單一商品。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    db_product = _db_products_queryset().filter(owner__username=username, slug=slug).first()
    if db_product:
        return prepare_product_for_display(_product_record_from_model(db_product))
    return None


def get_visible_product(slug: str, user: Dict[str, str] | None = None) -> Dict[str, Any] | None:
    # 商品詳情頁讀取入口；未公開商品只有 owner 或審核者能看到。
    """讀取前台目前可見的單一商品。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        slug: 商品或頁面使用的網址識別字串。
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    db_product = _db_products_queryset().filter(slug=slug).first()
    product = _product_record_from_model(db_product) if db_product else None
    if not product or not can_view_product(user, product):
        return None
    return prepare_product_for_display(product)


def get_product_for_admin(slug: str) -> Dict[str, Any] | None:
    # 後台編輯頁需要直接拿到完整商品，不受可見性限制。
    """讀取管理端可見的單一商品。"""
    product = _merged_product_record_by_slug(slug)
    return prepare_product_for_display(product) if product else None


def get_product_for_review(slug: str) -> Dict[str, Any] | None:
    # 商品審核頁與 admin 取用相同資料，只是語意上分成 review 專用入口。
    """讀取審核流程用的單一商品。"""
    product = _merged_product_record_by_slug(slug)
    return prepare_product_for_display(product) if product else None


def _next_product_id(products: List[Dict[str, Any]]) -> int:
    # 以記憶體 payload 操作商品時，仍需要穩定遞增 id。
    """計算下一個可用的商品 id。"""
    return max([int(item.get("id", 0)) for item in products] or [0]) + 1


# ---------------------------------------------------------------------------
# 商品欄位正規化
# 這一段把表單送進來的 tags / specs / price / stock / shipping profile /
# variants 等欄位整理成一致格式，供 create / update 流程重用。
# ---------------------------------------------------------------------------
def _normalize_tags(raw_tags: str) -> List[str]:
    # 後台 / 賣家表單的 tags 用逗號分隔，這裡清理成前端熟悉的字串陣列。
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        raw_tags: 表單輸入的標籤原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    return [item.strip() for item in raw_tags.split(",") if item.strip()]


def _normalize_specs(raw_specs: str) -> Dict[str, str]:
    # specs 編輯器使用 `key:value` 多行格式，這裡轉成商品 payload 內的 dict。
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        raw_specs: 表單輸入的規格原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    specs: Dict[str, str] = {}
    for line in raw_specs.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        if ":" not in clean_line:
            raise ValueError("Each spec line must use the format key:value.")
        key, value = clean_line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError("Each spec line must include both key and value.")
        specs[key] = value
    return specs


def _parse_price(raw_price: str) -> Decimal:
    # 價格欄位統一解析成兩位小數的 Decimal，供商品主價與 variant 價格共用。
    """解析原始輸入值，轉成 商品管理 流程內部使用的格式。

    參數:
        raw_price: 價格欄位的原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    try:
        price = Decimal(str(raw_price).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("Price must be a valid number.") from None
    if price <= 0:
        raise ValueError("Price must be greater than zero.")
    return price.quantize(Decimal("0.01"))


def _parse_optional_price(raw_price: str) -> Decimal | None:
    # compare_at_price 或運費覆寫等可空金額欄位共用這個寬鬆解析 helper。
    """解析原始輸入值，轉成 商品管理 流程內部使用的格式。

    參數:
        raw_price: 價格欄位的原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    clean_value = str(raw_price).strip()
    if not clean_value:
        return None
    return _parse_price(clean_value)


def _parse_stock(raw_stock: str) -> int:
    # 商品與 variant 庫存都要求非負整數，錯誤訊息集中在這裡維持一致。
    """解析原始輸入值，轉成 商品管理 流程內部使用的格式。

    參數:
        raw_stock: 庫存欄位的原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    try:
        stock = int(str(raw_stock).strip())
    except ValueError:
        raise ValueError("Stock must be a whole number.") from None
    if stock < 0:
        raise ValueError("Stock cannot be negative.")
    return stock


def _parse_optional_int(raw_value: str) -> int | None:
    # variant 的 image_index 是可選欄位；有填時必須是從 1 開始的整數。
    """解析原始輸入值，轉成 商品管理 流程內部使用的格式。

    參數:
        raw_value: 尚未轉型的原始輸入值。

    回傳:
        依函式用途回傳對應資料。
    """
    clean_value = str(raw_value).strip()
    if not clean_value:
        return None
    try:
        number = int(clean_value)
    except ValueError:
        raise ValueError("Image index must be a whole number.") from None
    if number <= 0:
        raise ValueError("Image index must start from 1.")
    return number


def _normalize_primary_image_index(raw_value: Any, images: List[str]) -> int | None:
    # 主商品預設圖索引必須落在目前圖片範圍內；超出時退回未指定，避免前台拿到壞索引。
    number = _parse_optional_int(str(raw_value or ""))
    if number is None:
        return None
    return number if 1 <= number <= len(images) else None


def _parse_bool_flag(raw_value: Any, default: bool = False) -> bool:
    # HTML form checkbox / API bool 字串都在這裡轉成穩定布林值。
    """Normalize checkbox / form-data style boolean values."""
    if raw_value is None or raw_value == "":
        return default
    if isinstance(raw_value, bool):
        return raw_value
    value = str(raw_value).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _serialize_optional_decimal(value: Decimal | None) -> float | None:
    # 商品 payload 最終要能 JSON 化，這裡把可選 Decimal 轉成 float 或 None。
    """Return a JSON-friendly float for optional Decimal values."""
    return float(value) if value is not None else None


def _normalize_shipping_profile(raw_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # 商品層運費設定可覆蓋賣家預設規則，這裡整理出穩定的 shipping_profile 結構。
    """Return a stable product-level shipping config."""
    profile = dict(DEFAULT_PRODUCT_SHIPPING_PROFILE)
    if isinstance(raw_profile, dict):
        profile.update(raw_profile)
    override_home_delivery_fee = profile.get("override_home_delivery_fee")
    override_convenience_store_fee = profile.get("override_convenience_store_fee")
    return {
        "use_seller_rules": bool(profile.get("use_seller_rules", True)),
        "allow_home_delivery": bool(profile.get("allow_home_delivery", True)),
        "allow_convenience_store": bool(profile.get("allow_convenience_store", True)),
        "override_home_delivery_fee": float(override_home_delivery_fee) if override_home_delivery_fee not in (None, "") else None,
        "override_convenience_store_fee": float(override_convenience_store_fee)
        if override_convenience_store_fee not in (None, "")
        else None,
    }


def _build_shipping_profile_from_form(form_data: Dict[str, Any], existing_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # 建立 / 編輯商品時，從表單欄位組出商品層專用的運費設定。
    """Build product-level shipping config from seller/admin form data."""
    base = _normalize_shipping_profile(existing_profile)
    use_seller_rules = _parse_bool_flag(form_data.get("use_seller_shipping_rules"), base["use_seller_rules"])
    allow_home_delivery = _parse_bool_flag(form_data.get("allow_home_delivery"), base["allow_home_delivery"])
    allow_convenience_store = _parse_bool_flag(form_data.get("allow_convenience_store"), base["allow_convenience_store"])
    if not allow_home_delivery and not allow_convenience_store:
        raise ValueError("At least one shipping method must stay enabled for the product.")

    override_home_delivery_fee = None
    override_convenience_store_fee = None
    if not use_seller_rules:
        override_home_delivery_fee = _parse_optional_price(form_data.get("override_home_delivery_fee", ""))
        override_convenience_store_fee = _parse_optional_price(form_data.get("override_convenience_store_fee", ""))

    return {
        "use_seller_rules": use_seller_rules,
        "allow_home_delivery": allow_home_delivery,
        "allow_convenience_store": allow_convenience_store,
        "override_home_delivery_fee": _serialize_optional_decimal(override_home_delivery_fee),
        "override_convenience_store_fee": _serialize_optional_decimal(override_convenience_store_fee),
    }


def _normalize_status(raw_status: str, user: Dict[str, str], existing_status: str | None = None) -> str:
    # 表單傳進來的商品狀態要先收斂成 seller / admin 都看得懂的 canonical 狀態值。
    # 商品狀態會依角色限制可選值：賣家只能 draft/active，管理者可額外設 archived。
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        raw_status: 表單送入的商品狀態字串。
        user: 目前操作中的會員快照資料。
        existing_status: 商品原本狀態，用來判斷是否允許切換。

    回傳:
        依函式用途回傳對應資料。
    """
    status = _canonical_status(raw_status.strip().lower() or existing_status or DRAFT_STATUS)
    allowed = ADMIN_FORM_STATUSES if auth_demo.is_admin(user) else SELLER_FORM_STATUSES
    if status not in allowed:
        raise ValueError("Invalid status value.")
    return status


def _canonical_status(raw_status: Any) -> str:
    # 舊資料裡的 pending / rejected 會對映成新版 draft / archived，避免前後台分叉。
    # 舊資料曾出現 pending / rejected 等暫時狀態，這裡統一映射回目前的三態模型。
    """把舊商品審核狀態映射到目前使用的狀態集合。"""
    status = str(raw_status or DRAFT_STATUS).strip().lower()
    if status == PENDING_STATUS:
        return DRAFT_STATUS
    if status == REJECTED_STATUS:
        return ARCHIVED_STATUS
    if status not in {DRAFT_STATUS, ACTIVE_STATUS, ARCHIVED_STATUS}:
        return DRAFT_STATUS
    return status


def _generate_unique_slug(name: str, products: List[Dict[str, Any]], current_slug: str | None = None) -> str:
    # 商品名稱會先變成 base slug，再避開現有商品衝突，必要時自動加流水號。
    # 商品改名或複製時都靠這裡產生唯一 slug，並保留編輯時原 slug 不算衝突。
    """處理 商品管理 相關流程。

    參數:
        name: 名稱字串，可能是商品名稱、變體名稱或檔名來源。
        products: 商品資料列表。
        current_slug: 原始 slug，更新商品名稱時可避免與自己衝突。

    回傳:
        依函式用途回傳對應資料。
    """
    base_slug = slugify(name.strip())
    if not base_slug:
        if current_slug:
            base_slug = current_slug
        else:
            timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
            base_slug = f"product-{timestamp}"
    slug = base_slug
    counter = 2
    existing_slugs = {item.get("slug") for item in products if item.get("slug") != current_slug}
    while slug in existing_slugs:
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _upload_dir() -> Path:
    # 所有商品圖統一落在 static/uploads/products，與 banner 等其他資源目錄分開。
    # 商品圖片統一存放在 static/uploads/products，與社群圖、banner 圖分開。
    """處理 商品管理 相關流程。

    回傳:
        依函式用途回傳對應資料。
    """
    return Path(settings.BASE_DIR) / "static" / "uploads" / "products"


def _save_uploaded_images(product_slug: str, uploaded_files: Iterable[UploadedFile]) -> List[str]:
    """將上傳圖片寫入商品圖目錄並回傳公開路徑。"""
    # 建檔與編輯商品共用這條路徑，檔名會帶 slug 與 timestamp，避免多次上傳互相覆蓋。
    # 將本次上傳的圖片寫入 static 目錄，並回傳 product payload 要存的公開路徑。
    # 建檔與編輯商品共用這條路徑，檔名會帶 slug 與 timestamp，避免多次上傳互相覆蓋。
    # 商品建立 / 編輯時的新上傳圖片都會先落地，回傳可直接塞進 payload 的靜態路徑。
    """處理 商品管理 相關流程。

    參數:
        product_slug: 商品 slug，常用在圖片存檔或 URL 建立。
        uploaded_files: 使用者上傳的圖片檔案集合。

    回傳:
        依函式用途回傳對應資料。
    """
    saved_paths: List[str] = []
    upload_dir = _upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    for index, uploaded_file in enumerate(uploaded_files, start=1):
        if not uploaded_file:
            continue
        extension = Path(uploaded_file.name).suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError("Only jpg, jpeg, png, webp, and gif images are allowed.")
        if uploaded_file.size > MAX_IMAGE_SIZE_BYTES:
            raise ValueError("Each image must be 5 MB or smaller.")
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
        file_name = f"{product_slug}-{timestamp}-{index}{extension}"
        object_name = f"products/{file_name}"
        if cloud_storage_service.is_enabled():
            uploaded_path = cloud_storage_service.upload_image(uploaded_file, object_name)
            if not uploaded_path:
                raise ValueError("Unable to upload the image to cloud storage.")
            saved_paths.append(uploaded_path)
            continue
        target_path = upload_dir / file_name
        with target_path.open("wb") as output:
            for chunk in uploaded_file.chunks():
                output.write(chunk)
        saved_paths.append(f"/static/uploads/products/{file_name}")
    return saved_paths


def _serialize_review_fields(product: Dict[str, Any], note: str = "") -> None:
    """將商品審核備註與審核時間寫回 payload。"""
    # 這裡不做權限判斷，只負責把審核結果格式化進商品資料。
    # 商品審核結果會補 review_note / reviewed_at，讓賣家中心與後台都能顯示最後一次審核資訊。
    # 這裡不做權限判斷，只負責把審核結果寫回商品 payload。
    # 商品被審核、下架或重新發佈時，統一在這裡更新 review_note 與 reviewed_at。
    """把 商品管理 相關資料整理成較適合輸出或渲染的格式。

    參數:
        product: 單一商品資料字典。
        note: 補充說明、審核備註或操作備註。

    回傳:
        依函式用途回傳對應資料。
    """
    product["review_note"] = note.strip()
    product["reviewed_at"] = timezone.now().isoformat()


def _delete_product_image(image_path: str) -> None:
    """刪除商品上傳目錄中的單張圖片。"""
    # 只允許刪除商品圖目錄內的檔案，避免誤碰其他 static 資產。
    # 只允許刪除商品上傳目錄內的檔案，避免誤碰其他 static 資產。
    # 被移除的圖片會在商品編輯時一併清掉，避免 static 資料夾累積孤兒檔案。
    # 只允許刪除商品上傳目錄底下的圖片，避免誤刪到其他 static 資源。
    """處理 商品管理 相關流程。

    參數:
        image_path: 單一圖片在媒體目錄中的相對路徑。

    回傳:
        依函式用途回傳對應資料。
    """
    if cloud_storage_service.delete_by_public_url(image_path):
        return
    if not image_path.startswith("/static/uploads/products/"):
        return
    relative = image_path.lstrip("/").replace("/", "\\")
    target = Path(settings.BASE_DIR) / relative
    if target.exists():
        target.unlink()


def _merge_image_changes(
    product: Dict[str, Any],
    form_data: Dict[str, Any],
    uploaded_files: Iterable[UploadedFile],
    next_slug: str,
) -> List[str]:
    """合併商品編輯時的既有圖片、刪除清單與新上傳圖片。"""
    # 前端可同時調整既有順序、刪除部分圖片，再補上新圖；最後都收斂成單一 images 陣列。
    # 編輯商品時，這裡會把既有圖片排序、刪除清單與新上傳圖片合併成最終 images。
    # 前端可同時調整既有順序、刪除部分圖片，再補上新圖；最後都收斂成單一 images 陣列。
    # 編輯商品時，保留既有圖片順序、移除被勾選刪除的圖片，再把新上傳圖片接到尾端。
    """合併 商品管理 流程中不同來源的資料結果。

    參數:
        product: 單一商品資料字典。
        form_data: 從表單或 API 送入的原始欄位資料。
        uploaded_files: 使用者上傳的圖片檔案集合。
        next_slug: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    existing_images = list(product.get("images", []))
    remove_images = set(form_data.getlist("remove_image_paths")) if hasattr(form_data, "getlist") else set()
    ordered_images = list(form_data.getlist("existing_image_paths")) if hasattr(form_data, "getlist") else existing_images

    kept_images = [image for image in ordered_images if image in existing_images and image not in remove_images]
    for image in existing_images:
        if image not in kept_images and image not in remove_images:
            kept_images.append(image)
    final_existing = [image for image in kept_images if image not in remove_images]

    for image in remove_images:
        if image in existing_images:
            _delete_product_image(image)

    uploaded_images = _save_uploaded_images(next_slug, uploaded_files)
    return final_existing + uploaded_images


def _variant_id_from_parts(name: str, sku: str, index: int) -> str:
    """依名稱、SKU 與索引組出穩定的 variant id。"""
    # variant id 要保持穩定，名稱與 SKU 相同時再用 index 避免碰撞。
    # 這裡保留 Unicode，避免中文顏色 / 尺寸名稱在 slugify 後全部塌成同一個 ASCII 值。
    # variant id 優先用 SKU / 名稱產生，保留 Unicode 以免中文顏色或尺寸被壓成同一 slug。
    """處理 商品管理 相關流程。

    參數:
        name: 名稱字串，可能是商品名稱、變體名稱或檔名來源。
        sku: 庫存管理單位，用來區分商品變體。
        index: 目前處理項目的索引值。

    回傳:
        依函式用途回傳對應資料。
    """
    # Preserve Unicode so Chinese color/name variants do not collapse to the same ASCII slug.
    base = slugify(sku or name or f"variant-{index}", allow_unicode=True)
    return base or f"variant-{index}"


def _normalize_variant_attributes(color: str = "", size: str = "") -> Dict[str, str]:
    """將 color / size 欄位收斂成固定 attributes dict。"""
    # 目前前台直接依賴這兩個常見屬性，所以先固定成簡單結構。
    # 目前前台只直接吃 color / size 兩個常見屬性，所以先收斂成固定 attributes dict。
    # 目前 variant 屬性只正式支援 color / size，這裡整理成 attributes dict。
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        color: 顏色屬性值。
        size: 尺寸屬性值。

    回傳:
        依函式用途回傳對應資料。
    """
    attributes: Dict[str, str] = {}
    if color.strip():
        attributes["color"] = color.strip()
    if size.strip():
        attributes["size"] = size.strip()
    return attributes


def _normalize_variants(raw_variants: str) -> List[Dict[str, Any]]:
    """解析後台 textarea 送來的多行 variant 定義。"""
    # 每行格式固定為 `Name|SKU|Price|Stock|Color|Size|ImageIndex|CompareAtPrice`。
    # 後台 textarea 會把每個 variant 壓成 `Name|SKU|Price|...` 一行，
    # 這裡負責解析、驗證欄位數量，並轉成商品 payload 要存的標準結構。
    # variants 編輯器使用 `Name|SKU|Price|...` 每行格式，這裡解析並驗證成標準 payload。
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        raw_variants: 表單輸入的變體原始文字內容。

    回傳:
        依函式用途回傳對應資料。
    """
    variants: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, line in enumerate(raw_variants.splitlines(), start=1):
        clean_line = line.strip()
        if not clean_line:
            continue
        parts = [part.strip() for part in clean_line.split("|")]
        if len(parts) not in {4, 5, 6, 7, 8}:
            raise ValueError("Each variant line must use Name|SKU|Price|Stock|Color|Size|ImageIndex|CompareAtPrice.")
        normalized_parts = parts + [""] * (8 - len(parts))
        name, sku, raw_price, raw_stock, color, size, image_index, raw_compare_at_price = normalized_parts
        if not name:
            raise ValueError("Each variant must have a name.")
        variant_id = _variant_id_from_parts(name, sku, index)
        if variant_id in seen_ids:
            raise ValueError("Variant names/SKUs must be unique.")
        seen_ids.add(variant_id)
        attributes = _normalize_variant_attributes(color=color, size=size)
        price_decimal = _parse_price(raw_price)
        compare_at_price = _parse_optional_price(raw_compare_at_price)
        variants.append(
            {
                "id": variant_id,
                "name": name,
                "sku": sku,
                "price": float(price_decimal),
                "compare_at_price": _serialize_compare_at_price(compare_at_price, price_decimal),
                "stock": _parse_stock(raw_stock),
                "attributes": attributes,
                "image_index": _parse_optional_int(image_index),
            }
        )
    return variants


def _summarize_variant_pricing(variants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """彙整多規格商品的最低價、最高價與總庫存摘要。"""
    # 多規格商品的商品卡只顯示最低價、最高價與總庫存，這裡先彙整出摘要欄位。
    # 實際單一規格的價格與庫存仍留在 variants，這裡只是給列表頁與卡片摘要使用。
    # 有 variants 時，商品主價與總庫存以 variants 匯總結果為準。
    """處理 商品管理 相關流程。

    參數:
        variants: 商品變體列表。

    回傳:
        依函式用途回傳對應資料。
    """
    prices = [Decimal(str(item["price"])) for item in variants]
    total_stock = sum(int(item.get("stock", 0)) for item in variants)
    return {
        "price": float(min(prices)),
        "max_price": float(max(prices)),
        "stock": total_stock,
    }


def _serialize_compare_at_price(compare_at_price: Decimal | None, price: Decimal) -> float | None:
    """驗證並序列化商品劃線價。"""
    # 若未提供 compare-at price，就回傳 None，讓前台自然不顯示劃線價。
    # compare-at price 是劃線價，不能低於實售價；合法時才寫回 payload。
    # 若未提供 compare-at price，就回傳 None，讓前台自然不顯示劃線價。
    # compare_at_price 不能低於售價，這裡集中處理驗證與序列化。
    """把 商品管理 相關資料整理成較適合輸出或渲染的格式。

    參數:
        compare_at_price: 原價或參考價，用來計算折扣展示。
        price: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    if compare_at_price is None:
        return None
    if compare_at_price < price:
        raise ValueError("Compare-at price must be greater than or equal to the sale price.")
    return float(compare_at_price)


def _bind_variant_images(variants: List[Dict[str, Any]], images: List[str]) -> List[Dict[str, Any]]:
    """依 image_index 把 variant 對回實際商品圖片。"""
    # 沒有指定 image_index 的 variant 仍保留空字串，交給前台退回商品主圖或預設圖。
    # variant 的 image_index 會在這裡對回實際圖片 URL，讓前台能直接顯示對應規格圖。
    # 沒有指定 image_index 的 variant 仍保留空字串，交給前台退回商品主圖或預設圖。
    # variant 可透過 image_index 指到商品圖陣列，這裡把索引轉成實際圖片路徑。
    """把 商品管理 中彼此關聯的資料綁定在一起。

    參數:
        variants: 商品變體列表。
        images: 圖片路徑列表。

    回傳:
        依函式用途回傳對應資料。
    """
    bound_variants: List[Dict[str, Any]] = []
    for variant in variants:
        item = dict(variant)
        image_index = item.get("image_index")
        if isinstance(image_index, int) and 1 <= image_index <= len(images):
            item["image"] = images[image_index - 1]
        else:
            item["image"] = ""
        bound_variants.append(item)
    return bound_variants


def _get_or_create_brand_model(brand_name: str) -> BrandModel:
    """將商品品牌文字解析成 ORM brand master table 的紀錄。"""
    # 沒有對應品牌時會建立新 master record，既有品牌則更新名稱並重用關聯。
    # 將表單內的品牌文字收斂到 ORM 的品牌主檔，沒有就建立、有差異就更新名稱。
    # ORM 商品模型需要 brand master table，文字品牌名稱在這裡解析成 BrandModel。
    # 商品寫 ORM 前先把品牌名稱對應到 brand master table，避免重複品牌字串散落。
    """Resolve product brand text into the ORM brand master table."""
    clean_name = brand_name.strip()
    if not clean_name:
        raise ValueError("Brand is required.")
    brand = BrandModel.objects.filter(name=clean_name).first()
    if brand:
        return brand

    slug = slugify(clean_name) or clean_name.lower().replace(" ", "-")
    brand = BrandModel.objects.filter(slug=slug).first()
    if not brand:
        return BrandModel.objects.create(
            slug=slug,
            name=clean_name,
            description="",
            is_active=True,
        )

    if brand.name != clean_name:
        brand.name = clean_name
        brand.save(update_fields=["name", "updated_at"])
    return brand


def _get_category_model_by_slug(category_slug: str) -> CategoryModel:
    """依 category slug 取得 ORM category master table 的紀錄。"""
    # ORM 商品需要實際 category row，這裡負責把前端 slug 對回分類主檔。
    # 將前端或表單傳來的 category slug 對回 ORM 分類主檔，後續商品模型會直接用這筆關聯。
    # ORM 商品必須掛正式 category row，這裡從 category slug 解析出對應 model。
    """Resolve category slug from the ORM category master table."""
    category = CategoryModel.objects.filter(slug=str(category_slug or "").strip().lower()).first()
    if not category:
        raise ValueError("Category not found in database.")
    return category


def _sync_product_record_to_orm(
    product_record: Dict[str, Any],
    *,
    owner_snapshot: Dict[str, Any],
    previous_slug: str | None = None,
) -> Dict[str, Any]:
    # 這是商品 ORM 寫入主流程：先 upsert 商品主表，再重建圖片、變體與 tag 關聯。
    """Upsert one JSON-shaped product record into the ORM tables used by MySQL."""
    owner = _ensure_db_user_from_snapshot(owner_snapshot)
    brand = _get_or_create_brand_model(str(product_record.get("brand") or ""))
    category = _get_category_model_by_slug(str(product_record.get("category_slug") or ""))
    target_slug = str(product_record.get("slug") or "").strip()
    if not target_slug:
        raise ValueError("Product slug is required.")

    with transaction.atomic():
        product = None
        if previous_slug and previous_slug != target_slug:
            product = ProductModel.objects.filter(slug=previous_slug).first()
        if not product:
            product = ProductModel.objects.filter(slug=target_slug).first()
        if not product:
            product = ProductModel(slug=target_slug)

        product.slug = target_slug
        product.name = str(product_record.get("name") or "").strip()
        product.description = str(product_record.get("description") or "").strip()
        product.brand = brand
        product.category = category
        product.owner = owner
        product.price = Decimal(str(product_record.get("price") or 0)).quantize(Decimal("0.01"))
        compare_at_price = product_record.get("compare_at_price")
        product.compare_at_price = (
            Decimal(str(compare_at_price)).quantize(Decimal("0.01"))
            if compare_at_price not in (None, "")
            else None
        )
        product.stock = int(product_record.get("stock") or 0)
        product.price_compare_enabled = bool(product_record.get("price_compare_enabled", False))
        product.price_compare_query = str(product_record.get("price_compare_query") or "").strip()
        product.primary_image_index = _normalize_primary_image_index(product_record.get("primary_image_index"), list(product_record.get("images", [])))
        product.specs = dict(product_record.get("specs") or {})
        product.status = _canonical_status(product_record.get("status"))
        product.review_note = str(product_record.get("review_note") or "")
        product.owner_username_snapshot = str(product_record.get("owner_username") or owner.username)
        product.owner_display_name_snapshot = str(product_record.get("owner_display_name") or owner.display_name)
        product.save()

        ProductImageModel.objects.filter(product=product).delete()
        image_map: Dict[str, ProductImageModel] = {}
        for index, image_path in enumerate(product_record.get("images", []), start=1):
            image = ProductImageModel.objects.create(
                product=product,
                file_path=str(image_path),
                sort_order=index,
                alt_text=product.name,
                is_primary=index == (product.primary_image_index or 1),
            )
            image_map[str(image_path)] = image

        ProductVariantModel.objects.filter(product=product).delete()
        for variant_record in product_record.get("variants", []):
            image_path = str(variant_record.get("image") or "").strip()
            ProductVariantModel.objects.create(
                product=product,
                external_variant_id=str(variant_record.get("id") or variant_record.get("external_variant_id") or ""),
                name=str(variant_record.get("name") or "").strip(),
                sku=str(variant_record.get("sku") or "").strip(),
                price=Decimal(str(variant_record.get("price") or 0)).quantize(Decimal("0.01")),
                compare_at_price=(
                    Decimal(str(variant_record.get("compare_at_price"))).quantize(Decimal("0.01"))
                    if variant_record.get("compare_at_price") not in (None, "")
                    else None
                ),
                stock=int(variant_record.get("stock") or 0),
                attributes=dict(variant_record.get("attributes") or {}),
                image=image_map.get(image_path),
                image_path_snapshot=image_path,
            )

        ProductTagRelationModel.objects.filter(product=product).delete()
        for raw_tag in product_record.get("tags", []):
            tag_name = str(raw_tag or "").strip()
            if not tag_name:
                continue
            tag_slug = slugify(tag_name) or tag_name.lower().replace(" ", "-")
            tag, _ = TagModel.objects.get_or_create(slug=tag_slug, defaults={"name": tag_name})
            if tag.name != tag_name:
                tag.name = tag_name
                tag.save(update_fields=["name", "updated_at"])
            ProductTagRelationModel.objects.create(product=product, tag=tag)

    refreshed = _db_products_queryset().filter(pk=product.pk).first()
    if not refreshed:
        raise ValueError("Failed to refresh product from database.")
    return _product_record_from_model(refreshed)


def _delete_product_from_orm(slug: str) -> None:
    # 依 slug 移除 ORM 商品副本，給賣家刪除與管理端刪除流程共用。
    """Delete one ORM product row by slug if the database copy exists."""
    if not _db_products_enabled():
        return
    ProductModel.objects.filter(slug=slug).delete()


def _serialize_specs_text(specs: Any) -> str:
    # 編輯商品表單回填時，把 specs dict 還原成多行 `key:value` 文字。
    """將規格字典轉回多行 key:value 文字，供前端編輯表單使用。"""
    if not isinstance(specs, dict):
        return ""

    lines: List[str] = []
    size_aliases = {alias.lower() for alias in FILTERABLE_ATTRIBUTE_ALIASES.get("size", ("size",))}
    for key, value in specs.items():
        normalized_key = str(key).strip().lower()
        if isinstance(value, str) and normalized_key in size_aliases:
            value = ",".join(_sort_size_values(_split_filter_values(value)))
        lines.append(f"{key}:{value}")
    return "\n".join(lines)


def _sort_size_values(values: List[str]) -> List[str]:
    # 尺寸 facet 與 specs 顯示希望依 XS/S/M... 順序，而不是單純字典序。
    def size_sort_key(value: str) -> tuple[int, str]:
        normalized = str(value).strip().upper()
        return (SIZE_ORDER_INDEX.get(normalized, len(SIZE_ORDER_INDEX) + 1), normalized)

    return sorted(values, key=size_sort_key)


def _serialize_variants_text(variants: Any) -> str:
    # 編輯頁回填 variants 時，把 variant dict 陣列轉回每行 `|` 分隔文字格式。
    """將變體資料轉回多行管線分隔文字，供前端編輯表單使用。"""
    if not isinstance(variants, list):
        return ""

    lines: List[str] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        attributes = variant.get("attributes", {}) if isinstance(variant.get("attributes"), dict) else {}
        lines.append(
            "|".join(
                [
                    str(variant.get("name", "")),
                    str(variant.get("sku", "")),
                    str(variant.get("price", "")),
                    str(variant.get("stock", 0)),
                    str(attributes.get("color", "")),
                    str(attributes.get("size", "")),
                    str(variant.get("image_index", "") or ""),
                    str(variant.get("compare_at_price", "") or ""),
                ]
            )
        )
    return "\n".join(lines)


def _split_filter_values(value: Any) -> List[str]:
    # specs / variant attributes 的複數值可能用逗號或其他符號混存，這裡統一拆解。
    """Split a raw filter field into normalized display values."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        raw_parts = value
    else:
        normalized = str(value)
        for delimiter in ("、", "，", "／", "|", ";", "；"):
            normalized = normalized.replace(delimiter, "," if delimiter != "／" else "/")
        raw_parts = normalized.split(",")
    values: List[str] = []
    for part in raw_parts:
        text = str(part).strip()
        if text:
            values.append(text)
    return values


def _extract_filter_attributes(product: Dict[str, Any]) -> Dict[str, List[str]]:
    # catalog facets 會從 specs 與 variants 兩邊抽出 color / size 等可篩選屬性。
    """從 商品管理 資料中擷取後續流程需要的欄位。

    參數:
        product: 單一商品資料字典。

    回傳:
        依函式用途回傳對應資料。
    """
    attribute_map: Dict[str, set[str]] = {key: set() for key in FILTERABLE_ATTRIBUTE_KEYS}
    specs = product.get("specs", {}) if isinstance(product.get("specs"), dict) else {}
    for key in FILTERABLE_ATTRIBUTE_KEYS:
        for alias in FILTERABLE_ATTRIBUTE_ALIASES.get(key, (key,)):
            for item in _split_filter_values(specs.get(alias)):
                attribute_map[key].add(item)
    for variant in product.get("variants", []):
        attributes = variant.get("attributes", {}) if isinstance(variant.get("attributes"), dict) else {}
        for key in FILTERABLE_ATTRIBUTE_KEYS:
            for alias in FILTERABLE_ATTRIBUTE_ALIASES.get(key, (key,)):
                for item in _split_filter_values(attributes.get(alias)):
                    attribute_map[key].add(item)
    return {
        key: (_sort_size_values(list(values)) if key == "size" else sorted(values, key=str.lower))
        for key, values in attribute_map.items()
        if values
    }


# ---------------------------------------------------------------------------
# Catalog 篩選 / facets / 排序
# 這一段提供商品總覽頁與分類頁使用的篩選能力。
# ---------------------------------------------------------------------------
def build_catalog_facets(products: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    # 商品列表頁的 facets 會從目前結果集動態抽出分類、品牌、tag、顏色與尺寸選項。
    """建立商品總覽頁需要的分類 / 品牌 / tags / attribute facets。"""
    """彙整並建立 商品管理 所需的輸出資料。

    參數:
        products: 商品資料列表。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    colors: set[str] = set()
    sizes: set[str] = set()
    for product in products:
        attributes = product.get("filter_attributes", {})
        colors.update(attributes.get("color", []))
        sizes.update(attributes.get("size", []))
    return {
        "categories": [
            {
                "slug": category["slug"],
                "label": category["name"],
            }
            for category in list_active_product_categories()
        ],
        "brands": sorted({str(product.get("brand", "")) for product in products if product.get("brand")}),
        "tags": sorted({tag_item for product in products for tag_item in product.get("tags", [])}),
        "colors": sorted(colors, key=str.lower),
        "sizes": _sort_size_values(list(sizes)),
    }


def _matches_attribute_filter(product: Dict[str, Any], key: str, value: str) -> bool:
    # color / size 篩選最後都落到這個 helper，比對商品已抽出的 filter_attributes。
    """判斷 商品管理 條件是否成立。

    參數:
        product: 單一商品資料字典。
        key: 快取或字典使用的鍵值。
        value: 待格式化、待解析或待判斷的值。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    clean_value = value.strip().lower()
    if not clean_value:
        return True
    options = [item.lower() for item in product.get("filter_attributes", {}).get(key, [])]
    return clean_value in options


def filter_products(
    products: List[Dict[str, Any]],
    *,
    q: str = "",
    category: str = "",
    brand: str = "",
    tag: str = "",
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    color: str = "",
    size: str = "",
) -> List[Dict[str, Any]]:
    # catalog 查詢把關鍵字、分類、品牌、tag、價格區間與屬性條件集中套用在這裡。
    """依 catalog 篩選條件過濾商品。"""
    """依條件篩選 商品管理 資料列表。

    參數:
        products: 商品資料列表。
        q: 函式執行所需的輸入資料。
        category: 函式執行所需的輸入資料。
        brand: 函式執行所需的輸入資料。
        tag: 函式執行所需的輸入資料。
        min_price: 函式執行所需的輸入資料。
        max_price: 函式執行所需的輸入資料。
        color: 顏色屬性值。
        size: 尺寸屬性值。

    回傳:
        依函式用途回傳對應資料。
    """
    filtered = list(products)
    if q:
        filtered = [
            product
            for product in filtered
            if q in product.get("name", "").lower()
            or q in str(product.get("brand", "")).lower()
            or any(q in tag_item.lower() for tag_item in product.get("tags", []))
        ]
    if category:
        filtered = [product for product in filtered if _product_category_slug(product) == category]
    if brand:
        filtered = [product for product in filtered if str(product.get("brand", "")).lower() == brand]
    if tag:
        filtered = [product for product in filtered if tag in [item.lower() for item in product.get("tags", [])]]
    if min_price is not None:
        filtered = [product for product in filtered if Decimal(str(product.get("price", 0))) >= min_price]
    if max_price is not None:
        filtered = [product for product in filtered if Decimal(str(product.get("price", 0))) <= max_price]
    if color:
        filtered = [product for product in filtered if _matches_attribute_filter(product, "color", color)]
    if size:
        filtered = [product for product in filtered if _matches_attribute_filter(product, "size", size)]
    return filtered


def sort_products(products: List[Dict[str, Any]], sort: str) -> List[Dict[str, Any]]:
    # catalog 排序集中在這裡，前端只需傳 sort key，不用自己重排商品陣列。
    """依指定排序規則重排商品清單。"""
    """依指定規則排序 商品管理 資料。

    參數:
        products: 商品資料列表。
        sort: 函式執行所需的輸入資料。

    回傳:
        依函式用途回傳對應資料。
    """
    if sort == "price_asc":
        return sorted(products, key=lambda item: Decimal(str(item.get("price", 0))))
    if sort == "price_desc":
        return sorted(products, key=lambda item: Decimal(str(item.get("price", 0))), reverse=True)
    if sort == "name_asc":
        return sorted(products, key=lambda item: item.get("name", "").lower())
    if sort == "name_desc":
        return sorted(products, key=lambda item: item.get("name", "").lower(), reverse=True)
    if sort == "newest":
        return sorted(products, key=lambda item: item.get("id", 0), reverse=True)
    return list(products)


def get_brand_by_slug(brand_slug: str) -> str | None:
    # 品牌頁路由會先拿 brand slug，再反查目前商城實際顯示用的品牌名稱。
    """由品牌 slug 反查品牌顯示名稱。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        brand_slug: 品牌頁使用的 slug。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    for product in list_public_products():
        brand = str(product.get("brand", "")).strip()
        if brand and slugify(brand) == brand_slug:
            return brand
    return None


def get_category_by_slug(category_slug: str) -> str | None:
    # 分類頁 breadcrumb / 標題會從 slug 反查正式分類名稱。
    """由分類 slug 反查分類顯示名稱。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        category_slug: 分類頁使用的 slug。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    category = get_product_category_by_slug(category_slug, include_inactive=False)
    if category:
        return category["name"]
    return None


def get_compare_products(slugs: List[str], user: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
    # 比較頁會依 slug 清單組出仍可見且仍公開的商品 payload。
    """依 compare slugs 取回商品比較頁所需商品。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        slugs: 函式執行所需的輸入資料。
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products: List[Dict[str, Any]] = []
    for slug in slugs:
        product = get_visible_product(slug, user)
        if product and is_public_product(product):
            products.append(product)
    return products


def available_stock(product: Dict[str, Any], variant_id: str = "") -> int | None:
    # 庫存查詢同時支援商品總庫存與指定 variant 庫存，供購物車與結帳檢查共用。
    """查詢商品或指定變體目前可用庫存。"""
    """處理 商品管理 相關流程。

    參數:
        product: 單一商品資料字典。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        數值結果，供後續金額或庫存流程使用。
    """
    clean_variant_id = str(variant_id).strip()
    variants = product.get("variants") or []
    if clean_variant_id and variants:
        for variant in variants:
            variant_internal_id = str(variant.get("id") or "").strip()
            variant_external_id = str(variant.get("external_variant_id") or "").strip()
            variant_sku = str(variant.get("sku") or "").strip()
            if clean_variant_id in {variant_internal_id, variant_external_id, variant_sku}:
                try:
                    return int(variant.get("stock", 0))
                except (TypeError, ValueError):
                    return 0
        return 0
    if variants:
        return sum(int(item.get("stock", 0)) for item in variants)
    if "stock" not in product:
        return None
    if product.get("stock") in (None, ""):
        return None
    try:
        return int(product.get("stock", 0))
    except (TypeError, ValueError):
        return 0


def get_variant(product: Dict[str, Any], variant_id: str) -> Dict[str, Any] | None:
    # 商品詳情頁切換規格時，用這個 helper 取出單一 variant payload。
    """由 variant id 取回單一商品變體。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        product: 單一商品資料字典。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    clean_variant_id = str(variant_id).strip()
    for variant in product.get("variants", []):
        variant_internal_id = str(variant.get("id") or "").strip()
        variant_external_id = str(variant.get("external_variant_id") or "").strip()
        variant_sku = str(variant.get("sku") or "").strip()
        if clean_variant_id in {variant_internal_id, variant_external_id, variant_sku}:
            return dict(variant)
    return None


def _find_variant_ref(product: Dict[str, Any], variant_id: str) -> Dict[str, Any] | None:
    # reserve / restock 需要直接改動原 variant 參照，所以這裡回傳可變動的原始 dict。
    """在 商品管理 資料中尋找符合條件的項目。

    參數:
        product: 單一商品資料字典。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    clean_variant_id = str(variant_id).strip()
    for variant in product.get("variants", []):
        variant_internal_id = str(variant.get("id") or "").strip()
        variant_external_id = str(variant.get("external_variant_id") or "").strip()
        variant_sku = str(variant.get("sku") or "").strip()
        if clean_variant_id in {variant_internal_id, variant_external_id, variant_sku}:
            return variant
    return None


# ---------------------------------------------------------------------------
# 前台商品輸出整理
# 這一段會把原始商品資料整理成前端可直接使用的 display payload。
# ---------------------------------------------------------------------------
def prepare_product_for_display(product: Dict[str, Any]) -> Dict[str, Any]:
    # 這是商品對外輸出的最後整理點：補狀態標籤、折扣資訊、facet 屬性、時間顯示與預設 variant。
    """把原始商品資料整理成前台 / API 可直接輸出的 payload。"""
    """處理 商品管理 相關流程。

    參數:
        product: 單一商品資料字典。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    item = dict(product)
    item["status"] = _canonical_status(item.get("status"))
    item["status_label"] = {
        DRAFT_STATUS: "草稿",
        ACTIVE_STATUS: "上架中",
        ARCHIVED_STATUS: "已下架",
    }.get(item["status"], item["status"])
    if not item.get("owner_user_id") and item.get("owner_username"):
        owner = auth_demo.get_user_by_username(str(item["owner_username"]))
        if owner:
            item["owner_user_id"] = owner["id"]
    item["images"] = list(item.get("images", []))
    variants = [dict(variant) for variant in item.get("variants", []) if isinstance(variant, dict)]
    variants = _bind_variant_images(variants, item["images"])
    for variant in variants:
        variant_price = Decimal(str(variant.get("price", 0))).quantize(Decimal("0.01"))
        raw_variant_compare_at = variant.get("compare_at_price")
        compare_at_decimal = (
            Decimal(str(raw_variant_compare_at)).quantize(Decimal("0.01"))
            if raw_variant_compare_at not in (None, "")
            else None
        )
        variant["compare_at_price"] = float(compare_at_decimal) if compare_at_decimal is not None else None
        variant["has_discount"] = bool(compare_at_decimal and compare_at_decimal > variant_price)
        variant["discount_percent"] = (
            int(((compare_at_decimal - variant_price) / compare_at_decimal) * 100)
            if variant["has_discount"]
            else 0
        )
    item["variants"] = variants
    item["specs_text"] = _serialize_specs_text(item.get("specs", {}))
    item["variants_text"] = _serialize_variants_text(variants)
    item["has_variants"] = bool(variants)
    item["stock"] = available_stock(item)
    base_price = Decimal(str(item.get("price", 0))).quantize(Decimal("0.01"))
    compare_at = item.get("compare_at_price")
    compare_at_decimal = Decimal(str(compare_at)).quantize(Decimal("0.01")) if compare_at not in (None, "") else None
    item["compare_at_price"] = float(compare_at_decimal) if compare_at_decimal is not None else None
    item["has_discount"] = bool(compare_at_decimal and compare_at_decimal > base_price)
    item["discount_percent"] = int(((compare_at_decimal - base_price) / compare_at_decimal) * 100) if item["has_discount"] else 0
    item["default_variant"] = variants[0] if variants else None
    item["variant_count"] = len(variants)
    item["variant_price_min"] = float(min(Decimal(str(v["price"])) for v in variants)) if variants else float(base_price)
    item["variant_price_max"] = float(max(Decimal(str(v["price"])) for v in variants)) if variants else float(base_price)
    item["price_range_label"] = (
        f"${item['variant_price_min']:.2f} - ${item['variant_price_max']:.2f}"
        if variants and item["variant_price_min"] != item["variant_price_max"]
        else f"${float(base_price):.2f}"
    )
    item["stock_status"] = "out_of_stock" if item["stock"] == 0 else "low_stock" if item["stock"] is not None and item["stock"] <= 3 else "in_stock"
    if item["stock"] is None:
        item["stock_display"] = ""
    elif item["stock"] <= 0:
        item["stock_display"] = "無庫存"
    else:
        item["stock_display"] = f"{item['stock']} 件"
    item["filter_attributes"] = _extract_filter_attributes(item)
    item["color_options"] = item["filter_attributes"].get("color", [])
    item["size_options"] = item["filter_attributes"].get("size", [])
    primary_image_index = _normalize_primary_image_index(item.get("primary_image_index"), item["images"])
    item["primary_image_index"] = primary_image_index
    item["primary_image"] = item["images"][primary_image_index - 1] if primary_image_index else (item["images"][0] if item["images"] else "")
    item["shipping_profile"] = _normalize_shipping_profile(item.get("shipping_profile"))
    item["price_compare_enabled"] = bool(item.get("price_compare_enabled", False))
    item["price_compare_query"] = str(item.get("price_compare_query") or "").strip()
    item["brand_slug"] = slugify(str(item.get("brand", "")))
    item["category"] = _product_category_label(item)
    item["category_label"] = item["category"]
    item["category_slug"] = _product_category_slug(item)
    created_at_value = str(item.get("created_at") or "")
    updated_at_value = str(item.get("updated_at") or "")
    created_at = parse_datetime(created_at_value) if created_at_value else None
    updated_at = parse_datetime(updated_at_value) if updated_at_value else None
    item["created_at_display"] = timezone.localtime(created_at).strftime("%Y-%m-%d %H:%M") if created_at else ""
    item["updated_at_display"] = timezone.localtime(updated_at).strftime("%Y-%m-%d %H:%M") if updated_at else ""
    return item


def get_status_choices(user: Dict[str, str]) -> List[Dict[str, str]]:
    # 商品編輯表單的狀態下拉選項依角色縮放，避免賣家看到不該直接設的狀態。
    """依角色回傳商品狀態選單。"""
    """取得 商品管理 流程中指定條件的資料。

    參數:
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    return [
        {"value": DRAFT_STATUS, "label": "草稿"},
        {"value": ACTIVE_STATUS, "label": "直接上架"},
    ]


# ---------------------------------------------------------------------------
# 賣家 / 管理端商品寫入
# 這一段是真正的 create / update / archive / delete / duplicate / review 流程。
# ---------------------------------------------------------------------------
def create_product(owner: Dict[str, str], form_data: Dict[str, str], uploaded_files: Iterable[UploadedFile] = ()) -> Dict[str, Any]:
    # 建立商品主流程：清理表單、處理圖片與 variants、組 canonical payload，再寫入資料源。
    """建立新商品。"""
    """建立新商品並處理圖片、變體與狀態欄位。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        form_data: 從表單或 API 送入的原始欄位資料。
        uploaded_files: 使用者上傳的圖片檔案集合。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    now = timezone.now().isoformat()
    name = form_data.get("name", "").strip()
    brand = form_data.get("brand", "").strip()
    category = _require_product_category(form_data.get("category", ""))
    if not name:
        raise ValueError("Product name is required.")
    if not brand:
        raise ValueError("Brand is required.")

    slug = _generate_unique_slug(name, _all_product_records_for_slug_generation())
    status = _normalize_status(form_data.get("status", DRAFT_STATUS), owner)
    price = _parse_price(form_data.get("price", ""))
    compare_at_price = _parse_optional_price(form_data.get("compare_at_price", ""))
    base_compare_at_price = _serialize_compare_at_price(compare_at_price, price)
    variants = _normalize_variants(form_data.get("variants", ""))
    if variants:
        summary = _summarize_variant_pricing(variants)
        price = Decimal(str(summary["price"]))
        stock = summary["stock"]
    else:
        stock = _parse_stock(form_data.get("stock", "0"))

    images = _save_uploaded_images(slug, uploaded_files)
    primary_image_index = _normalize_primary_image_index(form_data.get("primary_image_index", ""), images)
    variants = _bind_variant_images(variants, images)

    product = {
        "id": (
            (ProductModel.objects.order_by("-id").only("id").first().id + 1)
            if ProductModel.objects.exists()
            else 1
        ),
        "slug": slug,
        "name": name,
        "price": float(price),
        "compare_at_price": base_compare_at_price,
        "brand": brand,
        "category": category["name"],
        "category_slug": category["slug"],
        "tags": _normalize_tags(form_data.get("tags", "")),
        "images": images,
        "primary_image_index": primary_image_index,
        "specs": _normalize_specs(form_data.get("specs", "")),
        "stock": stock,
        "price_compare_enabled": False,
        "price_compare_query": "",
        "variants": variants,
        "shipping_profile": _build_shipping_profile_from_form(form_data),
        "owner_user_id": owner["id"],
        "owner_username": owner["username"],
        "owner_display_name": owner["display_name"],
        "status": status,
        "review_note": "",
        "created_at": now,
        "updated_at": now,
    }
    return prepare_product_for_display(_persist_product_record(product))


def update_product(owner: Dict[str, str], slug: str, form_data: Dict[str, str], uploaded_files: Iterable[UploadedFile] = ()) -> Dict[str, Any]:
    # 賣家更新商品時，保留 owner 限制，並處理改名、換圖、variants 重整與狀態更新。
    """由賣家更新自己的商品。"""
    """更新既有商品資料，並同步處理圖片與變體調整。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。
        form_data: 從表單或 API 送入的原始欄位資料。
        uploaded_files: 使用者上傳的圖片檔案集合。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    item = get_user_product(owner["username"], slug)
    if not item:
        raise ValueError("Product not found.")

    previous_slug = str(item.get("slug") or "")
    name = form_data.get("name", "").strip()
    brand = form_data.get("brand", "").strip()
    category = _require_product_category(form_data.get("category", ""))
    if not name:
        raise ValueError("Product name is required.")
    if not brand:
        raise ValueError("Brand is required.")
    next_slug = _generate_unique_slug(name, _all_product_records_for_slug_generation(), current_slug=item.get("slug"))
    price = _parse_price(form_data.get("price", ""))
    compare_at_price = _parse_optional_price(form_data.get("compare_at_price", ""))
    base_compare_at_price = _serialize_compare_at_price(compare_at_price, price)
    variants = _normalize_variants(form_data.get("variants", ""))
    if variants:
        summary = _summarize_variant_pricing(variants)
        price = Decimal(str(summary["price"]))
        stock = summary["stock"]
    else:
        stock = _parse_stock(form_data.get("stock", "0"))

    item["name"] = name
    item["slug"] = next_slug
    item["price"] = float(price)
    item["compare_at_price"] = base_compare_at_price
    item["brand"] = brand
    item["category"] = category["name"]
    item["category_slug"] = category["slug"]
    item["tags"] = _normalize_tags(form_data.get("tags", ""))
    item["specs"] = _normalize_specs(form_data.get("specs", ""))
    item["stock"] = stock
    item["price_compare_enabled"] = bool(item.get("price_compare_enabled", False))
    item["price_compare_query"] = str(item.get("price_compare_query") or "").strip()
    item["variants"] = variants
    item["shipping_profile"] = _build_shipping_profile_from_form(form_data, item.get("shipping_profile"))
    item["status"] = _normalize_status(form_data.get("status", item.get("status", DRAFT_STATUS)), owner, item.get("status"))
    item["images"] = _merge_image_changes(item, form_data, uploaded_files, next_slug)
    item["primary_image_index"] = _normalize_primary_image_index(form_data.get("primary_image_index", ""), item["images"])
    item["variants"] = _bind_variant_images(variants, item["images"])
    item["updated_at"] = timezone.now().isoformat()
    return prepare_product_for_display(_persist_product_record(item, previous_slug=previous_slug))


def admin_update_product(
    user: Dict[str, str],
    slug: str,
    form_data: Dict[str, str],
    uploaded_files: Iterable[UploadedFile] = (),
) -> Dict[str, Any]:
    # 管理端更新商品和賣家編輯類似，但不受 owner 限制，且可設定更完整的狀態集合。
    """由管理端更新指定商品。"""
    existing = _merged_product_record_by_slug(slug)
    if not existing:
        raise ValueError("Product not found.")
    item = deepcopy(existing)
    previous_slug = str(item.get("slug") or "")
    name = form_data.get("name", "").strip()
    brand = form_data.get("brand", "").strip()
    category = _require_product_category(form_data.get("category", ""))
    if not name:
        raise ValueError("Product name is required.")
    if not brand:
        raise ValueError("Brand is required.")
    next_slug = _generate_unique_slug(name, _all_product_records_for_slug_generation(), current_slug=item.get("slug"))
    price = _parse_price(form_data.get("price", ""))
    compare_at_price = _parse_optional_price(form_data.get("compare_at_price", ""))
    base_compare_at_price = _serialize_compare_at_price(compare_at_price, price)
    variants = _normalize_variants(form_data.get("variants", ""))
    if variants:
        summary = _summarize_variant_pricing(variants)
        price = Decimal(str(summary["price"]))
        stock = summary["stock"]
    else:
        stock = _parse_stock(form_data.get("stock", "0"))

    item["name"] = name
    item["slug"] = next_slug
    item["price"] = float(price)
    item["compare_at_price"] = base_compare_at_price
    item["brand"] = brand
    item["category"] = category["name"]
    item["category_slug"] = category["slug"]
    item["tags"] = _normalize_tags(form_data.get("tags", ""))
    item["specs"] = _normalize_specs(form_data.get("specs", ""))
    item["stock"] = stock
    item["price_compare_enabled"] = bool(item.get("price_compare_enabled", False))
    item["price_compare_query"] = str(item.get("price_compare_query") or "").strip()
    item["variants"] = variants
    item["shipping_profile"] = _build_shipping_profile_from_form(form_data, item.get("shipping_profile"))
    item["status"] = _normalize_status(
        form_data.get("status", item.get("status", DRAFT_STATUS)),
        user,
        item.get("status"),
    )
    item["images"] = _merge_image_changes(item, form_data, uploaded_files, next_slug)
    item["variants"] = _bind_variant_images(variants, item["images"])
    item["updated_at"] = timezone.now().isoformat()
    return _persist_product_record(item, previous_slug=previous_slug)


def admin_update_price_compare_settings(slug: str, *, enabled: bool, query: str = "") -> Dict[str, Any]:
    # 管理端可單獨調整比價開關與搜尋關鍵字，不必重送整份商品編輯表單。
    item = _merged_product_record_by_slug(slug)
    if not item:
        raise ValueError("Product not found.")

    item["price_compare_enabled"] = bool(enabled)
    item["price_compare_query"] = str(query or "").strip()
    item["updated_at"] = timezone.now().isoformat()
    return _persist_product_record(item, previous_slug=slug)


def archive_product(owner: Dict[str, str], slug: str) -> Dict[str, Any]:
    # 賣家主動下架商品時，只改狀態與時間，不刪除資料本體。
    """由賣家將商品封存 / 下架。"""
    """將商品封存，使其不再公開顯示。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    item = get_user_product(owner["username"], slug)
    if not item:
        raise ValueError("Product not found.")
    item["status"] = ARCHIVED_STATUS
    item["updated_at"] = timezone.now().isoformat()
    return prepare_product_for_display(_persist_product_record(item, previous_slug=slug))


def delete_product(owner: Dict[str, str], slug: str) -> None:
    # 賣家刪除商品時，除了移除資料，也會清掉對應商品圖片檔案。
    """由賣家刪除自己的商品。"""
    """永久刪除商品與相關圖片資料。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    existing = get_user_product(owner["username"], slug)
    if not existing:
        raise ValueError("Product not found.")
    for image in existing.get("images", []):
        _delete_product_image(image)
    _delete_product_from_orm(slug)


def admin_delete_product(slug: str) -> None:
    # 管理端可不經 owner 驗證直接刪除商品，刪除前同樣先清圖片檔。
    """由管理端直接刪除商品。"""
    fallback = _merged_product_record_by_slug(slug)
    if not fallback:
        raise ValueError("Product not found.")
    for image in fallback.get("images", []):
        _delete_product_image(image)
    _delete_product_from_orm(slug)


def duplicate_product_as_draft(owner: Dict[str, str], slug: str) -> Dict[str, Any]:
    # 複製商品會重產 slug、切成 draft，讓賣家能以現有商品快速開新稿。
    """以既有商品複製出新的草稿商品。"""
    """複製既有商品為新的草稿商品，方便賣家快速延伸上架。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    source = get_user_product(owner["username"], slug)
    if not source:
        raise ValueError("Product not found.")

    now = timezone.now().isoformat()
    latest = ProductModel.objects.order_by("-id").only("id").first()
    source["id"] = latest.id + 1 if latest else 1
    source["slug"] = _generate_unique_slug(f"{source['name']} copy", _all_product_records_for_slug_generation())
    source["name"] = f"{source['name']} Copy"
    source["status"] = DRAFT_STATUS
    source["review_note"] = ""
    source["created_at"] = now
    source["updated_at"] = now
    return prepare_product_for_display(_persist_product_record(source))


def review_product(slug: str, approved: bool, note: str = "") -> Dict[str, Any]:
    # 商品審核入口：通過就上架，否則轉 archived，並記錄 review note 與 reviewed_at。
    """審核待審商品並決定核准或退回。"""
    """審核商品是否可以上架公開。

    參數:
        slug: 商品或頁面使用的網址識別字串。
        approved: 是否核准此次審核或申請。
        note: 補充說明、審核備註或操作備註。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    item = _merged_product_record_by_slug(slug)
    if not item:
        raise ValueError("Product not found.")
    item["status"] = ACTIVE_STATUS if approved else ARCHIVED_STATUS
    _serialize_review_fields(item, note)
    item["updated_at"] = timezone.now().isoformat()
    return _persist_product_record(item, previous_slug=slug)


def admin_archive_product(slug: str, note: str = "") -> Dict[str, Any]:
    # 管理端可強制下架商品，並留下管理說明供賣家回看。
    """由管理端強制下架商品。"""
    item = _merged_product_record_by_slug(slug)
    if not item:
        raise ValueError("Product not found.")
    item["status"] = ARCHIVED_STATUS
    _serialize_review_fields(item, note or "Forced down by admin.")
    item["updated_at"] = timezone.now().isoformat()
    return _persist_product_record(item, previous_slug=slug)


def admin_publish_product(slug: str, note: str = "") -> Dict[str, Any]:
    # 管理端可直接強制上架商品，仍會保留 review note 與 reviewed_at。
    """由管理端強制上架商品。"""
    item = _merged_product_record_by_slug(slug)
    if not item:
        raise ValueError("Product not found.")
    item["status"] = ACTIVE_STATUS
    _serialize_review_fields(item, note or "Published by admin.")
    item["updated_at"] = timezone.now().isoformat()
    return _persist_product_record(item, previous_slug=slug)


def _resolve_inventory_target(product: Dict[str, Any], line: Dict[str, Any]) -> tuple[str, Dict[str, Any] | None, int | None]:
    # 訂單行可能指定 variant，也可能只有商品本體；這裡統一解析出要扣哪一格庫存。
    """處理 商品管理 相關流程。

    參數:
        product: 單一商品資料字典。
        line: 單一訂單行或購物車行資料。

    回傳:
        依函式用途回傳對應資料。
    """
    variant_id = str(line.get("variant_id", "")).strip()
    if variant_id:
        variant = _find_variant_ref(product, variant_id)
        stock = available_stock(product, variant_id)
        return variant_id, variant, stock
    return "", None, available_stock(product)


# ---------------------------------------------------------------------------
# 庫存異動
# 這一段由結帳 / 售後流程呼叫，用於預留庫存與取消時回補。
# ---------------------------------------------------------------------------
def reserve_stock(items: List[Dict[str, Any]]) -> None:
    # 建單時先檢查所有商品庫存是否足夠，再一次性扣減，避免半途扣了一半就失敗。
    """在建單時預留商品 / 變體庫存。"""
    """在成立訂單時預扣商品或變體庫存。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    indexed = {str(line.get("slug") or ""): _merged_product_record_by_slug(str(line.get("slug") or "")) for line in items}

    for line in items:
        product = indexed.get(line["slug"])
        if not product or not is_public_product(product):
            raise ValueError(f"Product {line['name']} is no longer available.")
        _, variant, stock = _resolve_inventory_target(product, line)
        if line.get("variant_id") and not variant:
            raise ValueError(f"Selected variant is no longer available for {product['name']}.")
        if stock is None:
            continue
        if int(line["qty"]) > stock:
            label = variant["name"] if variant else product["name"]
            raise ValueError(f"Only {stock} units left for {label}.")

    for line in items:
        product = indexed.get(line["slug"])
        variant_id, variant, stock = _resolve_inventory_target(product, line)
        if stock is None:
            continue
        if variant_id and variant:
            variant["stock"] = stock - int(line["qty"])
            product["stock"] = available_stock(product)
        else:
            product["stock"] = stock - int(line["qty"])

    for product in indexed.values():
        if product:
            _persist_product_record(product, previous_slug=str(product.get("slug") or ""))


def restock_items(items: List[Dict[str, Any]]) -> None:
    # 訂單取消或退款回補庫存時，沿用和 reserve 同樣的 target 解析規則做反向加回。
    """在取消訂單或退款時回補商品 / 變體庫存。"""
    """在取消或退款核准後回補商品庫存。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    indexed = {str(line.get("slug") or ""): _merged_product_record_by_slug(str(line.get("slug") or "")) for line in items}
    for line in items:
        product = indexed.get(line.get("slug"))
        if not product:
            continue
        variant_id, variant, stock = _resolve_inventory_target(product, line)
        if stock is None:
            continue
        if variant_id and variant:
            variant["stock"] = stock + int(line.get("qty", 0))
            product["stock"] = available_stock(product)
        else:
            product["stock"] = stock + int(line.get("qty", 0))
    for product in indexed.values():
        if product:
            _persist_product_record(product, previous_slug=str(product.get("slug") or ""))

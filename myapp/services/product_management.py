"""商品與賣家上架管理服務模組。

負責商品建立、編輯、審核、變體、圖片與庫存等核心商業邏輯。
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from ..repositories import local_store
from . import auth_demo

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


def is_public_product(product: Dict[str, Any]) -> bool:
    """判斷 商品管理 條件是否成立。

    參數:
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return _canonical_status(product.get("status")) in PUBLIC_STATUSES


def can_manage_product(user: Dict[str, str] | None, product: Dict[str, Any]) -> bool:
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return bool(user and product.get("owner_username") == user["username"])


def can_review_product(user: Dict[str, str] | None) -> bool:
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return auth_demo.is_admin(user)


def can_sell(user: Dict[str, str] | None) -> bool:
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return auth_demo.is_seller(user)


def can_view_product(user: Dict[str, str] | None, product: Dict[str, Any]) -> bool:
    """判斷 商品管理 條件是否成立。

    參數:
        user: 目前操作中的會員快照資料。
        product: 單一商品資料字典。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return is_public_product(product) or can_manage_product(user, product) or can_review_product(user)


def list_public_products() -> List[Dict[str, Any]]:
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    return [prepare_product_for_display(product) for product in local_store.get_products() if is_public_product(product)]


def list_products_for_user(username: str) -> List[Dict[str, Any]]:
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    products = [product for product in local_store.get_products() if product.get("owner_username") == username]
    ordered = sorted(products, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return [prepare_product_for_display(product) for product in ordered]


def list_pending_products() -> List[Dict[str, Any]]:
    """列出 商品管理 相關資料，供頁面或 API 顯示。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    products = [product for product in local_store.get_products() if _canonical_status(product.get("status")) == PENDING_STATUS]
    ordered = sorted(products, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return [prepare_product_for_display(product) for product in ordered]


def list_moderation_products() -> List[Dict[str, Any]]:
    """列出目前已上架的商品，供管理者進行強制下架。"""
    products = [product for product in local_store.get_products() if _canonical_status(product.get("status")) == ACTIVE_STATUS]
    ordered = sorted(products, key=lambda item: item.get("updated_at", item.get("created_at", "")), reverse=True)
    return [prepare_product_for_display(product) for product in ordered]


def list_products_for_admin() -> List[Dict[str, Any]]:
    """Return every product for admin management."""
    products = sorted(
        local_store.get_products(),
        key=lambda item: item.get("updated_at", item.get("created_at", "")),
        reverse=True,
    )
    return [prepare_product_for_display(product) for product in products]


def get_user_product(username: str, slug: str) -> Dict[str, Any] | None:
    """取得 商品管理 流程中指定條件的資料。

    參數:
        username: 會員帳號，通常也是 JSON 資料中的唯一識別鍵。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    for product in local_store.get_products():
        if product.get("owner_username") == username and product.get("slug") == slug:
            return prepare_product_for_display(product)
    return None


def get_visible_product(slug: str, user: Dict[str, str] | None = None) -> Dict[str, Any] | None:
    """取得 商品管理 流程中指定條件的資料。

    參數:
        slug: 商品或頁面使用的網址識別字串。
        user: 目前操作中的會員快照資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    product = local_store.get_product_by_slug(slug)
    if not product or not can_view_product(user, product):
        return None
    return prepare_product_for_display(product)


def get_product_for_admin(slug: str) -> Dict[str, Any] | None:
    """Return any product record for admin management."""
    product = local_store.get_product_by_slug(slug)
    return prepare_product_for_display(product) if product else None


def get_product_for_review(slug: str) -> Dict[str, Any] | None:
    """取得 商品管理 流程中指定條件的資料。

    參數:
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    product = local_store.get_product_by_slug(slug)
    return prepare_product_for_display(product) if product else None


def _next_product_id(products: List[Dict[str, Any]]) -> int:
    """處理 商品管理 相關流程。

    參數:
        products: 商品資料列表。

    回傳:
        數值結果，供後續金額或庫存流程使用。
    """
    return max([int(item.get("id", 0)) for item in products] or [0]) + 1


def _normalize_tags(raw_tags: str) -> List[str]:
    """正規化輸入資料，降低 商品管理 流程中的格式差異。

    參數:
        raw_tags: 表單輸入的標籤原始字串。

    回傳:
        依函式用途回傳對應資料。
    """
    return [item.strip() for item in raw_tags.split(",") if item.strip()]


def _normalize_specs(raw_specs: str) -> Dict[str, str]:
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


def _parse_bool_flag(raw_value: Any, default: bool = False) -> bool:
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
    """Return a JSON-friendly float for optional Decimal values."""
    return float(value) if value is not None else None


def _normalize_shipping_profile(raw_profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
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
    """處理 商品管理 相關流程。

    回傳:
        依函式用途回傳對應資料。
    """
    return Path(settings.BASE_DIR) / "static" / "uploads" / "products"


def _save_uploaded_images(product_slug: str, uploaded_files: Iterable[UploadedFile]) -> List[str]:
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
        target_path = upload_dir / file_name
        with target_path.open("wb") as output:
            for chunk in uploaded_file.chunks():
                output.write(chunk)
        saved_paths.append(f"/static/uploads/products/{file_name}")
    return saved_paths


def _serialize_review_fields(product: Dict[str, Any], note: str = "") -> None:
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
    """處理 商品管理 相關流程。

    參數:
        image_path: 單一圖片在媒體目錄中的相對路徑。

    回傳:
        依函式用途回傳對應資料。
    """
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


def _serialize_specs_text(specs: Any) -> str:
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
    def size_sort_key(value: str) -> tuple[int, str]:
        normalized = str(value).strip().upper()
        return (SIZE_ORDER_INDEX.get(normalized, len(SIZE_ORDER_INDEX) + 1), normalized)

    return sorted(values, key=size_sort_key)


def _serialize_variants_text(variants: Any) -> str:
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
    """Split a raw filter field into normalized display values."""
    if value in (None, ""):
        return []
    if isinstance(value, list):
        raw_parts = value
    else:
        normalized = str(value).replace("?", ",").replace("?", ",").replace("?", "/")
        raw_parts = normalized.split(",")
    values: List[str] = []
    for part in raw_parts:
        text = str(part).strip()
        if text:
            values.append(text)
    return values


def _extract_filter_attributes(product: Dict[str, Any]) -> Dict[str, List[str]]:
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


def build_catalog_facets(products: List[Dict[str, Any]]) -> Dict[str, List[str]]:
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
        "categories": sorted({str(product.get("category", "")).lower() for product in products if product.get("category")}),
        "brands": sorted({str(product.get("brand", "")) for product in products if product.get("brand")}),
        "tags": sorted({tag_item for product in products for tag_item in product.get("tags", [])}),
        "colors": sorted(colors, key=str.lower),
        "sizes": _sort_size_values(list(sizes)),
    }


def _matches_attribute_filter(product: Dict[str, Any], key: str, value: str) -> bool:
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
        filtered = [product for product in filtered if str(product.get("category", "")).lower() == category]
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
    """取得 商品管理 流程中指定條件的資料。

    參數:
        category_slug: 分類頁使用的 slug。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    for product in list_public_products():
        category = str(product.get("category", "")).strip().lower()
        if category and slugify(category) == category_slug:
            return category
    return None


def get_compare_products(slugs: List[str], user: Dict[str, str] | None = None) -> List[Dict[str, Any]]:
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
            if variant.get("id") == clean_variant_id:
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
    """取得 商品管理 流程中指定條件的資料。

    參數:
        product: 單一商品資料字典。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    for variant in product.get("variants", []):
        if variant.get("id") == variant_id:
            return dict(variant)
    return None


def _find_variant_ref(product: Dict[str, Any], variant_id: str) -> Dict[str, Any] | None:
    """在 商品管理 資料中尋找符合條件的項目。

    參數:
        product: 單一商品資料字典。
        variant_id: 指定變體的唯一識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    for variant in product.get("variants", []):
        if variant.get("id") == variant_id:
            return variant
    return None


def prepare_product_for_display(product: Dict[str, Any]) -> Dict[str, Any]:
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
        owner = local_store.get_user_by_username(str(item["owner_username"]))
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
    item["primary_image"] = item["images"][0] if item["images"] else ""
    item["shipping_profile"] = _normalize_shipping_profile(item.get("shipping_profile"))
    item["brand_slug"] = slugify(str(item.get("brand", "")))
    item["category_slug"] = slugify(str(item.get("category", "")))
    created_at_value = str(item.get("created_at") or "")
    updated_at_value = str(item.get("updated_at") or "")
    created_at = parse_datetime(created_at_value) if created_at_value else None
    updated_at = parse_datetime(updated_at_value) if updated_at_value else None
    item["created_at_display"] = timezone.localtime(created_at).strftime("%Y-%m-%d %H:%M") if created_at else ""
    item["updated_at_display"] = timezone.localtime(updated_at).strftime("%Y-%m-%d %H:%M") if updated_at else ""
    return item


def get_status_choices(user: Dict[str, str]) -> List[Dict[str, str]]:
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


def create_product(owner: Dict[str, str], form_data: Dict[str, str], uploaded_files: Iterable[UploadedFile] = ()) -> Dict[str, Any]:
    """建立新商品並處理圖片、變體與狀態欄位。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        form_data: 從表單或 API 送入的原始欄位資料。
        uploaded_files: 使用者上傳的圖片檔案集合。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products = deepcopy(local_store.get_products())
    now = timezone.now().isoformat()
    name = form_data.get("name", "").strip()
    brand = form_data.get("brand", "").strip()
    category = form_data.get("category", "").strip().lower()
    if not name:
        raise ValueError("Product name is required.")
    if not brand:
        raise ValueError("Brand is required.")
    if not category:
        raise ValueError("Category is required.")

    slug = _generate_unique_slug(name, products)
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
    variants = _bind_variant_images(variants, images)

    product = {
        "id": _next_product_id(products),
        "slug": slug,
        "name": name,
        "price": float(price),
        "compare_at_price": base_compare_at_price,
        "brand": brand,
        "category": category,
        "tags": _normalize_tags(form_data.get("tags", "")),
        "images": images,
        "specs": _normalize_specs(form_data.get("specs", "")),
        "stock": stock,
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
    products.append(product)
    local_store.save_products(products)
    return prepare_product_for_display(product)


def update_product(owner: Dict[str, str], slug: str, form_data: Dict[str, str], uploaded_files: Iterable[UploadedFile] = ()) -> Dict[str, Any]:
    """更新既有商品資料，並同步處理圖片與變體調整。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。
        form_data: 從表單或 API 送入的原始欄位資料。
        uploaded_files: 使用者上傳的圖片檔案集合。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug or item.get("owner_username") != owner["username"]:
            continue
        name = form_data.get("name", "").strip()
        brand = form_data.get("brand", "").strip()
        category = form_data.get("category", "").strip().lower()
        if not name:
            raise ValueError("Product name is required.")
        if not brand:
            raise ValueError("Brand is required.")
        if not category:
            raise ValueError("Category is required.")

        next_slug = _generate_unique_slug(name, products, current_slug=item.get("slug"))
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
        item["category"] = category
        item["tags"] = _normalize_tags(form_data.get("tags", ""))
        item["specs"] = _normalize_specs(form_data.get("specs", ""))
        item["stock"] = stock
        item["variants"] = variants
        item["shipping_profile"] = _build_shipping_profile_from_form(form_data, item.get("shipping_profile"))
        item["status"] = _normalize_status(form_data.get("status", item.get("status", DRAFT_STATUS)), owner, item.get("status"))
        item["images"] = _merge_image_changes(item, form_data, uploaded_files, next_slug)
        item["variants"] = _bind_variant_images(variants, item["images"])
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def admin_update_product(
    user: Dict[str, str],
    slug: str,
    form_data: Dict[str, str],
    uploaded_files: Iterable[UploadedFile] = (),
) -> Dict[str, Any]:
    """Update any product as an admin."""
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug:
            continue
        name = form_data.get("name", "").strip()
        brand = form_data.get("brand", "").strip()
        category = form_data.get("category", "").strip().lower()
        if not name:
            raise ValueError("Product name is required.")
        if not brand:
            raise ValueError("Brand is required.")
        if not category:
            raise ValueError("Category is required.")

        next_slug = _generate_unique_slug(name, products, current_slug=item.get("slug"))
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
        item["category"] = category
        item["tags"] = _normalize_tags(form_data.get("tags", ""))
        item["specs"] = _normalize_specs(form_data.get("specs", ""))
        item["stock"] = stock
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
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def archive_product(owner: Dict[str, str], slug: str) -> Dict[str, Any]:
    """將商品封存，使其不再公開顯示。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug or item.get("owner_username") != owner["username"]:
            continue
        item["status"] = ARCHIVED_STATUS
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def delete_product(owner: Dict[str, str], slug: str) -> None:
    """永久刪除商品與相關圖片資料。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    products = deepcopy(local_store.get_products())
    next_products = []
    deleted = False
    for item in products:
        if item.get("slug") == slug and item.get("owner_username") == owner["username"]:
            deleted = True
            for image in item.get("images", []):
                _delete_product_image(image)
            continue
        next_products.append(item)
    if not deleted:
        raise ValueError("Product not found.")
    local_store.save_products(next_products)


def admin_delete_product(slug: str) -> None:
    """Delete any product as an admin."""
    products = deepcopy(local_store.get_products())
    next_products = []
    deleted = False
    for item in products:
        if item.get("slug") == slug:
            deleted = True
            for image in item.get("images", []):
                _delete_product_image(image)
            continue
        next_products.append(item)
    if not deleted:
        raise ValueError("Product not found.")
    local_store.save_products(next_products)


def duplicate_product_as_draft(owner: Dict[str, str], slug: str) -> Dict[str, Any]:
    """複製既有商品為新的草稿商品，方便賣家快速延伸上架。

    參數:
        owner: 賣家或商品擁有者資料，用來驗證是否有管理權限。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        依函式用途回傳對應資料。
    """
    products = deepcopy(local_store.get_products())
    source = None
    for item in products:
        if item.get("slug") == slug and item.get("owner_username") == owner["username"]:
            source = deepcopy(item)
            break
    if not source:
        raise ValueError("Product not found.")

    now = timezone.now().isoformat()
    source["id"] = _next_product_id(products)
    source["slug"] = _generate_unique_slug(f"{source['name']} copy", products)
    source["name"] = f"{source['name']} Copy"
    source["status"] = DRAFT_STATUS
    source["review_note"] = ""
    source["created_at"] = now
    source["updated_at"] = now
    products.append(source)
    local_store.save_products(products)
    return prepare_product_for_display(source)


def review_product(slug: str, approved: bool, note: str = "") -> Dict[str, Any]:
    """審核商品是否可以上架公開。

    參數:
        slug: 商品或頁面使用的網址識別字串。
        approved: 是否核准此次審核或申請。
        note: 補充說明、審核備註或操作備註。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug:
            continue
        item["status"] = ACTIVE_STATUS if approved else ARCHIVED_STATUS
        _serialize_review_fields(item, note)
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def admin_archive_product(slug: str, note: str = "") -> Dict[str, Any]:
    """提供管理者強制下架商品。"""
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug:
            continue
        item["status"] = ARCHIVED_STATUS
        _serialize_review_fields(item, note or "Forced down by admin.")
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def admin_publish_product(slug: str, note: str = "") -> Dict[str, Any]:
    """Force publish a product as active."""
    products = deepcopy(local_store.get_products())
    for item in products:
        if item.get("slug") != slug:
            continue
        item["status"] = ACTIVE_STATUS
        _serialize_review_fields(item, note or "Published by admin.")
        item["updated_at"] = timezone.now().isoformat()
        local_store.save_products(products)
        return prepare_product_for_display(item)
    raise ValueError("Product not found.")


def _resolve_inventory_target(product: Dict[str, Any], line: Dict[str, Any]) -> tuple[str, Dict[str, Any] | None, int | None]:
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


def reserve_stock(items: List[Dict[str, Any]]) -> None:
    """在成立訂單時預扣商品或變體庫存。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    products = deepcopy(local_store.get_products())
    indexed = {item.get("slug"): item for item in products}

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

    local_store.save_products(products)


def restock_items(items: List[Dict[str, Any]]) -> None:
    """在取消或退款核准後回補商品庫存。

    參數:
        items: 訂單或購物車中的品項列表。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    products = deepcopy(local_store.get_products())
    indexed = {item.get("slug"): item for item in products}
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
    local_store.save_products(products)

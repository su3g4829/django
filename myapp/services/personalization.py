"""收藏、最近瀏覽與商品比較 service。

這層同時支援兩種資料來源：
- 訪客：資料放在 session bucket
- 已登入會員：優先同步到 ORM / MySQL，再把結果回寫到 session

目標是讓收藏、最近瀏覽、比較清單三種功能都維持一致的 payload 與操作方式。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from ..models import AppUser as AppUserModel
from ..models import CompareItem as CompareItemModel
from ..models import Product as ProductModel
from ..models import RecentView as RecentViewModel
from ..models import UserFavorite as UserFavoriteModel
from ..repositories import local_store

FAVORITES_KEY = "favorite_products"
RECENT_VIEWS_KEY = "recent_products"
COMPARE_PRODUCTS_KEY = "compare_products"
SESSION_USER_KEY = "demo_user"
GUEST_BUCKET_KEY = "__guest__"
MAX_RECENT_VIEWS = 8
MAX_COMPARE_PRODUCTS = 4


def _session_username(session) -> str:
    # session 內目前登入者統一掛在 `demo_user`，這裡抽出標準化 username。
    user = session.get(SESSION_USER_KEY)
    if isinstance(user, dict):
        username = str(user.get("username", "")).strip().lower()
        if username:
            return username
    return ""


def _session_bucket_name(session) -> str:
    # 未登入使用 guest bucket，登入後則按 username 分桶，避免多帳號共用同一份 session 清單。
    username = _session_username(session)
    return username or GUEST_BUCKET_KEY


def _ensure_bucket(session, key: str) -> List[str]:
    # 確保 session 裡某個 personalization bucket 一定存在，而且格式是 `{bucket_name: [slug...]}`。
    bucket_name = _session_bucket_name(session)
    raw = session.get(key)

    if isinstance(raw, list):
        raw = {GUEST_BUCKET_KEY: list(raw)}
        session[key] = raw
        session.modified = True
    elif not isinstance(raw, dict):
        raw = {}
        session[key] = raw
        session.modified = True

    bucket = raw.get(bucket_name)
    if not isinstance(bucket, list):
        bucket = []
        raw[bucket_name] = bucket
        session[key] = raw
        session.modified = True

    return bucket


def _replace_bucket(session, key: str, values: List[str], *, bucket_name: str | None = None) -> None:
    # 用新的 slug 清單完整覆蓋指定 bucket，讓 ORM 與 session 能重新同步到同一狀態。
    target_bucket = bucket_name or _session_bucket_name(session)
    raw = session.get(key)

    if isinstance(raw, list):
        raw = {GUEST_BUCKET_KEY: list(raw)}
    elif not isinstance(raw, dict):
        raw = {}

    raw[target_bucket] = list(values)
    session[key] = raw
    session.modified = True


def clear_guest_buckets(session) -> None:
    # 使用者登入並完成 guest 資料合併後，清空 guest bucket，避免之後再次重複併入。
    for key in (FAVORITES_KEY, RECENT_VIEWS_KEY, COMPARE_PRODUCTS_KEY):
        raw = session.get(key)
        if isinstance(raw, list):
            raw = {GUEST_BUCKET_KEY: []}
        elif isinstance(raw, dict):
            raw = dict(raw)
            raw[GUEST_BUCKET_KEY] = []
        else:
            raw = {GUEST_BUCKET_KEY: []}
        session[key] = raw
    session.modified = True


def _merge_slug_lists(primary: List[str], secondary: List[str], *, max_items: int | None = None) -> List[str]:
    # 合併兩份 slug 清單並去重，順序以 primary 優先，必要時再套用長度上限。
    merged: List[str] = []
    for slug in [*primary, *secondary]:
        clean = str(slug or "").strip()
        if clean and clean not in merged:
            merged.append(clean)
    if max_items is not None:
        return merged[:max_items]
    return merged


def _db_personalization_enabled() -> bool:
    # 三張 personalization 相關資料表都能正常查詢時，才切到 ORM 儲存流程。
    try:
        UserFavoriteModel.objects.count()
        CompareItemModel.objects.count()
        RecentViewModel.objects.count()
        return True
    except Exception:
        return False


def _get_or_bootstrap_db_user(username: str) -> Optional[AppUserModel]:
    # 個人化資料都綁在 `AppUser` 上；登入會員第一次進來時，必要時補出對應 ORM user。
    clean_username = str(username or "").strip().lower()
    if not clean_username or not _db_personalization_enabled():
        return None
    from . import auth_demo

    return auth_demo._get_or_bootstrap_db_user(clean_username)


def _visible_product_by_slug(slug: str) -> Dict[str, object] | None:
    # 收藏 / 比較 / 最近瀏覽都只應顯示可見商品，所以走 merged visible product 查詢。
    from . import product_management

    return product_management._merged_product_record_by_slug(str(slug or "").strip())


def _product_model_by_slug(slug: str) -> Optional[ProductModel]:
    # ORM 寫入收藏或比較前，需要先把 slug 解析成資料庫中的 Product row。
    if not _db_personalization_enabled():
        return None
    clean_slug = str(slug or "").strip()
    if not clean_slug:
        return None
    return ProductModel.objects.filter(slug=clean_slug).first()


def _favorite_slugs_from_db(db_user: AppUserModel) -> List[str]:
    # 依最新新增順序取出會員收藏清單，回寫 session 與 API 都會用到。
    return list(
        UserFavoriteModel.objects.filter(user=db_user)
        .select_related("product")
        .order_by("-id")
        .values_list("product__slug", flat=True)
    )


def _compare_slugs_from_db(db_user: AppUserModel) -> List[str]:
    # 比較清單使用獨立 bucket_key，讓同一使用者未來也可支援多裝置或多桶位。
    bucket_key = f"user:{db_user.id}"
    return list(
        CompareItemModel.objects.filter(bucket_key=bucket_key)
        .select_related("product")
        .order_by("-id")
        .values_list("product__slug", flat=True)
    )


def _recent_slugs_from_db(db_user: AppUserModel) -> List[str]:
    # 最近瀏覽以 viewed_at 排序，並在 DB 端先限制最大數量。
    return list(
        RecentViewModel.objects.filter(user=db_user)
        .select_related("product")
        .order_by("-viewed_at", "-id")
        .values_list("product__slug", flat=True)[:MAX_RECENT_VIEWS]
    )


def _sync_session_from_db(session, db_user: AppUserModel) -> None:
    # 將 ORM 目前狀態完整回寫到該會員的 session bucket，避免頁面仍讀到舊清單。
    _replace_bucket(session, FAVORITES_KEY, _favorite_slugs_from_db(db_user), bucket_name=db_user.username)
    _replace_bucket(session, COMPARE_PRODUCTS_KEY, _compare_slugs_from_db(db_user), bucket_name=db_user.username)
    _replace_bucket(session, RECENT_VIEWS_KEY, _recent_slugs_from_db(db_user), bucket_name=db_user.username)


def _bootstrap_user_bucket_from_session(session, db_user: AppUserModel) -> None:
    # ORM bucket 尚未建立時，用 session 內現有資料初始化 DB，完成後再反向同步回 session。
    username = db_user.username
    raw_favorites = session.get(FAVORITES_KEY, {})
    raw_compare = session.get(COMPARE_PRODUCTS_KEY, {})
    raw_recent = session.get(RECENT_VIEWS_KEY, {})
    favorite_slugs = list(raw_favorites.get(username, [])) if isinstance(raw_favorites, dict) else []
    compare_slugs = list(raw_compare.get(username, [])) if isinstance(raw_compare, dict) else []
    recent_slugs = list(raw_recent.get(username, [])) if isinstance(raw_recent, dict) else []

    if favorite_slugs and not UserFavoriteModel.objects.filter(user=db_user).exists():
        for slug in favorite_slugs:
            product = _product_model_by_slug(slug)
            if product:
                UserFavoriteModel.objects.get_or_create(user=db_user, product=product)

    bucket_key = f"user:{db_user.id}"
    if compare_slugs and not CompareItemModel.objects.filter(bucket_key=bucket_key).exists():
        for slug in compare_slugs[:MAX_COMPARE_PRODUCTS]:
            product = _product_model_by_slug(slug)
            if product:
                CompareItemModel.objects.get_or_create(
                    bucket_key=bucket_key,
                    product=product,
                    defaults={"user": db_user, "session_key": ""},
                )

    if recent_slugs and not RecentViewModel.objects.filter(user=db_user).exists():
        now = timezone.now()
        for index, slug in enumerate(recent_slugs[:MAX_RECENT_VIEWS]):
            product = _product_model_by_slug(slug)
            if product:
                RecentViewModel.objects.update_or_create(
                    user=db_user,
                    product=product,
                    defaults={"viewed_at": now - timedelta(seconds=index)},
                )

    _sync_session_from_db(session, db_user)


def migrate_guest_buckets(session, username: str) -> None:
    # 使用者登入後，把 guest bucket 合併進會員 bucket；若 ORM 可用，再同步落地到資料庫。
    bucket_name = username.strip().lower()
    if not bucket_name:
        return

    for key, max_items in (
        (FAVORITES_KEY, None),
        (RECENT_VIEWS_KEY, MAX_RECENT_VIEWS),
        (COMPARE_PRODUCTS_KEY, MAX_COMPARE_PRODUCTS),
    ):
        raw = session.get(key)
        if isinstance(raw, list):
            raw = {GUEST_BUCKET_KEY: list(raw)}
        elif not isinstance(raw, dict):
            raw = {}
        else:
            raw = dict(raw)

        guest_values = list(raw.get(GUEST_BUCKET_KEY, [])) if isinstance(raw.get(GUEST_BUCKET_KEY), list) else []
        target_values = list(raw.get(bucket_name, [])) if isinstance(raw.get(bucket_name), list) else []
        raw[bucket_name] = _merge_slug_lists(guest_values, target_values, max_items=max_items)
        raw[GUEST_BUCKET_KEY] = []
        session[key] = raw

    session.modified = True

    db_user = _get_or_bootstrap_db_user(bucket_name)
    if not db_user:
        return

    _bootstrap_user_bucket_from_session(session, db_user)


def get_favorite_slugs(session) -> List[str]:
    # 收藏清單優先讀 ORM；若使用者未登入或 DB 不可用，再退回 session bucket。
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        _bootstrap_user_bucket_from_session(session, db_user)
        slugs = _favorite_slugs_from_db(db_user)
        _replace_bucket(session, FAVORITES_KEY, slugs, bucket_name=db_user.username)
        return slugs
    return list(_ensure_bucket(session, FAVORITES_KEY))


def is_favorite(session, slug: str) -> bool:
    # 商品卡片上愛心狀態只需要判斷 slug 是否存在於目前收藏桶位。
    return str(slug or "").strip() in get_favorite_slugs(session)


def toggle_favorite(session, product: Dict[str, object]) -> bool:
    # 切換收藏時，登入會員寫 ORM，訪客只改 session；回傳值表示切換後是否為已收藏。
    slug = str(product["slug"])
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        db_product = _product_model_by_slug(slug)
        if not db_product:
            raise ValueError("Product not found in database.")
        favorite = UserFavoriteModel.objects.filter(user=db_user, product=db_product).first()
        if favorite:
            favorite.delete()
            active = False
        else:
            UserFavoriteModel.objects.create(user=db_user, product=db_product)
            active = True
        _replace_bucket(session, FAVORITES_KEY, _favorite_slugs_from_db(db_user), bucket_name=db_user.username)
        return active

    slugs = get_favorite_slugs(session)
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
    _replace_bucket(session, FAVORITES_KEY, slugs)
    return active


def get_favorite_products(session) -> List[Dict[str, object]]:
    # 收藏頁需要完整商品資料，這裡把 slug 清單轉回可見商品 payload。
    products: List[Dict[str, object]] = []
    for slug in get_favorite_slugs(session):
        product = _visible_product_by_slug(slug) or local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def record_recent_view(session, product: Dict[str, object]) -> None:
    # 每次進商品頁都會更新最近瀏覽；登入會員寫 ORM，訪客則更新 session 順序。
    slug = str(product["slug"])
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        db_product = _product_model_by_slug(slug)
        if db_product:
            RecentViewModel.objects.update_or_create(
                user=db_user,
                product=db_product,
                defaults={"viewed_at": timezone.now()},
            )
            slugs = _recent_slugs_from_db(db_user)
            _replace_bucket(session, RECENT_VIEWS_KEY, slugs, bucket_name=db_user.username)
        return

    slugs = list(_ensure_bucket(session, RECENT_VIEWS_KEY))
    if slug in slugs:
        slugs.remove(slug)
    slugs.insert(0, slug)
    _replace_bucket(session, RECENT_VIEWS_KEY, slugs[:MAX_RECENT_VIEWS])


def get_recent_products(session) -> List[Dict[str, object]]:
    # 會員中心與商品頁推薦區都會讀最近瀏覽商品，先拿 slug，再補回商品 payload。
    products: List[Dict[str, object]] = []
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        _bootstrap_user_bucket_from_session(session, db_user)
        slugs = _recent_slugs_from_db(db_user)
        _replace_bucket(session, RECENT_VIEWS_KEY, slugs, bucket_name=db_user.username)
    else:
        slugs = list(_ensure_bucket(session, RECENT_VIEWS_KEY))

    for slug in slugs:
        product = _visible_product_by_slug(slug) or local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def get_compare_slugs(session) -> List[str]:
    # 比較清單和收藏一樣優先讀 ORM，訪客則沿用 session bucket。
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        _bootstrap_user_bucket_from_session(session, db_user)
        slugs = _compare_slugs_from_db(db_user)
        _replace_bucket(session, COMPARE_PRODUCTS_KEY, slugs, bucket_name=db_user.username)
        return slugs
    return list(_ensure_bucket(session, COMPARE_PRODUCTS_KEY))


def is_in_compare(session, slug: str) -> bool:
    # 商品卡片的比較狀態只要判斷目前 slug 是否已在比較桶位中。
    return str(slug or "").strip() in get_compare_slugs(session)


def toggle_compare(session, product: Dict[str, object]) -> tuple[bool, str]:
    # 切換比較清單時，回傳 `(是否已加入, 被擠掉的 slug)`，方便前端提示超出上限的商品。
    slug = str(product["slug"])
    username = _session_username(session)
    db_user = _get_or_bootstrap_db_user(username) if username else None
    if db_user:
        db_product = _product_model_by_slug(slug)
        if not db_product:
            raise ValueError("Product not found in database.")
        bucket_key = f"user:{db_user.id}"
        compare_item = CompareItemModel.objects.filter(bucket_key=bucket_key, product=db_product).first()
        removed_slug = ""
        if compare_item:
            compare_item.delete()
            active = False
        else:
            active = True
            CompareItemModel.objects.create(
                user=db_user,
                session_key="",
                bucket_key=bucket_key,
                product=db_product,
            )
            slugs = _compare_slugs_from_db(db_user)
            if len(slugs) > MAX_COMPARE_PRODUCTS:
                removed_slug = str(slugs[-1])
                CompareItemModel.objects.filter(bucket_key=bucket_key, product__slug=removed_slug).delete()
        final_slugs = _compare_slugs_from_db(db_user)[:MAX_COMPARE_PRODUCTS]
        _replace_bucket(session, COMPARE_PRODUCTS_KEY, final_slugs, bucket_name=db_user.username)
        return active, removed_slug

    slugs = get_compare_slugs(session)
    removed_slug = ""
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
        if len(slugs) > MAX_COMPARE_PRODUCTS:
            removed_slug = str(slugs.pop())
    _replace_bucket(session, COMPARE_PRODUCTS_KEY, slugs)
    return active, removed_slug


def get_compare_products(session) -> List[Dict[str, object]]:
    # 比較頁需要完整商品內容，這裡把比較桶內的 slug 依順序轉成商品 payload。
    products: List[Dict[str, object]] = []
    for slug in get_compare_slugs(session):
        product = _visible_product_by_slug(slug) or local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products

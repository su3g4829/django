"""個人化互動服務模組。

負責收藏、最近瀏覽與商品比較清單等 session 型個人化資料。
"""
from __future__ import annotations

from typing import Dict, List

from ..repositories import local_store

FAVORITES_KEY = "favorite_products"
RECENT_VIEWS_KEY = "recent_products"
COMPARE_PRODUCTS_KEY = "compare_products"
MAX_RECENT_VIEWS = 8
MAX_COMPARE_PRODUCTS = 4


def get_favorite_slugs(session) -> List[str]:
    """取得 個人化互動 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    slugs = session.get(FAVORITES_KEY, [])
    return slugs if isinstance(slugs, list) else []


def is_favorite(session, slug: str) -> bool:
    """判斷 個人化互動 條件是否成立。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return slug in get_favorite_slugs(session)


def toggle_favorite(session, product: Dict[str, object]) -> bool:
    """切換商品是否在收藏清單中。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        product: 單一商品資料字典。

    回傳:
        切換後的狀態結果，通常是布林值或狀態訊息。
    """
    slugs = list(get_favorite_slugs(session))
    slug = str(product["slug"])
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
    session[FAVORITES_KEY] = slugs
    session.modified = True
    return active


def get_favorite_products(session) -> List[Dict[str, object]]:
    """取得 個人化互動 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products = []
    for slug in get_favorite_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def record_recent_view(session, product: Dict[str, object]) -> None:
    """記錄商品最近瀏覽清單，供會員中心與推薦功能使用。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        product: 單一商品資料字典。

    回傳:
        無回傳值；函式會直接修改 session、檔案或傳入資料。
    """
    slugs = list(session.get(RECENT_VIEWS_KEY, []))
    slug = str(product["slug"])
    if slug in slugs:
        slugs.remove(slug)
    slugs.insert(0, slug)
    session[RECENT_VIEWS_KEY] = slugs[:MAX_RECENT_VIEWS]
    session.modified = True


def get_recent_products(session) -> List[Dict[str, object]]:
    """取得 個人化互動 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    slugs = session.get(RECENT_VIEWS_KEY, [])
    products = []
    for slug in slugs if isinstance(slugs, list) else []:
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products


def get_compare_slugs(session) -> List[str]:
    """取得 個人化互動 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        列表資料，可直接提供給頁面或 API 進一步使用。
    """
    slugs = session.get(COMPARE_PRODUCTS_KEY, [])
    return slugs if isinstance(slugs, list) else []


def is_in_compare(session, slug: str) -> bool:
    """判斷 個人化互動 條件是否成立。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        slug: 商品或頁面使用的網址識別字串。

    回傳:
        布林值，用來表示條件是否成立或操作是否成功。
    """
    return slug in get_compare_slugs(session)


def toggle_compare(session, product: Dict[str, object]) -> tuple[bool, str]:
    """切換商品是否加入比較清單。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。
        product: 單一商品資料字典。

    回傳:
        切換後的狀態結果，通常是布林值或狀態訊息。
    """
    slugs = list(get_compare_slugs(session))
    slug = str(product["slug"])
    removed_slug = ""
    if slug in slugs:
        slugs.remove(slug)
        active = False
    else:
        slugs.insert(0, slug)
        active = True
        if len(slugs) > MAX_COMPARE_PRODUCTS:
            removed_slug = str(slugs.pop())
    session[COMPARE_PRODUCTS_KEY] = slugs
    session.modified = True
    return active, removed_slug


def get_compare_products(session) -> List[Dict[str, object]]:
    """取得 個人化互動 流程中指定條件的資料。

    參數:
        session: Django session 物件，用來保存登入狀態、購物車與個人化資料。

    回傳:
        整理後的資料字典；若查無資料，部分函式可能回傳 `None`。
    """
    products = []
    for slug in get_compare_slugs(session):
        product = local_store.get_product_by_slug(slug)
        if product:
            products.append(product)
    return products

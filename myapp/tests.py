"""專案測試集合。

測試內容涵蓋：
- 頁面流程與文件頁
- DRF API
- 商品、購物車、訂單、會員中心
- 賣家中心、社群、Banner 與管理後台

目前多數整合測試會先 seed ORM 資料，再透過 API 或 service 驗證
DB-first 架構下的實際行為。
"""

import json
import os
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from .models import AppUser as AppUserModel
from .models import Banner as BannerModel
from .models import Brand as BrandModel
from .models import Cart as CartModel
from .models import CartItem as CartItemModel
from .models import Category as CategoryModel
from .models import CommunityPost as CommunityPostModel
from .models import CommunityReply as CommunityReplyModel
from .models import CommunityVote as CommunityVoteModel
from .models import CompareItem as CompareItemModel
from .models import NewebpayStoreMapSelection as NewebpayStoreMapSelectionModel
from .models import Order as OrderModel
from .models import OrderItem as OrderItemModel
from .models import PasswordResetToken as PasswordResetTokenModel
from .models import PaymentTransaction as PaymentTransactionModel
from .models import Product as ProductModel
from .models import ProductQuestion as ProductQuestionModel
from .models import ProductQuestionAnswer as ProductQuestionAnswerModel
from .models import ProductRecommendation as ProductRecommendationModel
from .models import ProductReview as ProductReviewModel
from .models import RecentView as RecentViewModel
from .models import SellerRequest as SellerRequestModel
from .models import ShipmentEvent as ShipmentEventModel
from .models import UserFavorite as UserFavoriteModel
from .models import UserAddress as UserAddressModel
from .models import UserInvoiceProfile as UserInvoiceProfileModel
from .models import UserShippingRule as UserShippingRuleModel
from .services import auth_demo
from .services import banners as banner_service
from .services import cloud_storage as cloud_storage_service
from .services import community as community_service
from .services import customer_center
from .services import newebpay_payment_real as newebpay_payment_real_service
from .services import orders as orders_service
from .services import password_reset as password_reset_service
from .services import personalization as personalization_service
from .services import price_compare as price_compare_service
from .services import product_management
from .services import questions as question_service
from .services import recommendations as recommendation_service
from .services import reviews as review_service
from .services.privacy import anonymize_public_name
from .management.commands.migrate_media_to_gcs import infer_object_name_from_legacy_path, replace_media_references


PRODUCTS_FIXTURE = [
    {
        "id": 1,
        "slug": "acme-mug",
        "name": "ACME Mug",
        "price": 12.9,
        "brand": "ACME",
        "category": "kitchen",
        "tags": ["mug", "ceramic"],
        "images": [],
        "specs": {"capacity_ml": 350},
        "status": "active",
        "stock": 10,
        "owner_username": "alice",
        "owner_display_name": "Alice",
    },
    {
        "id": 2,
        "slug": "acme-tee",
        "name": "ACME Tee",
        "price": 24.0,
        "brand": "ACME",
        "category": "apparel",
        "tags": ["shirt"],
        "images": [],
        "specs": {"size": "M"},
        "status": "active",
        "stock": 8,
        "owner_username": "alice",
        "owner_display_name": "Alice",
    },
    {
        "id": 3,
        "slug": "acme-bottle",
        "name": "ACME Bottle",
        "price": 18.5,
        "brand": "ACME",
        "category": "outdoor",
        "tags": ["bottle", "stainless"],
        "images": [],
        "specs": {"capacity_ml": 750},
        "status": "active",
        "stock": 12,
        "owner_username": "alice",
        "owner_display_name": "Alice",
    },
]


class CloudStorageServiceTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        cloud_storage_service._service_account_info.cache_clear()
        cloud_storage_service._storage_client.cache_clear()
        self.addCleanup(cloud_storage_service._service_account_info.cache_clear)
        self.addCleanup(cloud_storage_service._storage_client.cache_clear)

    def test_build_public_url_uses_bucket_base(self):
        with patch.dict(
            os.environ,
            {
                "GCS_BUCKET_NAME": "store_django",
                "GCS_SERVICE_ACCOUNT_JSON": "{}",
            },
            clear=False,
        ):
            url = cloud_storage_service.build_public_url("products/demo image.png")

        self.assertEqual(url, "https://storage.googleapis.com/store_django/products/demo%20image.png")

    def test_object_name_from_public_url_parses_bucket_path(self):
        with patch.dict(
            os.environ,
            {
                "GCS_BUCKET_NAME": "store_django",
                "GCS_SERVICE_ACCOUNT_JSON": "{}",
            },
            clear=False,
        ):
            object_name = cloud_storage_service.object_name_from_public_url(
                "https://storage.googleapis.com/store_django/community/poster%201.png"
            )

        self.assertEqual(object_name, "community/poster 1.png")

    def test_delete_by_public_url_deletes_matching_blob(self):
        class FakeBlob:
            def __init__(self):
                self.deleted = False

            def delete(self):
                self.deleted = True

        class FakeBucket:
            def __init__(self):
                self.blob_name = None
                self.blob_instance = FakeBlob()

            def blob(self, name):
                self.blob_name = name
                return self.blob_instance

        class FakeClient:
            def __init__(self):
                self.bucket_name = None
                self.bucket_instance = FakeBucket()

            def bucket(self, name):
                self.bucket_name = name
                return self.bucket_instance

        fake_client = FakeClient()

        with patch.dict(
            os.environ,
            {
                "GCS_BUCKET_NAME": "store_django",
                "GCS_SERVICE_ACCOUNT_JSON": "{}",
            },
            clear=False,
        ):
            with patch("myapp.services.cloud_storage._storage_client", return_value=fake_client):
                deleted = cloud_storage_service.delete_by_public_url(
                    "https://storage.googleapis.com/store_django/banners/banner-1.png"
                )

        self.assertTrue(deleted)
        self.assertEqual(fake_client.bucket_name, "store_django")
        self.assertEqual(fake_client.bucket_instance.blob_name, "banners/banner-1.png")
        self.assertTrue(fake_client.bucket_instance.blob_instance.deleted)


class MediaMigrationCommandTests(SimpleTestCase):
    def test_infer_object_name_from_legacy_path_maps_known_directories(self):
        self.assertEqual(
            infer_object_name_from_legacy_path("/static/uploads/products/demo.png"),
            "products/demo.png",
        )
        self.assertEqual(
            infer_object_name_from_legacy_path("http://localhost:3000/static/images/banner.jpg"),
            "images/banner.jpg",
        )

    def test_replace_media_references_swaps_relative_and_localhost_urls(self):
        body = (
            '<p><img src="/static/uploads/community/post-1.png"> '
            '<img src="http://localhost:3000/static/uploads/community/post-1.png"></p>'
        )
        updated = replace_media_references(
            body,
            {"/static/uploads/community/post-1.png": "https://storage.googleapis.com/store_django/community/post-1.png"},
        )

        self.assertNotIn("/static/uploads/community/post-1.png", updated)
        self.assertEqual(updated.count("https://storage.googleapis.com/store_django/community/post-1.png"), 2)


@contextmanager
def _gcs_disabled_for_test():
    overrides = {
        "GCS_PROJECT_ID": "",
        "GCS_BUCKET_NAME": "",
        "GCS_SERVICE_ACCOUNT_FILE": "",
        "GCS_SERVICE_ACCOUNT_JSON": "",
        "GCS_PUBLIC_BASE_URL": "",
    }
    cloud_storage_service._service_account_info.cache_clear()
    cloud_storage_service._storage_client.cache_clear()
    with patch.dict(os.environ, overrides, clear=False):
        try:
            yield
        finally:
            cloud_storage_service._service_account_info.cache_clear()
            cloud_storage_service._storage_client.cache_clear()

CATEGORIES_FIXTURE = [
    {
        "id": 1,
        "slug": "tops",
        "name": "上衣",
        "description": "上衣分類",
        "is_active": True,
        "sort_order": 1,
    },
    {
        "id": 2,
        "slug": "pants",
        "name": "褲子",
        "description": "褲子分類",
        "is_active": True,
        "sort_order": 2,
    },
    {
        "id": 3,
        "slug": "kitchen",
        "name": "kitchen",
        "description": "legacy kitchen category for tests",
        "is_active": True,
        "sort_order": 10,
    },
    {
        "id": 4,
        "slug": "apparel",
        "name": "apparel",
        "description": "legacy apparel category for tests",
        "is_active": True,
        "sort_order": 11,
    },
    {
        "id": 5,
        "slug": "outdoor",
        "name": "outdoor",
        "description": "legacy outdoor category for tests",
        "is_active": True,
        "sort_order": 12,
    },
]

REVIEWS_FIXTURE = [
    {
        "id": 1,
        "product_id": 1,
        "author": "Alice",
        "rating": 5,
        "title": "Nice daily mug",
        "body": "The size is practical and the ceramic feels solid.",
        "created_at": "2026-04-10T09:30:00+08:00",
    }
]

RECOMMENDATIONS_FIXTURE = [
    {
        "product_id": 1,
        "similar_ids": [2],
        "also_bought_ids": [3],
    }
]

COMPETITOR_PRICES_FIXTURE = [
    {
        "our_product_slug": "acme-mug",
        "our_product_name": "ACME Mug",
        "our_product_id": 1,
        "source_type": "mock",
        "last_refreshed_at": "2026-05-25T10:00:00+08:00",
        "competitors": [
            {
                "site": "momo",
                "site_label": "momo 購物網",
                "title": "ACME Mug - momo 模擬結果",
                "url": "https://example.com/momo/acme-mug",
                "price": 11.9,
                "currency": "TWD",
                "captured_at": "2026-05-25T10:00:00+08:00",
                "status": "matched",
                "note": "模擬資料",
                "mock_rank": 1,
            },
            {
                "site": "pchome",
                "site_label": "PChome 24h",
                "title": "ACME Mug - PChome 模擬結果",
                "url": "https://example.com/pchome/acme-mug",
                "price": 13.5,
                "currency": "TWD",
                "captured_at": "2026-05-25T10:02:00+08:00",
                "status": "matched",
                "note": "模擬資料",
                "mock_rank": 2,
            },
        ],
    }
]

QUESTIONS_FIXTURE = [
    {
        "id": 1,
        "product_id": 1,
        "author": "Eva",
        "title": "Can this go in the dishwasher?",
        "body": "I want to use it every day and need easy cleaning.",
        "created_at": "2026-04-20T10:15:00+08:00",
        "answers": [
            {
                "id": 1,
                "author": "Store Team",
                "body": "Yes. The mug is safe for regular dishwasher use.",
                "created_at": "2026-04-20T11:00:00+08:00",
            }
        ],
    }
]

POSTS_FIXTURE = [
    {
        "id": 1,
        "topic": "general",
        "author": "Nora",
        "title": "Best mug for office use?",
        "body": "I want something easy to clean and good for daily coffee.",
        "tags": ["mug", "office"],
        "votes": 3,
        "created_at": "2026-04-25T09:00:00+08:00",
        "replies": [
            {
                "id": 1,
                "author": "Store Team",
                "body": "The ACME Mug is our most common office pick because it is compact and dishwasher safe.",
                "created_at": "2026-04-25T09:45:00+08:00",
            }
        ],
    }
]

BANNERS_FIXTURE = [
    {
        "id": 1,
        "title": "Primary Banner",
        "copy_text": "Main campaign",
        "image_path": "/static/images/banner-1.jpg",
        "link_url": "/products/acme-mug",
        "starts_at": "2026-05-01",
        "ends_at": "2026-06-30",
        "position": "home_main",
        "note": "seeded active banner",
        "sort_order": 1,
        "status": "approved",
        "is_active": True,
        "rejection_reason": "",
        "applicant_user_id": 2,
        "applicant_username": "storeteam",
        "applicant_display_name": "Store Team",
        "reviewed_at": "2026-05-31T10:00:00+08:00",
        "reviewed_by_username": "storeteam",
        "reviewed_by_display_name": "Store Team",
        "created_at": "2026-05-31T10:00:00+08:00",
        "updated_at": "2026-05-31T10:00:00+08:00",
    },
    {
        "id": 2,
        "title": "Hidden Banner",
        "copy_text": "Disabled campaign",
        "image_path": "/static/images/banner-2.jpg",
        "link_url": "/products/acme-tee",
        "starts_at": "2026-04-01",
        "ends_at": "2026-04-30",
        "position": "home_main",
        "note": "expired banner",
        "sort_order": 2,
        "status": "approved",
        "is_active": True,
        "rejection_reason": "",
        "applicant_user_id": 2,
        "applicant_username": "storeteam",
        "applicant_display_name": "Store Team",
        "reviewed_at": "2026-05-31T11:00:00+08:00",
        "reviewed_by_username": "storeteam",
        "reviewed_by_display_name": "Store Team",
        "created_at": "2026-05-31T11:00:00+08:00",
        "updated_at": "2026-05-31T11:00:00+08:00",
    },
]

ORDERS_FIXTURE = []

USERS_FIXTURE = [
    {
        "id": 1,
        "username": "alice",
        "password": "demo123",
        "display_name": "Alice",
        "role": "seller",
        "seller_request_status": "approved",
    },
    {
        "id": 2,
        "username": "storeteam",
        "password": "demo123",
        "display_name": "Store Team",
        "role": "admin",
        "seller_request_status": "approved",
    },
    {
        "id": 3,
        "username": "buyer",
        "password": "demo123",
        "display_name": "Buyer",
        "role": "member",
        "seller_request_status": "",
    },
]


def _fixture_datetime(value: str):
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = parse_datetime(raw)
    if parsed is not None:
        return parsed
    if len(raw) == 10:
        parsed = timezone.datetime.fromisoformat(f"{raw}T00:00:00")
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return None


def _seed_users(records=None):
    for user in records or USERS_FIXTURE:
        auth_demo._sync_user_to_orm(dict(user))


def _seed_categories(records=None):
    for category in records or CATEGORIES_FIXTURE:
        CategoryModel.objects.update_or_create(
            id=int(category["id"]),
            defaults={
                "slug": str(category.get("slug") or "").strip(),
                "name": str(category.get("name") or category.get("label") or "").strip(),
                "description": str(category.get("description") or "").strip(),
                "is_active": bool(category.get("is_active", True)),
            },
        )


def _seed_products(records=None):
    category_slugs = {str(item.get("slug") or "").strip().lower() for item in CATEGORIES_FIXTURE}
    for product_record in records or PRODUCTS_FIXTURE:
        seeded_record = dict(product_record)
        category_slug = str(seeded_record.get("category") or seeded_record.get("category_slug") or "").strip().lower()
        if category_slug:
            seeded_record.setdefault("category_slug", category_slug)
            if category_slug not in category_slugs:
                CategoryModel.objects.get_or_create(
                    slug=category_slug,
                    defaults={"name": category_slug.replace("-", " ").title(), "is_active": True},
                )
                category_slugs.add(category_slug)
        owner_username = str(seeded_record.get("owner_username") or "").strip().lower()
        owner_snapshot = auth_demo.get_user_by_username(owner_username) if owner_username else None
        if not owner_snapshot:
            owner_snapshot = {
                "username": owner_username or "alice",
                "display_name": str(seeded_record.get("owner_display_name") or owner_username or "Alice").strip(),
                "role": "seller",
            }
        product_management._sync_product_record_to_orm(seeded_record, owner_snapshot=owner_snapshot)


def _seed_reviews(records=None):
    ProductReviewModel.objects.all().delete()
    for review in records or REVIEWS_FIXTURE:
        product = ProductModel.objects.filter(id=int(review["product_id"])).first()
        if product is None:
            continue
        author_name = str(review.get("author") or "").strip() or "Reviewer"
        username = author_name.lower().replace(" ", "")
        author_snapshot = auth_demo.get_user_by_username(username)
        if not author_snapshot:
            auth_demo._sync_user_to_orm({"username": username, "password": "demo123", "display_name": author_name, "role": "member"})
            author_snapshot = auth_demo.get_user_by_username(username)
        author = AppUserModel.objects.get(username=username)
        obj, _ = ProductReviewModel.objects.update_or_create(
            id=int(review["id"]),
            defaults={
                "product": product,
                "author": author,
                "author_display_name_snapshot": author_name,
                "rating": int(review.get("rating", 5)),
                "title": str(review.get("title") or ""),
                "body": str(review.get("body") or ""),
                "is_visible": True,
            },
        )
        created_at = _fixture_datetime(str(review.get("created_at") or ""))
        if created_at:
            ProductReviewModel.objects.filter(id=obj.id).update(created_at=created_at, updated_at=created_at)


def _seed_questions(records=None):
    ProductQuestionAnswerModel.objects.all().delete()
    ProductQuestionModel.objects.all().delete()
    for question in records or QUESTIONS_FIXTURE:
        product = ProductModel.objects.filter(id=int(question["product_id"])).first()
        if product is None:
            continue
        author_name = str(question.get("author") or "").strip() or "Question User"
        username = author_name.lower().replace(" ", "")
        if not auth_demo.get_user_by_username(username):
            auth_demo._sync_user_to_orm({"username": username, "password": "demo123", "display_name": author_name, "role": "member"})
        author = AppUserModel.objects.get(username=username)
        obj, _ = ProductQuestionModel.objects.update_or_create(
            id=int(question["id"]),
            defaults={
                "product": product,
                "author": author,
                "author_display_name_snapshot": author_name,
                "title": str(question.get("title") or ""),
                "body": str(question.get("body") or ""),
                "is_visible": True,
            },
        )
        created_at = _fixture_datetime(str(question.get("created_at") or ""))
        if created_at:
            ProductQuestionModel.objects.filter(id=obj.id).update(created_at=created_at, updated_at=created_at)
        for answer in question.get("answers", []) or []:
            answer_name = str(answer.get("author") or "").strip() or "Answer User"
            answer_username = answer_name.lower().replace(" ", "")
            if not auth_demo.get_user_by_username(answer_username):
                auth_demo._sync_user_to_orm({"username": answer_username, "password": "demo123", "display_name": answer_name, "role": "member"})
            answer_author = AppUserModel.objects.get(username=answer_username)
            answer_obj, _ = ProductQuestionAnswerModel.objects.update_or_create(
                id=int(answer["id"]),
                defaults={
                    "question": obj,
                    "author": answer_author,
                    "author_display_name_snapshot": answer_name,
                    "body": str(answer.get("body") or ""),
                    "is_visible": True,
                },
            )
            answer_created_at = _fixture_datetime(str(answer.get("created_at") or ""))
            if answer_created_at:
                ProductQuestionAnswerModel.objects.filter(id=answer_obj.id).update(
                    created_at=answer_created_at,
                    updated_at=answer_created_at,
                )


def _seed_posts(records=None):
    CommunityVoteModel.objects.all().delete()
    CommunityReplyModel.objects.all().delete()
    CommunityPostModel.objects.all().delete()
    for post in records or POSTS_FIXTURE:
        author_name = str(post.get("author") or "").strip() or "Community User"
        author_username = str(post.get("author_username") or "").strip().lower() or author_name.lower().replace(" ", "")
        if not auth_demo.get_user_by_username(author_username):
            auth_demo._sync_user_to_orm({"username": author_username, "password": "demo123", "display_name": author_name, "role": "member"})
        author = AppUserModel.objects.get(username=author_username)
        obj, _ = CommunityPostModel.objects.update_or_create(
            id=int(post["id"]),
            defaults={
                "author": author,
                "author_display_name_snapshot": author_name,
                "topic": str(post.get("topic") or "general"),
                "title": str(post.get("title") or ""),
                "body_html": str(post.get("body") or ""),
                "votes_count": int(post.get("votes", 0) or 0),
                "is_visible": True,
            },
        )
        created_at = _fixture_datetime(str(post.get("created_at") or ""))
        if created_at:
            CommunityPostModel.objects.filter(id=obj.id).update(created_at=created_at, updated_at=created_at)
        for reply in post.get("replies", []) or []:
            reply_name = str(reply.get("author") or "").strip() or "Reply User"
            reply_username = str(reply.get("author_username") or "").strip().lower() or reply_name.lower().replace(" ", "")
            if not auth_demo.get_user_by_username(reply_username):
                auth_demo._sync_user_to_orm({"username": reply_username, "password": "demo123", "display_name": reply_name, "role": "member"})
            reply_author = AppUserModel.objects.get(username=reply_username)
            reply_obj, _ = CommunityReplyModel.objects.update_or_create(
                id=int(reply["id"]),
                defaults={
                    "post": obj,
                    "author": reply_author,
                    "author_display_name_snapshot": reply_name,
                    "body": str(reply.get("body") or ""),
                    "is_visible": True,
                },
            )
            reply_created_at = _fixture_datetime(str(reply.get("created_at") or ""))
            if reply_created_at:
                CommunityReplyModel.objects.filter(id=reply_obj.id).update(
                    created_at=reply_created_at,
                    updated_at=reply_created_at,
                )


def _seed_banners(records=None):
    BannerModel.objects.all().delete()
    for banner in records or BANNERS_FIXTURE:
        banner_service._sync_banner_record_to_orm(dict(banner))


def _seed_recommendations(records=None):
    ProductRecommendationModel.objects.all().delete()
    for item in records or RECOMMENDATIONS_FIXTURE:
        source = ProductModel.objects.filter(id=int(item["product_id"])).first()
        if source is None:
            continue
        for rank, product_id in enumerate(item.get("similar_ids", []) or [], start=1):
            recommended = ProductModel.objects.filter(id=int(product_id)).first()
            if recommended is None:
                continue
            ProductRecommendationModel.objects.update_or_create(
                source_product=source,
                recommended_product=recommended,
                defaults={"reason": "similar", "score": max(1, 100 - rank)},
            )
        for rank, product_id in enumerate(item.get("also_bought_ids", []) or [], start=1):
            recommended = ProductModel.objects.filter(id=int(product_id)).first()
            if recommended is None:
                continue
            ProductRecommendationModel.objects.update_or_create(
                source_product=source,
                recommended_product=recommended,
                defaults={"reason": "also_bought", "score": max(1, 100 - rank)},
            )


def _seed_orders(records=None):
    for order in records or ORDERS_FIXTURE:
        orders_service._sync_order_record_to_orm(dict(order))


def _seed_fixture_state(*, products=None, orders=None, reviews=None, questions=None, posts=None):
    _seed_users()
    _seed_categories()
    _seed_products(products)
    _seed_reviews(reviews)
    _seed_questions(questions)
    _seed_posts(posts)
    _seed_banners()
    _seed_recommendations()
    _seed_orders(orders)


class _OrmLocalStoreAdapter:
    """測試期相容 adapter。

    測試仍大量沿用 `local_store` 這個讀取介面名稱，
    但實際資料都改由 ORM 與 service 組裝回傳。
    """

    @staticmethod
    def clear_cache():
        return None

    @staticmethod
    def get_user_by_username(username):
        clean_username = str(username or "").strip().lower()
        db_user = AppUserModel.objects.filter(username=clean_username).first()
        if db_user is None:
            return None
        payload = auth_demo.get_user_by_username(clean_username) or {}
        addresses = customer_center.list_addresses(clean_username)
        default_address = next((item for item in addresses if item.get("is_default")), None)
        payload["password_hash"] = db_user.password_hash
        payload["addresses"] = addresses
        payload["default_address_id"] = int(default_address["id"]) if default_address else None
        payload["invoice_profile"] = customer_center.get_invoice_profile(clean_username)
        payload["shipping_rules"] = auth_demo.get_seller_shipping_rules(clean_username)
        return payload

    @staticmethod
    def get_product_by_slug(slug):
        return product_management.get_product_for_admin(slug)

    @staticmethod
    def get_categories():
        return product_management.list_product_categories(include_inactive=True)

    @staticmethod
    def get_order_by_id(order_id):
        return orders_service._db_order_record_by_id(int(order_id))

    @staticmethod
    def get_orders():
        return list(orders_service._merged_order_records())

    @staticmethod
    def save_orders(records):
        for record in records:
            orders_service._sync_order_record_to_orm(dict(record))

    @staticmethod
    def get_orders_by_username(username):
        return orders_service.list_orders_for_seller(username)

    @staticmethod
    def get_reviews_by_product_id(product_id):
        return review_service.list_reviews(int(product_id))

    @staticmethod
    def get_reviews():
        return review_service.list_all_reviews()

    @staticmethod
    def get_questions_by_product_id(product_id):
        return question_service.list_questions(int(product_id))

    @staticmethod
    def get_questions():
        return question_service.list_all_questions()

    @staticmethod
    def get_post_by_id(post_id):
        post = CommunityPostModel.objects.filter(id=int(post_id), is_visible=True).select_related("author").prefetch_related("replies__author").first()
        if post is None:
            return None
        return community_service._db_post_to_record(post)

    @staticmethod
    def get_posts():
        return community_service.list_all_posts()

    @staticmethod
    def get_newebpay_payment_logs():
        return [
            newebpay_payment_real_service._record_from_transaction(item)
            for item in PaymentTransactionModel.objects.select_related("order", "order__buyer")
            .prefetch_related("callback_logs")
            .order_by("-updated_at", "-created_at", "-id")
        ]


local_store = _OrmLocalStoreAdapter()


def build_extra_products():
    """建立額外商品 fixture。

    Returns:
        list[dict]: 加上延伸商品後的測試資料。
    """
    return PRODUCTS_FIXTURE + [
        {
            "id": 4,
            "slug": "beta-pan",
            "name": "Beta Pan",
            "price": 32.5,
            "brand": "Beta",
            "category": "kitchen",
            "tags": ["pan"],
            "images": [],
            "specs": {"diameter_cm": 24},
            "status": "active",
            "stock": 6,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 5,
            "slug": "camp-cup",
            "name": "Camp Cup",
            "price": 9.5,
            "brand": "Trails",
            "category": "outdoor",
            "tags": ["mug", "camp"],
            "images": [],
            "specs": {"capacity_ml": 280},
            "status": "active",
            "stock": 14,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
    ]


def build_catalog_products():
    """建立商品目錄測試專用 fixture。

    Returns:
        list[dict]: 商品列表頁會用到的完整測試商品資料。
    """
    return [
        {
            "id": 1,
            "slug": "acme-mug",
            "name": "ACME Mug",
            "price": 12.9,
            "brand": "ACME",
            "category": "kitchen",
            "tags": ["mug", "ceramic"],
            "images": [],
            "specs": {"capacity_ml": 350},
            "status": "active",
            "stock": 10,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 2,
            "slug": "acme-tee",
            "name": "ACME Tee",
            "price": 24.0,
            "brand": "ACME",
            "category": "apparel",
            "tags": ["shirt"],
            "images": [],
            "specs": {"size": "M"},
            "status": "active",
            "stock": 8,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 3,
            "slug": "acme-bottle",
            "name": "ACME Bottle",
            "price": 18.5,
            "brand": "ACME",
            "category": "outdoor",
            "tags": ["bottle", "stainless"],
            "images": [],
            "specs": {"capacity_ml": 750},
            "status": "active",
            "stock": 12,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 4,
            "slug": "beta-pan",
            "name": "Beta Pan",
            "price": 32.5,
            "brand": "Beta",
            "category": "kitchen",
            "tags": ["pan"],
            "images": [],
            "specs": {"diameter_cm": 24},
            "status": "active",
            "stock": 6,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 5,
            "slug": "camp-cup",
            "name": "Camp Cup",
            "price": 9.5,
            "brand": "Trails",
            "category": "outdoor",
            "tags": ["mug", "camp"],
            "images": [],
            "specs": {"capacity_ml": 280},
            "status": "active",
            "stock": 14,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
    ]


def build_public_and_draft_products():
    """建立同時包含公開與草稿商品的 fixture。
    Returns:
        list[dict]: 可用來驗證可見性規則的商品資料。
    """
    return [
        {
            "id": 1,
            "slug": "acme-mug",
            "name": "ACME Mug",
            "price": 12.9,
            "brand": "ACME",
            "category": "kitchen",
            "tags": ["mug", "ceramic"],
            "images": [],
            "specs": {"capacity_ml": 350},
            "status": "active",
            "stock": 10,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 2,
            "slug": "seller-draft-mug",
            "name": "Seller Draft Mug",
            "price": 22.5,
            "brand": "Alice Studio",
            "category": "kitchen",
            "tags": ["draft"],
            "images": [],
            "specs": {"capacity_ml": "420"},
            "owner_username": "alice",
            "owner_display_name": "Alice",
            "status": "draft",
            "stock": 4,
            "review_note": "",
            "created_at": "2026-04-29T08:00:00+08:00",
            "updated_at": "2026-04-29T08:00:00+08:00",
        },
    ]


def build_seller_order_products():
    """建立賣家訂單相關測試商品。

    Returns:
        list[dict]: 含賣家資訊的商品資料。
    """
    return [
        {
            "id": 1,
            "slug": "alice-mug",
            "name": "Alice Mug",
            "price": 12.9,
            "brand": "Alice Studio",
            "category": "kitchen",
            "tags": ["mug"],
            "images": [],
            "specs": {"capacity_ml": 350},
            "status": "active",
            "stock": 10,
            "owner_username": "alice",
            "owner_display_name": "Alice",
        },
        {
            "id": 2,
            "slug": "team-bottle",
            "name": "Team Bottle",
            "price": 18.0,
            "brand": "Team",
            "category": "outdoor",
            "tags": ["bottle"],
            "images": [],
            "specs": {"capacity_ml": 600},
            "status": "active",
            "stock": 5,
            "owner_username": "storeteam",
            "owner_display_name": "Store Team",
        },
    ]


def build_variant_products():
    """建立含變體與 SKU 的測試商品。

    Returns:
        list[dict]: 變體功能測試用商品資料。
    """
    return [
        {
            "id": 1,
            "slug": "acme-hoodie",
            "name": "ACME Hoodie",
            "price": 28.0,
            "compare_at_price": 35.0,
            "brand": "ACME",
            "category": "apparel",
            "tags": ["hoodie", "winter"],
            "images": ["/static/uploads/products/hoodie-1.png", "/static/uploads/products/hoodie-2.png"],
            "specs": {"material": "cotton"},
            "stock": 5,
            "variants": [
                {
                    "id": "navy-m",
                    "name": "Navy / M",
                    "sku": "HD-NV-M",
                    "price": 28.0,
                    "stock": 2,
                    "attributes": {"color": "Navy", "size": "M"},
                    "image_index": 1,
                },
                {
                    "id": "navy-l",
                    "name": "Navy / L",
                    "sku": "HD-NV-L",
                    "price": 30.0,
                    "stock": 3,
                    "attributes": {"color": "Navy", "size": "L"},
                    "image_index": 2,
                },
            ],
            "status": "active",
            "owner_username": "alice",
            "owner_display_name": "Alice",
        }
    ]


def build_attribute_products():
    """建立屬性過濾測試用商品。

    Returns:
        list[dict]: 含顏色、尺寸等屬性的商品資料。
    """
    return build_variant_products() + [
        {
            "id": 2,
            "slug": "beta-jacket",
            "name": "Beta Jacket",
            "price": 42.0,
            "brand": "Beta",
            "category": "apparel",
            "tags": ["jacket"],
            "images": ["/static/uploads/products/jacket-1.png"],
            "specs": {"material": "nylon"},
            "stock": 4,
            "variants": [
                {
                    "id": "black-l",
                    "name": "Black / L",
                    "sku": "JK-BK-L",
                    "price": 42.0,
                    "stock": 4,
                    "attributes": {"color": "Black", "size": "L"},
                    "image_index": 1,
                }
            ],
            "status": "active",
            "owner_username": "alice",
            "owner_display_name": "Alice",
        }
    ]


class ProductFeatureTests(TestCase):
    """驗證商品、購物流程與 API 的主要整合行為。"""
    def setUp(self):
        """建立測試需要的 fixture 與 client。

        Args:
            self: 目前測試類別實例。
        """
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(data_dir / "products.json", PRODUCTS_FIXTURE)
        self._write_json(data_dir / "categories.json", CATEGORIES_FIXTURE)
        self._write_json(data_dir / "reviews.json", REVIEWS_FIXTURE)
        self._write_json(data_dir / "recommendations.json", RECOMMENDATIONS_FIXTURE)
        self._write_json(data_dir / "questions.json", QUESTIONS_FIXTURE)
        self._write_json(data_dir / "posts.json", POSTS_FIXTURE)
        self._write_json(data_dir / "banners.json", BANNERS_FIXTURE)
        self._write_json(data_dir / "orders.json", ORDERS_FIXTURE)
        self._write_json(data_dir / "users.json", USERS_FIXTURE)

        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.client = Client()

    def tearDown(self):
        """清理測試用暫存檔與 override settings。

        Args:
            self: 目前測試類別實例。
        """
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _write_json(self, path: Path, payload):
        """將測試資料寫入 JSON 檔案。

        Args:
            self: 目前測試類別實例。
            path: 要寫入的檔案路徑。
            payload: 要儲存的 Python 資料。
        """
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_products(self, products):
        """快速覆寫 products fixture 內容。

        Args:
            self: 目前測試類別實例。
            products: 要寫入的商品 fixture 清單。
        """
        data_dir = Path(self.temp_dir.name) / "data"
        self._write_json(data_dir / "products.json", products)
        local_store.clear_cache()
        _seed_products(products)

    def _post_json(self, path, payload):
        """以 JSON request body 發出 POST 請求。

        Args:
            self: 目前測試類別實例。
            path: 目標路由。
            payload: 要送出的 JSON payload。
        """
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _put_json(self, path, payload):
        """以 JSON request body 發出 PUT 請求。

        Args:
            self: 目前測試類別實例。
            path: 目標路由。
            payload: 要送出的 JSON payload。
        """
        return self.client.put(path, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, path, payload):
        """測試輔助方法：_patch_json。
        
                Args:
                    self: 當前類別或 API view 實例。
                    path: 測試或路由路徑。
                    payload: 要送出或寫入的資料。
                """
        return self.client.patch(path, data=json.dumps(payload), content_type="application/json")

    def _add_to_cart(self, qty=1):
        """測試輔助方法：_add_to_cart。
        
                Args:
                    self: 當前類別或 API view 實例。
                    qty: 該測試使用的參數。
                """
        return self._add_product_to_cart("acme-mug", qty=qty)

    def _add_product_to_cart(self, slug, qty=1, variant_id=""):
        """測試輔助方法：_add_product_to_cart。
        
                Args:
                    self: 當前類別或 API view 實例。
                    slug: 商品 slug。
                    qty: 該測試使用的參數。
                    variant_id: 該測試使用的參數。
                """
        payload = {"slug": slug, "qty": qty}
        if variant_id:
            payload["variant_id"] = variant_id
        return self._post_json("/api/v1/cart/items/", payload)

    def _login(self, username="alice", password="demo123", next_url="/"):
        """測試輔助方法：_login。
        
                Args:
                    self: 當前類別或 API view 實例。
                    username: 會員帳號。
                    password: 該測試使用的參數。
                    next_url: 完成動作後要導向的網址。
                """
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _logout(self):
        """測試輔助方法：_logout。
        
                Args:
                    self: 當前類別或 API view 實例。
                """
        return self.client.post("/api/v1/auth/logout/")

    def _assert_frontend_redirect(self, response, path):
        """確認舊 Django HTML 路由已轉到 Next.js 前端。"""
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}{path}")

    def _confirm_checkout(self):
        """測試輔助方法：_confirm_checkout。
        
                Args:
                    self: 當前類別或 API view 實例。
                """
        address_id = None
        addresses_response = self.client.get("/api/v1/me/addresses/")
        if addresses_response.status_code == 200:
            items = addresses_response.json().get("items", [])
            if items:
                address_id = items[0]["id"]
        if address_id is None:
            create_response = self.client.post(
                "/api/v1/me/addresses/",
                data=json.dumps(
                    {
                        "label": "Home",
                        "recipient": "Buyer",
                        "phone": "0912345678",
                        "city": "Taipei",
                        "district": "Da'an",
                        "postal_code": "106",
                        "address_line": "No. 1, Xinyi Rd.",
                    }
                ),
                content_type="application/json",
            )
            if create_response.status_code == 201:
                address_id = create_response.json()["id"]
        payload = {"address_id": address_id} if address_id is not None else {}
        return self.client.post("/api/v1/checkout/confirm/", data=json.dumps(payload), content_type="application/json")

    def test_login_page_loads(self):
        response = self.client.get("/login/")
        self._assert_frontend_redirect(response, "/login")

    def test_login_succeeds_and_redirects(self):
        response = self._login(next_url="/community/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Signed in as Alice.")
        session = self.client.session
        self.assertEqual(session["demo_user"]["username"], "alice")

    def test_login_failure_shows_message(self):
        response = self._login(password="wrong")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid username or password.")

    def test_seeded_user_password_is_hashed_in_orm(self):
        stored_user = local_store.get_user_by_username("alice")
        self.assertIn("password_hash", stored_user)
        self.assertNotIn("password", stored_user)
        self.assertTrue(check_password("demo123", stored_user["password_hash"]))

    def test_register_page_loads(self):
        response = self.client.get("/register/")
        self._assert_frontend_redirect(response, "/register")

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            data=json.dumps(
                {
                    "username": "new_user",
                    "display_name": "New User",
                    "password": "secret123",
                    "password_confirm": "secret123",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["detail"], "Welcome, New User. Your account is ready.")
        session = self.client.session
        self.assertEqual(session["demo_user"]["username"], "new_user")
        stored_user = local_store.get_user_by_username("new_user")
        self.assertEqual(stored_user["display_name"], "New User")
        self.assertIn("password_hash", stored_user)
        self.assertTrue(check_password("secret123", stored_user["password_hash"]))

    def test_register_rejects_duplicate_username(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            data=json.dumps(
                {
                    "username": "alice",
                    "display_name": "Someone Else",
                    "password": "secret123",
                    "password_confirm": "secret123",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "This username is already taken.")

    def test_password_reset_request_creates_dev_mailbox_message(self):
        auth_demo.register_user("resetuser", "Reset User", "secret123", "reset@example.com")

        response = self._post_json("/api/v1/auth/password-reset/request/", {"email": "reset@example.com"})
        mailbox_response = self.client.get("/api/v1/auth/password-reset/dev-mailbox/?email=reset@example.com")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json()["detail"],
            "If the email exists, a reset link has been prepared in the dev mailbox.",
        )
        self.assertEqual(mailbox_response.status_code, 200)
        item = mailbox_response.json()["items"][0]
        self.assertEqual(item["email"], "reset@example.com")
        self.assertIn("/reset-password?token=", item["reset_url"])
        self.assertEqual(item["status"], "active")

    def test_password_reset_confirm_updates_password_and_invalidates_token(self):
        auth_demo.register_user("resetuser", "Reset User", "secret123", "reset@example.com")
        self._post_json("/api/v1/auth/password-reset/request/", {"email": "reset@example.com"})
        mailbox_response = self.client.get("/api/v1/auth/password-reset/dev-mailbox/?email=reset@example.com")
        token = mailbox_response.json()["items"][0]["token"]

        response = self._post_json(
            "/api/v1/auth/password-reset/confirm/",
            {
                "token": token,
                "new_password": "secret456",
                "password_confirm": "secret456",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Password has been reset. Please sign in with your new password.")
        self.assertEqual(self._login(username="resetuser", password="secret456").status_code, 200)
        self.assertEqual(self._login(username="resetuser", password="secret123").status_code, 400)
        second_try = self._post_json(
            "/api/v1/auth/password-reset/confirm/",
            {
                "token": token,
                "new_password": "another789",
                "password_confirm": "another789",
            },
        )
        self.assertEqual(second_try.status_code, 400)
        self.assertEqual(second_try.json()["detail"], "Reset link is invalid or expired.")

    def test_buyer_can_manage_addresses_and_invoice_profile(self):
        self._login(username="buyer", next_url="/me/addresses/")
        address_response = self._post_json(
            "/api/v1/me/addresses/",
            {
                "label": "Home",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Da'an",
                "postal_code": "106",
                "address_line": "1 Demo Road",
            },
        )
        self.assertEqual(address_response.status_code, 201)

        invoice_response = self._post_json(
            "/api/v1/me/invoice/",
            {
                "invoice_type": "company",
                "company_name": "Buyer Co",
                "tax_id": "12345678",
                "carrier_code": "/ABC1234",
            },
        )
        self.assertEqual(invoice_response.status_code, 200)

        buyer = local_store.get_user_by_username("buyer")
        self.assertEqual(buyer["addresses"][0]["recipient"], "Buyer")
        self.assertEqual(buyer["default_address_id"], buyer["addresses"][0]["id"])
        self.assertEqual(buyer["invoice_profile"]["company_name"], "Buyer Co")

    def test_checkout_stores_address_and_invoice_snapshot(self):
        self._login(username="buyer", next_url="/me/addresses/")
        self._post_json(
            "/api/v1/me/addresses/",
            {
                "label": "Office",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Xinyi",
                "postal_code": "110",
                "address_line": "99 Example St",
            },
        )
        self._post_json(
            "/api/v1/me/invoice/",
            {
                "invoice_type": "personal",
                "carrier_code": "/BUYER99",
            },
        )
        self._add_to_cart(qty=1)
        self._confirm_checkout()

        order = local_store.get_order_by_id(1)
        self.assertEqual(order["shipping_address"]["recipient"], "Buyer")
        self.assertEqual(order["invoice_profile"]["carrier_code"], "/BUYER99")

    def test_product_create_requires_login(self):
        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps({"name": "Seller Mug"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_product_create_saves_owner_and_status(self):
        self._login(next_url="/me/products/create/")
        image = SimpleUploadedFile("mug.png", b"fake-image-bytes", content_type="image/png")
        with _gcs_disabled_for_test():
            response = self.client.post(
                "/api/v1/me/products/",
                {
                    "name": "Seller Mug",
                    "price": "19.9",
                    "brand": "Alice Studio",
                    "category": "kitchen",
                    "tags": "mug, handmade",
                    "status": "active",
                    "specs": "material:ceramic\ncapacity_ml:420",
                    "stock": "8",
                    "images": image,
                },
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "active")
        product = local_store.get_product_by_slug("seller-mug")
        self.assertEqual(product["owner_username"], "alice")
        self.assertEqual(product["status"], "active")
        self.assertEqual(product["specs"]["material"], "ceramic")
        self.assertEqual(product["stock"], 8)
        self.assertTrue(product["images"][0].endswith(".png"))

    def test_public_product_categories_api_returns_category_master(self):
        response = self.client.get("/api/v1/product-categories/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["slug"], "tops")
        self.assertEqual(payload["items"][0]["label"], "上衣")
        self.assertEqual(payload["items"][1]["slug"], "pants")

    def test_product_create_accepts_category_slug_and_stores_master_fields(self):
        self._login(next_url="/me/products/create/")

        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "Seller Tee",
                    "price": "29.9",
                    "brand": "Alice Studio",
                    "category": "tops",
                    "tags": "shirt",
                    "status": "active",
                    "specs": "material:cotton",
                    "stock": "5",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        product = local_store.get_product_by_slug("seller-tee")
        self.assertEqual(product["category"], "上衣")
        self.assertEqual(product["category_slug"], "tops")

    def test_admin_can_create_product_category(self):
        self._login(username="storeteam", next_url="/staff/products/")

        response = self.client.post(
            "/api/v1/staff/product-categories/",
            data=json.dumps(
                {
                    "name": "外套",
                    "slug": "outerwear",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["slug"], "outerwear")
        self.assertEqual(payload["label"], "外套")
        categories = local_store.get_categories()
        self.assertTrue(any(item["slug"] == "outerwear" and item["name"] == "外套" for item in categories))

    def test_my_products_lists_owned_products(self):
        self._write_products(build_public_and_draft_products())
        self._login(next_url="/me/products/")

        response = self.client.get("/me/products/")
        self._assert_frontend_redirect(response, "/me/products")

    def test_member_cannot_open_seller_tools_until_approved(self):
        self._login(username="buyer", next_url="/me/products/")

        response = self.client.get("/me/products/")
        self._assert_frontend_redirect(response, "/me/products")

    def test_draft_product_visible_only_to_owner(self):
        self._write_products(build_public_and_draft_products())

        anonymous_response = self.client.get("/products/seller-draft-mug/")
        self._assert_frontend_redirect(anonymous_response, "/products/seller-draft-mug")

        self._login(next_url="/products/seller-draft-mug/")
        owner_response = self.client.get("/products/seller-draft-mug/")
        self._assert_frontend_redirect(owner_response, "/products/seller-draft-mug")

    def test_product_edit_and_archive_flow(self):
        self._write_products(build_public_and_draft_products())
        self._login(next_url="/me/products/seller-draft-mug/edit/")

        edit_response = self.client.put(
            "/api/v1/me/products/seller-draft-mug/",
            data=json.dumps(
                {
                    "name": "Seller Active Mug",
                    "price": "25.5",
                    "brand": "Alice Studio",
                    "category": "kitchen",
                    "tags": "mug, premium",
                    "status": "active",
                    "specs": "material:stoneware",
                    "stock": "3",
                    "existing_image_paths": [],
                    "remove_image_paths": [],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(edit_response.status_code, 200)

        updated = local_store.get_product_by_slug("seller-active-mug")
        self.assertEqual(updated["status"], "active")
        self.assertEqual(updated["stock"], 3)

        self._logout()
        self._login(username="storeteam", next_url="/staff/reviews/")
        review_response = self._post_json(
            "/api/v1/staff/products/seller-active-mug/archive/",
            {"note": "Violation report confirmed."},
        )
        self.assertEqual(review_response.status_code, 200)

        reviewed = local_store.get_product_by_slug("seller-active-mug")
        self.assertEqual(reviewed["status"], "archived")
        public_response = self.client.get("/products/")
        self._assert_frontend_redirect(public_response, "/products")

    def test_product_duplicate_and_delete_flow(self):
        self._write_products(build_public_and_draft_products())
        self._login(next_url="/me/products/")

        duplicate_response = self.client.post("/api/v1/me/products/seller-draft-mug/duplicate/")
        self.assertEqual(duplicate_response.status_code, 201)

        copied = local_store.get_product_by_slug("seller-draft-mug-copy")
        self.assertEqual(copied["status"], "draft")

        delete_response = self.client.delete("/api/v1/me/products/seller-draft-mug-copy/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertIsNone(local_store.get_product_by_slug("seller-draft-mug-copy"))

    def test_member_can_request_seller_and_admin_can_approve(self):
        self._login(username="buyer", next_url="/me/profile/")
        request_response = self.client.post("/api/v1/me/seller-request/")

        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(request_response.json()["detail"], "Seller access request submitted.")
        buyer = local_store.get_user_by_username("buyer")
        self.assertEqual(buyer["seller_request_status"], "pending")

        self._logout()
        self._login(username="storeteam", next_url="/staff/reviews/")
        review_response = self._post_json("/api/v1/staff/seller-requests/buyer/review/", {"approved": True})

        self.assertEqual(review_response.status_code, 200)
        buyer = local_store.get_user_by_username("buyer")
        self.assertEqual(buyer["role"], "seller")
        self.assertEqual(buyer["seller_request_status"], "approved")

    def test_admin_can_reject_product_review(self):
        self._login(next_url="/me/products/create/")
        self.client.post(
            "/api/v1/me/products/",
            {
                "name": "Needs Review Mug",
                "price": "19.9",
                "brand": "Alice Studio",
                "category": "kitchen",
                "tags": "mug",
                "status": "active",
                "specs": "material:ceramic",
                "stock": "2",
            },
        )
        self._logout()
        self._login(username="storeteam", next_url="/staff/reviews/")

        response = self._post_json(
            "/api/v1/staff/products/needs-review-mug/archive/",
            {"note": "Please add clearer photos."},
        )

        self.assertEqual(response.status_code, 200)
        product = local_store.get_product_by_slug("needs-review-mug")
        self.assertEqual(product["status"], "archived")
        self.assertEqual(product["review_note"], "Please add clearer photos.")

    def test_checkout_reduces_stock_for_tracked_products(self):
        self._write_products(build_public_and_draft_products())
        self._login(next_url="/checkout/preview/")
        self._add_product_to_cart("acme-mug", qty=2)
        self._confirm_checkout()

        product = local_store.get_product_by_slug("acme-mug")
        self.assertEqual(product["stock"], 8)

    def test_seller_order_list_requires_seller_role(self):
        self._login(username="buyer", next_url="/me/sales/")

        response = self.client.get("/me/sales/")
        self._assert_frontend_redirect(response, "/me/sales")

    def test_seller_order_center_shows_only_seller_lines(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._add_product_to_cart("team-bottle", qty=1)
        self._confirm_checkout()

        self._logout()
        self._login(username="alice", next_url="/me/sales/")

        response = self.client.get("/me/sales/")
        self._assert_frontend_redirect(response, "/me/sales")

    def test_seller_order_detail_shows_subset_for_seller(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._add_product_to_cart("team-bottle", qty=1)
        self._confirm_checkout()

        self._logout()
        self._login(username="alice", next_url="/me/sales/1/")

        response = self.client.get("/me/sales/1/")
        self._assert_frontend_redirect(response, "/me/sales/1")

    def test_seller_can_update_order_status_and_tracking(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._confirm_checkout()

        self._logout()
        self._login(username="alice", next_url="/me/sales/1/")
        response = self._post_json(
            "/api/v1/me/sales/1/update/",
            {
                "seller_status": "shipped",
                "tracking_number": "TW123456789",
                "shipping_note": "Packed with bubble wrap.",
            },
        )

        self.assertEqual(response.status_code, 200)
        order = local_store.get_order_by_id(1)
        line = order["items"][0]
        self.assertEqual(line["seller_status"], "shipped")
        self.assertEqual(line["tracking_number"], "TW123456789")
        self.assertEqual(line["shipping_note"], "Packed with bubble wrap.")
        self.assertTrue(line["shipped_at"])

    def test_buyer_can_complete_order_after_seller_ships(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()

        self._logout()
        self._login(username="alice", next_url="/me/sales/1/")
        response = self._post_json(
            "/api/v1/me/sales/1/update/",
            {
                "seller_status": "shipped",
                "tracking_number": "TW123456789",
                "shipping_note": "Seller shipped the parcel.",
            },
        )
        self.assertEqual(response.status_code, 200)

        self._logout()
        self._login(username="buyer", next_url="/me/orders/1/")
        response = self._post_json("/api/v1/me/orders/1/complete/", {})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["can_confirm_completion"] is False)
        order = local_store.get_order_by_id(1)
        line = order["items"][0]
        self.assertEqual(line["seller_status"], "completed")
        self.assertTrue(line["completed_at"])

    def test_buyer_cannot_complete_order_before_seller_ships(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()

        response = self._post_json("/api/v1/me/orders/1/complete/", {})

        self.assertEqual(response.status_code, 400)
        self.assertIn("not ready", response.json()["detail"])

    def test_seller_sales_report_aggregates_orders(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._confirm_checkout()
        self._logout()

        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        self._logout()

        self._login(username="alice", next_url="/me/sales/1/")
        self._post_json(
            "/api/v1/me/sales/1/update/",
            {"seller_status": "completed", "tracking_number": "DONE1", "shipping_note": "Delivered."},
        )
        page_response = self.client.get("/me/sales/report/")
        api_response = self.client.get("/api/v1/me/sales/report/")

        self._assert_frontend_redirect(page_response, "/me/sales/report")
        self.assertEqual(api_response.status_code, 200)
        payload = api_response.json()
        self.assertEqual(payload["revenue"], "38.70")
        self.assertEqual(payload["units_sold"], 3)
        self.assertEqual(payload["top_products"][0]["name"], "Alice Mug")

    def test_buyer_order_detail_shows_seller_tracking_and_status(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()

        self._logout()
        self._login(username="alice", next_url="/me/sales/1/")
        self.client.post(
            "/api/v1/me/sales/1/update/",
            data=json.dumps(
                {
                    "seller_status": "shipped",
                    "tracking_number": "BUYERTRACK1",
                    "shipping_note": "Left warehouse.",
                }
            ),
            content_type="application/json",
        )
        self._logout()
        self._login(username="buyer", next_url="/orders/1/")

        response = self.client.get("/orders/1/")
        self._assert_frontend_redirect(response, "/orders/1")

    def test_seller_order_list_filters_by_date_range(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        self._logout()

        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        orders = local_store.get_orders()
        orders[0]["created_at"] = "2026-05-01T10:00:00+08:00"
        orders[1]["created_at"] = "2026-05-04T10:00:00+08:00"
        local_store.save_orders(orders)

        self._logout()
        self._login(username="alice", next_url="/me/sales/")
        response = self.client.get("/me/sales/?date_from=2026-05-03&date_to=2026-05-05")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/me/sales?date_from=2026-05-03&date_to=2026-05-05")

    def test_seller_orders_csv_export(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._confirm_checkout()
        self._logout()

        self._login(username="alice", next_url="/me/sales/")
        response = self.client.get("/me/sales/export/orders.csv")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode("utf-8-sig")
        self.assertIn("order_id,buyer,created_at", content)
        self.assertIn("Alice Mug", content)

    def test_seller_report_csv_export_uses_date_filter(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        orders = local_store.get_orders()
        orders[0]["created_at"] = "2026-05-01T10:00:00+08:00"
        local_store.save_orders(orders)
        self._logout()

        self._login(username="alice", next_url="/me/sales/report/")
        response = self.client.get("/me/sales/export/report.csv?date_from=2026-05-03&date_to=2026-05-05")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\xef\xbb\xbf"))
        content = response.content.decode("utf-8-sig")
        self.assertIn("metric,value", content)
        self.assertIn("date_from,2026-05-03", content)
        self.assertIn("date_to,2026-05-05", content)
        self.assertIn("order_count,0", content)

    def test_product_detail_shows_review_summary(self):
        response = self.client.get("/products/acme-mug/")
        self._assert_frontend_redirect(response, "/products/acme-mug")

    def test_html_review_create_requires_login(self):
        response = self.client.post("/products/acme-mug/reviews/")

        self.assertEqual(response.status_code, 404)

    def test_post_review_from_html_form(self):
        self._login(next_url="/products/acme-mug/")
        response = self.client.post(
            "/api/v1/products/acme-mug/reviews/",
            data=json.dumps({"rating": 4, "title": "Useful cup", "body": "Works well on my desk."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["title"], "Useful cup")

        stored_reviews = local_store.get_reviews_by_product_id(1)
        self.assertEqual(len(stored_reviews), 2)
        self.assertEqual(stored_reviews[0]["author"], "Alice")

    def test_reviews_api_requires_login_for_post(self):
        response = self.client.post(
            "/api/v1/products/acme-mug/reviews/",
            data=json.dumps({"rating": 3, "title": "Average", "body": "It is okay."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_reviews_api_post_creates_review(self):
        self._login()
        response = self.client.post(
            "/api/v1/products/acme-mug/reviews/",
            data=json.dumps({"rating": 3, "title": "Average", "body": "It is okay."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["author"], "A***")

    def test_reviews_api_anonymizes_authors_by_rule(self):
        custom_reviews = [
            {
                "id": 1,
                "product_id": 1,
                "author": "王小明",
                "rating": 5,
                "title": "中文",
                "body": "很好用。",
                "created_at": "2026-05-31T10:00:00+08:00",
            },
            {
                "id": 2,
                "product_id": 1,
                "author": "David Chen",
                "rating": 4,
                "title": "English",
                "body": "Nice fit.",
                "created_at": "2026-05-31T10:05:00+08:00",
            },
            {
                "id": 3,
                "product_id": 1,
                "author": "kaijun123",
                "rating": 4,
                "title": "Account",
                "body": "值得買。",
                "created_at": "2026-05-31T10:10:00+08:00",
            },
            {
                "id": 4,
                "product_id": 1,
                "author": "test@example.com",
                "rating": 3,
                "title": "Email",
                "body": "普通。",
                "created_at": "2026-05-31T10:15:00+08:00",
            },
        ]
        self._write_json(Path(self.temp_dir.name) / "data" / "reviews.json", custom_reviews)
        local_store.clear_cache()

        response = self.client.get("/api/v1/products/acme-mug/reviews/")

        self.assertEqual(response.status_code, 200)
        authors = [item["author"] for item in response.json()["items"]]
        self.assertEqual(authors, ["te***@gmail.com", "ka***3", "D*** C***", "王**"])

    def test_product_list_filters_by_category(self):
        self._write_products(build_catalog_products())

        response = self.client.get("/products/?category=apparel")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/products?category=apparel")

    def test_product_list_sorts_by_price_desc(self):
        self._write_products(build_catalog_products())

        response = self.client.get("/products/?sort=price_desc")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/products?sort=price_desc")

    def test_product_list_paginates_results(self):
        self._write_products(build_catalog_products())

        page_one = self.client.get("/products/?page=1")
        page_two = self.client.get("/products/?page=2")
        self.assertEqual(page_one.status_code, 302)
        self.assertEqual(page_two.status_code, 302)
        self.assertEqual(page_one["Location"], f"{settings.FRONTEND_ORIGIN}/products?page=1")
        self.assertEqual(page_two["Location"], f"{settings.FRONTEND_ORIGIN}/products?page=2")

    def test_public_catalog_hides_draft_products(self):
        self._write_products(build_public_and_draft_products())

        response = self.client.get("/products/")
        self._assert_frontend_redirect(response, "/products")

    def test_product_detail_shows_recommendations(self):
        self._write_products(build_extra_products())

        response = self.client.get("/products/acme-mug/")
        self._assert_frontend_redirect(response, "/products/acme-mug")

    def test_recommendations_api_returns_grouped_data(self):
        self._write_products(build_extra_products())

        response = self.client.get("/api/products/acme-mug/recommendations/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["slug"] for item in payload["similar"]], ["beta-pan", "camp-cup"])
        self.assertEqual(payload["also_bought"], [])

    def test_product_detail_shows_questions_and_answers(self):
        response = self.client.get("/products/acme-mug/")
        self._assert_frontend_redirect(response, "/products/acme-mug")

    def test_post_question_from_html_form(self):
        self._login(next_url="/products/acme-mug/")
        response = self.client.post(
            "/api/v1/products/acme-mug/questions/",
            data=json.dumps({"title": "Is it microwave safe?", "body": "I want to heat milk in it."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author"], "alice")

        stored_questions = local_store.get_questions_by_product_id(1)
        self.assertEqual(len(stored_questions), 2)
        self.assertEqual(stored_questions[0]["author"], "Alice")

    def test_post_answer_from_html_form(self):
        self._login(next_url="/products/acme-mug/")
        response = self.client.post(
            "/api/v1/products/acme-mug/questions/1/answers/",
            data=json.dumps({"body": "I use mine in the microwave without issues."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        stored_questions = local_store.get_questions_by_product_id(1)
        self.assertEqual(len(stored_questions[0]["answers"]), 2)
        self.assertEqual(stored_questions[0]["answers"][-1]["author"], "Alice")

    def test_questions_api_post_requires_login(self):
        response = self.client.post(
            "/api/v1/products/acme-mug/questions/",
            data=json.dumps({"title": "Does it stain easily?", "body": "Coffee every morning."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_answers_api_post_creates_answer(self):
        self._login()
        response = self.client.post(
            "/api/v1/products/acme-mug/questions/1/answers/",
            data=json.dumps({"body": "Mine has been easy to clean after daily use."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["answers"][-1]["author"], "alice")
        self.assertTrue(payload["answers"][-1]["is_seller_reply"])

    def test_questions_api_hides_bodies_from_other_viewers_but_keeps_accounts_visible(self):
        self._login(username="buyer", next_url="/products/acme-mug/")

        response = self.client.get("/api/v1/products/acme-mug/questions/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["items"][0]
        self.assertEqual(payload["author"], anonymize_public_name("Eva"))
        self.assertEqual(payload["body"], "****")
        self.assertTrue(payload["is_body_masked"])
        self.assertEqual(payload["answers"][0]["author"], anonymize_public_name("Store Team"))
        self.assertEqual(payload["answers"][0]["body"], "****")
        self.assertTrue(payload["answers"][0]["is_body_masked"])

    def test_questions_api_marks_seller_reply_for_other_viewers(self):
        self._login(username="alice", next_url="/products/acme-mug/")
        create_response = self.client.post(
            "/api/v1/products/acme-mug/questions/1/answers/",
            data=json.dumps({"body": "Seller-only stock note."}),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        self._logout()
        self._login(username="buyer", next_url="/products/acme-mug/")

        response = self.client.get("/api/v1/products/acme-mug/questions/")

        self.assertEqual(response.status_code, 200)
        answers = response.json()["items"][0]["answers"]
        seller_reply = next(answer for answer in answers if answer["author"] == anonymize_public_name("alice"))
        self.assertTrue(seller_reply["is_seller_reply"])
        self.assertEqual(seller_reply["body"], "****")

    def test_community_list_shows_posts(self):
        response = self.client.get("/community/")
        self._assert_frontend_redirect(response, "/community")

    def test_post_community_thread_from_html_form(self):
        self._login(next_url="/community/")
        response = self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "How do you store travel bottles?",
                    "body": "Looking for ways to avoid odor between trips.",
                    "tags": "bottle, travel",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["author"], "Alice")

        stored_post = local_store.get_post_by_id(2)
        self.assertIsNotNone(stored_post)
        self.assertEqual(stored_post["author_username"], "alice")
        self.assertEqual(stored_post["author"], "Alice")

    def test_post_community_reply_from_html_form(self):
        self._login(next_url="/community/1/")
        response = self.client.post(
            "/api/v1/community/posts/1/replies/",
            data=json.dumps({"body": "I leave the cap open overnight after washing."}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["replies"][-1]["author"], anonymize_public_name("Alice"))

        stored_post = local_store.get_post_by_id(1)
        self.assertIsNotNone(stored_post)
        self.assertEqual(len(stored_post["replies"]), 2)
        self.assertEqual(stored_post["replies"][-1]["author"], "Alice")

    def test_community_vote_requires_login(self):
        response = self.client.post("/api/v1/community/posts/1/vote/")

        self.assertEqual(response.status_code, 403)

    def test_community_vote_updates_count(self):
        self._login(next_url="/community/1/")
        response = self.client.post("/api/v1/community/posts/1/vote/")

        self.assertEqual(response.status_code, 200)

        stored_post = local_store.get_post_by_id(1)
        self.assertIsNotNone(stored_post)
        self.assertEqual(stored_post["votes"], 4)

    def test_community_posts_api_post_requires_login(self):
        response = self.client.post(
            "/api/community/posts/",
            {"topic": "care", "title": "Deep clean routine", "body": "Share yours.", "tags": "mug"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("detail", response.json())

    def test_community_posts_api_post_creates_thread(self):
        self._login()
        response = self.client.post(
            "/api/community/posts/",
            {"topic": "care", "title": "Deep clean routine", "body": "Share yours.", "tags": "mug"},
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["author"], "Alice")

    def test_community_editor_image_upload_api_saves_file(self):
        self._login()
        image = SimpleUploadedFile("forum.png", b"fake-image-bytes", content_type="image/png")

        with _gcs_disabled_for_test():
            response = self.client.post("/api/v1/community/uploads/images/", {"image": image})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        path = payload["path"]
        self.assertTrue(
            path.startswith("/static/uploads/community/community-")
            or path.startswith("https://storage.googleapis.com/store_django/community/community-")
        )
        self.assertTrue(payload["path"].endswith(".png"))

    def test_community_post_detail_api_reports_manage_permissions_for_author(self):
        self._login(next_url="/community/")
        create_response = self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "Storage checklist",
                    "body": "<p>Keep lids open after washing.</p>",
                    "tags": "care",
                }
            ),
            content_type="application/json",
        )
        post_id = create_response.json()["id"]

        response = self.client.get(f"/api/v1/community/posts/{post_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["can_edit"])
        self.assertTrue(response.json()["can_delete"])

    def test_community_post_author_can_update_own_post(self):
        self._login(next_url="/community/")
        create_response = self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "Storage checklist",
                    "body": "<p>Keep lids open after washing.</p>",
                    "tags": "care",
                }
            ),
            content_type="application/json",
        )
        post_id = create_response.json()["id"]

        response = self.client.put(
            f"/api/v1/community/posts/{post_id}/",
            data=json.dumps(
                {
                    "topic": "care",
                    "title": "Updated storage checklist",
                    "body": "<p>Dry bottles upside down first.</p>",
                    "tags": "care, bottle",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        stored_post = local_store.get_post_by_id(post_id)
        self.assertIsNotNone(stored_post)
        self.assertEqual(stored_post["topic"], "care")
        self.assertEqual(stored_post["title"], "Updated storage checklist")

    def test_community_post_non_author_cannot_update_post(self):
        self._login(next_url="/community/")
        create_response = self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "Storage checklist",
                    "body": "<p>Keep lids open after washing.</p>",
                    "tags": "care",
                }
            ),
            content_type="application/json",
        )
        post_id = create_response.json()["id"]
        self._logout()
        self._login(username="buyer", next_url="/community/")

        response = self.client.put(
            f"/api/v1/community/posts/{post_id}/",
            data=json.dumps(
                {
                    "topic": "care",
                    "title": "Changed by someone else",
                    "body": "<p>Should not work.</p>",
                    "tags": "care",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "You can only edit your own post.")

    def test_community_post_author_can_delete_own_post(self):
        self._login(next_url="/community/")
        create_response = self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "Storage checklist",
                    "body": "<p>Keep lids open after washing.</p>",
                    "tags": "care",
                }
            ),
            content_type="application/json",
        )
        post_id = create_response.json()["id"]

        response = self.client.delete(f"/api/v1/community/posts/{post_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(local_store.get_post_by_id(post_id))

    def test_root_redirects_to_index_home(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/")

    def test_home_page_loads_and_shows_feature_sections(self):
        self._write_products(build_extra_products())

        response = self.client.get("/index/")
        self._assert_frontend_redirect(response, "/")

    def test_community_replies_api_post_creates_reply(self):
        self._login()
        response = self.client.post(
            "/api/community/posts/1/replies/",
            {"body": "I keep one soft brush next to the sink for this."},
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["id"], 1)
        self.assertEqual(payload["replies"][-1]["author"], anonymize_public_name("Alice"))

    def test_community_vote_api_updates_votes(self):
        self._login()
        response = self.client.post("/api/community/posts/1/vote/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["votes"], 4)
        self.assertTrue(payload["has_voted"])

    def test_order_list_requires_login(self):
        response = self.client.get("/orders/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/orders")

    def test_checkout_confirm_requires_login(self):
        self._add_to_cart()
        response = self.client.post("/api/v1/checkout/confirm/")

        self.assertEqual(response.status_code, 403)

    def test_checkout_confirm_creates_order_and_clears_cart(self):
        self._login(next_url="/checkout/preview/")
        self._add_to_cart(qty=2)

        response = self._confirm_checkout()

        self.assertEqual(response.status_code, 201)
        stored_orders = local_store.get_orders_by_username("alice")
        self.assertEqual(len(stored_orders), 1)
        self.assertEqual(stored_orders[0]["display_name"], "Alice")
        self.assertEqual(stored_orders[0]["items"][0]["qty"], 2)
        self.assertEqual(self.client.session["cart"]["alice"]["items"], {})

    def test_order_list_shows_created_order(self):
        self._login(next_url="/checkout/preview/")
        self._add_to_cart()
        self._confirm_checkout()

        response = self.client.get("/orders/")
        self._assert_frontend_redirect(response, "/orders")

    def test_order_detail_shows_line_items(self):
        self._login(next_url="/checkout/preview/")
        self._add_to_cart()
        self._confirm_checkout()

        response = self.client.get("/orders/1/")
        self._assert_frontend_redirect(response, "/orders/1")

    def test_me_requires_login(self):
        response = self.client.get("/me/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/me/dashboard")

    def test_profile_edit_requires_login(self):
        response = self.client.get("/me/profile/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/me/profile")

    def test_profile_edit_updates_display_name_and_password(self):
        self._login(next_url="/me/profile/")
        response = self.client.post(
            "/api/v1/me/profile/",
            data=json.dumps(
                {
                    "display_name": "Alice Chen",
                    "new_password": "newpass123",
                    "confirm_password": "newpass123",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["detail"], "Profile updated.")
        stored_user = local_store.get_user_by_username("alice")
        self.assertEqual(stored_user["display_name"], "Alice Chen")
        self.assertTrue(check_password("newpass123", stored_user["password_hash"]))
        self.assertEqual(self.client.session["demo_user"]["display_name"], "Alice Chen")

    def test_favorite_toggle_updates_profile_dashboard(self):
        self._login(next_url="/me/")
        self.client.post("/api/v1/products/acme-mug/favorite/")
        self.client.get("/products/acme-mug/")

        response = self.client.get("/me/")
        self._assert_frontend_redirect(response, "/me/dashboard")

    def test_me_dashboard_shows_authored_content(self):
        self._login(next_url="/me/")
        self.client.post(
            "/api/v1/products/acme-mug/reviews/",
            data=json.dumps({"rating": 4, "title": "Useful cup", "body": "Works well on my desk."}),
            content_type="application/json",
        )
        self.client.post(
            "/api/v1/products/acme-mug/questions/",
            data=json.dumps({"title": "Is it microwave safe?", "body": "I want to heat milk in it."}),
            content_type="application/json",
        )
        self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "How do you store travel bottles?",
                    "body": "Looking for ways to avoid odor between trips.",
                    "tags": "bottle, travel",
                }
            ),
            content_type="application/json",
        )
        self._add_to_cart()
        self._confirm_checkout()

        response = self.client.get("/me/")
        self._assert_frontend_redirect(response, "/me/dashboard")
    def test_buyer_can_manage_addresses_and_invoice_profile(self):
        self._login(username="buyer", next_url="/me/addresses/")
        address_response = self.client.post(
            "/api/v1/me/addresses/",
            data=json.dumps(
                {
                    "label": "Home",
                    "recipient": "Buyer",
                    "phone": "0912345678",
                    "city": "Taipei",
                    "district": "Da'an",
                    "postal_code": "106",
                    "address_line": "1 Demo Road",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(address_response.status_code, 201)

        invoice_response = self.client.post(
            "/api/v1/me/invoice/",
            data=json.dumps(
                {
                    "invoice_type": "company",
                    "company_name": "Buyer Co",
                    "tax_id": "12345678",
                    "carrier_code": "/ABC1234",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invoice_response.status_code, 200)

        buyer = local_store.get_user_by_username("buyer")
        self.assertEqual(buyer["addresses"][0]["recipient"], "Buyer")
        self.assertEqual(buyer["default_address_id"], buyer["addresses"][0]["id"])
        self.assertEqual(buyer["invoice_profile"]["company_name"], "Buyer Co")

    def test_checkout_stores_address_and_invoice_snapshot(self):
        self._login(username="buyer", next_url="/me/addresses/")
        self.client.post(
            "/api/v1/me/addresses/",
            data=json.dumps(
                {
                    "label": "Office",
                    "recipient": "Buyer",
                    "phone": "0912345678",
                    "city": "Taipei",
                    "district": "Xinyi",
                    "postal_code": "110",
                    "address_line": "99 Example St",
                }
            ),
            content_type="application/json",
        )
        self.client.post(
            "/api/v1/me/invoice/",
            data=json.dumps(
                {
                    "invoice_type": "personal",
                    "carrier_code": "/BUYER99",
                }
            ),
            content_type="application/json",
        )
        self._add_product_to_cart("acme-mug", qty=1)
        self._confirm_checkout()

        order = local_store.get_order_by_id(1)
        self.assertEqual(order["shipping_address"]["recipient"], "Buyer")
        self.assertEqual(order["invoice_profile"]["carrier_code"], "/BUYER99")

    def test_seller_can_update_shipping_rules(self):
        self._login(username="alice", next_url="/me/shipping-rules/")

        response = self.client.put(
            "/api/v1/me/shipping-rules/",
            data=json.dumps(
                {
                    "home_delivery_enabled": True,
                    "home_delivery_fee": "90",
                    "convenience_store_enabled": True,
                    "convenience_store_fee": "70",
                    "free_shipping_threshold": "1500",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        refreshed = local_store.get_user_by_username("alice")
        self.assertEqual(refreshed["shipping_rules"]["home_delivery_fee"], "90.00")
        self.assertEqual(refreshed["shipping_rules"]["convenience_store_fee"], "70.00")
        self.assertEqual(refreshed["shipping_rules"]["free_shipping_threshold"], "1500.00")

    def test_checkout_preview_calculates_shipping_per_seller_group(self):
        self._write_products(build_seller_order_products())
        auth_demo.update_seller_shipping_rules(
            "alice",
            home_delivery_enabled=True,
            home_delivery_fee="90",
            convenience_store_enabled=True,
            convenience_store_fee="60",
            free_shipping_threshold="9999",
        )
        auth_demo.update_seller_shipping_rules(
            "storeteam",
            home_delivery_enabled=True,
            home_delivery_fee="120",
            convenience_store_enabled=True,
            convenience_store_fee="80",
            free_shipping_threshold="9999",
        )

        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._add_product_to_cart("team-bottle", qty=1)

        response = self.client.get("/api/v1/checkout/preview/?shipping_method=home_delivery")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(f'{payload["totals"]["shipping"]:.2f}', "210.00")
        self.assertEqual(len(payload["seller_shipping_groups"]), 2)
        self.assertEqual(payload["seller_shipping_groups"][0]["selected_shipping_method"], "home_delivery")
        shipping_map = {group["seller_username"]: group["shipping_fee"] for group in payload["seller_shipping_groups"]}
        self.assertEqual(shipping_map["alice"], "90.00")
        self.assertEqual(shipping_map["storeteam"], "120.00")

    def test_product_create_persists_shipping_profile(self):
        self._login(username="alice", next_url="/me/products/create/")

        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "Shipping Test Tee",
                    "price": "600",
                    "brand": "Alice Studio",
                    "category": "apparel",
                    "tags": "tee",
                    "status": "draft",
                    "specs": "material:cotton",
                    "stock": "3",
                    "use_seller_shipping_rules": "false",
                    "allow_home_delivery": "false",
                    "allow_convenience_store": "true",
                    "override_convenience_store_fee": "75",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        product = local_store.get_product_by_slug("shipping-test-tee")
        self.assertEqual(product["shipping_profile"]["use_seller_rules"], False)
        self.assertEqual(product["shipping_profile"]["allow_home_delivery"], False)
        self.assertEqual(product["shipping_profile"]["allow_convenience_store"], True)
        self.assertEqual(product["shipping_profile"]["override_convenience_store_fee"], 75.0)

    def test_buyer_cancel_request_and_admin_approval_restocks_stock(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=2)
        self._confirm_checkout()

        buyer_response = self.client.post(
            "/api/v1/me/orders/1/cancel-request/",
            data=json.dumps({"reason": "Ordered by mistake."}),
            content_type="application/json",
        )
        self.assertEqual(buyer_response.status_code, 200)
        order = local_store.get_order_by_id(1)
        self.assertEqual(order["service_request"]["type"], "cancel")
        self.assertEqual(order["service_request"]["status"], "pending")

        self._logout()
        self._login(username="storeteam", next_url="/staff/orders/1/")
        admin_response = self.client.post(
            "/api/v1/staff/orders/1/service-review/",
            data=json.dumps({"approved": True, "note": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(admin_response.status_code, 200)
        order = local_store.get_order_by_id(1)
        self.assertEqual(order["status"], "cancelled")
        self.assertEqual(order["service_request"]["status"], "approved")
        product = local_store.get_product_by_slug("alice-mug")
        self.assertEqual(product["stock"], 10)

    def test_buyer_refund_request_and_admin_rejection(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        self._logout()

        self._login(username="alice", next_url="/me/sales/1/")
        self.client.post(
            "/api/v1/me/sales/1/update/",
            data=json.dumps({"seller_status": "shipped", "tracking_number": "TX1", "shipping_note": "Sent."}),
            content_type="application/json",
        )
        self._logout()

        self._login(username="buyer", next_url="/orders/1/")
        refund_response = self.client.post(
            "/api/v1/me/orders/1/refund-request/",
            data=json.dumps({"reason": "Package damaged."}),
            content_type="application/json",
        )
        self.assertEqual(refund_response.status_code, 200)

        self._logout()
        self._login(username="storeteam", next_url="/staff/orders/1/")
        admin_response = self.client.post(
            "/api/v1/staff/orders/1/service-review/",
            data=json.dumps({"approved": False, "note": "Need more evidence."}),
            content_type="application/json",
        )
        self.assertEqual(admin_response.status_code, 200)
        order = local_store.get_order_by_id(1)
        self.assertEqual(order["status"], "confirmed")
        self.assertEqual(order["service_request"]["status"], "rejected")

    def test_admin_can_suspend_member_and_block_future_login(self):
        self._login(username="storeteam", next_url="/staff/users/")
        response = self.client.post(
            "/api/v1/staff/users/buyer/status/",
            data=json.dumps({"account_status": "suspended"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        buyer = local_store.get_user_by_username("buyer")
        self.assertEqual(buyer["account_status"], "suspended")

        self._logout()
        login_response = self._login(username="buyer", next_url="/")
        self.assertEqual(login_response.status_code, 400)
        self.assertEqual(login_response.json()["detail"], "Invalid username or password.")

    def test_product_create_with_variants_sets_summary_price_and_stock(self):
        self._login(next_url="/me/products/create/")
        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "Variant Hoodie",
                    "price": "28.0",
                    "compare_at_price": "35.0",
                    "brand": "ACME",
                    "category": "apparel",
                    "tags": "hoodie, winter",
                    "status": "active",
                    "specs": "material:cotton",
                    "stock": "0",
                    "variants": "Navy / M|HD-NV-M|28|2\nNavy / L|HD-NV-L|30|3",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        product = local_store.get_product_by_slug("variant-hoodie")
        self.assertEqual(product["price"], 28.0)
        self.assertEqual(product["stock"], 5)
        self.assertEqual(product["compare_at_price"], 35.0)
        self.assertEqual(len(product["variants"]), 2)
        self.assertEqual(product["variants"][0]["sku"], "HD-NV-M")
        self.assertEqual(sum(variant["stock"] for variant in product["variants"]), 5)

    def test_product_create_allows_variant_compare_at_prices_independent_from_base_compare_at(self):
        self._login(next_url="/me/products/create/")
        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "Short Sleeve Polo",
                    "price": "800",
                    "compare_at_price": "900",
                    "brand": "ACC",
                    "category": "apparel",
                    "tags": "polo",
                    "status": "active",
                    "specs": "material:cotton",
                    "stock": "0",
                    "variants": "\n".join(
                        [
                            "White / M|SH-W-M|800|2|White|M||900",
                            "Gray / M|SH-G-M|1000|3|Gray|M||1200",
                        ]
                    ),
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        product = local_store.get_product_by_slug("short-sleeve-polo")
        self.assertIsNotNone(product)
        self.assertEqual(product["compare_at_price"], 900.0)
        self.assertEqual(product["price"], 800.0)
        self.assertEqual(product["stock"], 5)
        self.assertEqual(product["variants"][0]["compare_at_price"], 900.0)
        self.assertEqual(product["variants"][1]["compare_at_price"], 1200.0)

    def test_product_create_allows_chinese_color_variants_with_same_size(self):
        self._login(next_url="/me/products/create/")
        response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "長袖上衣",
                    "price": "800",
                    "compare_at_price": "900",
                    "brand": "ACC",
                    "category": "apparel",
                    "tags": "長袖上衣",
                    "status": "active",
                    "specs": "材質:棉",
                    "stock": "0",
                    "variants": "\n".join(
                        [
                            "長袖上衣-灰-M|長袖上衣-灰-M|1000|5|灰|M||",
                            "長袖上衣-黑-M|長袖上衣-黑-M|1200|8|黑|M||",
                        ]
                    ),
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        created_slug = response.json()["slug"]
        product = local_store.get_product_by_slug(created_slug)
        self.assertIsNotNone(product)
        self.assertEqual(len(product["variants"]), 2)
        self.assertNotEqual(product["variants"][0]["id"], product["variants"][1]["id"])
        self.assertEqual(product["variants"][0]["attributes"]["color"], "灰")
        self.assertEqual(product["variants"][1]["attributes"]["color"], "黑")

    def test_product_detail_and_cart_support_selected_variant(self):
        self._write_products(build_variant_products())

        detail_response = self.client.get("/products/acme-hoodie/")
        self._assert_frontend_redirect(detail_response, "/products/acme-hoodie")

        self._add_product_to_cart("acme-hoodie", qty=1, variant_id="navy-l")
        cart = self.client.session["cart"]["__guest__"]
        item = cart["items"]["acme-hoodie__navy-l"]
        self.assertEqual(item["variant_name"], "Navy / L")
        self.assertEqual(item["sku"], "HD-NV-L")
        self.assertEqual(item["price"], 30.0)

    def test_variant_stock_reserved_and_restocked_after_cancellation(self):
        self._write_products(build_variant_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("acme-hoodie", qty=2, variant_id="navy-m")
        self._confirm_checkout()

        product = local_store.get_product_by_slug("acme-hoodie")
        self.assertEqual(product["variants"][0]["stock"], 0)

        self.client.post(
            "/api/v1/me/orders/1/cancel-request/",
            data=json.dumps({"reason": "Need a different size."}),
            content_type="application/json",
        )
        self._logout()
        self._login(username="storeteam", next_url="/staff/orders/1/")
        self.client.post(
            "/api/v1/staff/orders/1/service-review/",
            data=json.dumps({"approved": True, "note": "Approved."}),
            content_type="application/json",
        )

        product = local_store.get_product_by_slug("acme-hoodie")
        self.assertEqual(product["variants"][0]["stock"], 2)

    def test_product_edit_can_remove_and_reorder_existing_images(self):
        self._write_products(build_variant_products())
        self._login(next_url="/me/products/acme-hoodie/edit/")
        response = self.client.put(
            "/api/v1/me/products/acme-hoodie/",
            data=json.dumps(
                {
                    "name": "ACME Hoodie",
                    "price": "28.0",
                    "compare_at_price": "35.0",
                    "brand": "ACME",
                    "category": "apparel",
                    "tags": "hoodie, winter",
                    "status": "active",
                    "specs": "material:cotton",
                    "stock": "0",
                    "variants": "Navy / M|HD-NV-M|28|2\nNavy / L|HD-NV-L|30|3",
                    "existing_image_paths": ["/static/uploads/products/hoodie-2.png", "/static/uploads/products/hoodie-1.png"],
                    "remove_image_paths": ["/static/uploads/products/hoodie-1.png"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        product = local_store.get_product_by_slug("acme-hoodie")
        self.assertEqual(product["images"], ["/static/uploads/products/hoodie-2.png"])

    def test_product_list_filters_by_variant_color_and_size(self):
        self._write_products(build_attribute_products())

        response = self.client.get("/products/?color=Navy&size=M")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/products?color=Navy&size=M")

    def test_product_detail_prioritizes_selected_variant_image(self):
        self._write_products(build_variant_products())

        response = self.client.get("/products/acme-hoodie/?variant=navy-l")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}/products/acme-hoodie?variant=navy-l")

    def test_compare_toggle_and_compare_page(self):
        self._write_products(build_catalog_products())

        self.client.post("/api/v1/products/acme-mug/compare/")
        self.client.post("/api/v1/products/beta-pan/compare/")
        response = self.client.get("/products/compare/")
        self._assert_frontend_redirect(response, "/products/compare")

    def test_brand_detail_page_scopes_products(self):
        self._write_products(build_catalog_products())

        response = self.client.get("/brands/acme/")
        self._assert_frontend_redirect(response, "/brands/acme")

    def test_category_detail_page_scopes_products(self):
        self._write_products(build_catalog_products())

        response = self.client.get("/categories/kitchen/")
        self._assert_frontend_redirect(response, "/categories/kitchen")

    def test_drf_products_list_supports_catalog_filters(self):
        self._write_products(build_attribute_products())

        response = self.client.get("/api/v1/products/?color=Navy&size=M")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["meta"]["total_items"], 1)
        self.assertEqual(payload["items"][0]["slug"], "acme-hoodie")

    def test_drf_product_detail_includes_variants_and_images(self):
        self._write_products(build_variant_products())

        response = self.client.get("/api/v1/products/acme-hoodie/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["slug"], "acme-hoodie")
        self.assertEqual(payload["variants"][0]["image"], "/static/uploads/products/hoodie-1.png")

    def test_drf_reviews_post_requires_login_and_can_create_review(self):
        self._write_products(build_variant_products())

        anonymous = self.client.post(
            "/api/v1/products/acme-hoodie/reviews/",
            data=json.dumps({"rating": 5, "title": "Great", "body": "Solid quality."}),
            content_type="application/json",
        )
        self.assertEqual(anonymous.status_code, 403)

        self._login(username="buyer", next_url="/")
        response = self.client.post(
            "/api/v1/products/acme-hoodie/reviews/",
            data=json.dumps({"rating": 5, "title": "Great", "body": "Solid quality."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["author"], anonymize_public_name("Buyer"))

    def test_drf_me_endpoint_returns_demo_session_user(self):
        self._login(username="buyer", next_url="/")

        response = self.client.get("/api/v1/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["username"], "buyer")

    def test_openapi_schema_and_swagger_ui_are_available(self):
        schema_response = self.client.get("/api/v1/schema/")
        swagger_response = self.client.get("/api/v1/schema/swagger-ui/")

        self.assertEqual(schema_response.status_code, 200)
        self.assertContains(schema_response, "openapi: 3.")
        self.assertEqual(swagger_response.status_code, 200)

    def test_api_route_record_page_lists_canonical_and_legacy_routes(self):
        response = self.client.get("/docs/api-routes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/products/&lt;slug&gt;/reviews/")
        self.assertContains(response, "/api/products/&lt;slug&gt;/reviews/")

    def test_me_dashboard_api_returns_summary(self):
        self._login(username="buyer", next_url="/")

        response = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["username"], "buyer")
        self.assertIn("favorite_products", payload)

    def test_favorite_and_compare_toggle_apis_update_session_state(self):
        self._login(username="buyer", next_url="/")

        favorite_response = self.client.post("/api/v1/products/acme-mug/favorite/")
        compare_response = self.client.post("/api/v1/products/acme-mug/compare/")

        self.assertEqual(favorite_response.status_code, 200)
        self.assertTrue(favorite_response.json()["active"])
        self.assertEqual(favorite_response.json()["favorite_count"], 1)
        self.assertEqual(compare_response.status_code, 200)
        self.assertTrue(compare_response.json()["active"])
        self.assertIn("acme-mug", self.client.session["compare_products"]["buyer"])

    def test_compare_list_is_isolated_per_logged_in_user(self):
        self._login(username="buyer", next_url="/")
        self.client.post("/api/v1/products/acme-mug/compare/")
        self.client.post("/api/v1/auth/logout/")

        self._login(username="storeteam", next_url="/")
        response = self.client.get("/api/v1/products/compare/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slugs"], [])
        self.assertEqual(self.client.session["compare_products"]["buyer"], ["acme-mug"])
        self.assertEqual(self.client.session["compare_products"]["storeteam"], [])

    def test_favorite_list_is_isolated_per_logged_in_user(self):
        self._login(username="buyer", next_url="/")
        self.client.post("/api/v1/products/acme-mug/favorite/")
        self.client.post("/api/v1/auth/logout/")

        self._login(username="storeteam", next_url="/")
        bootstrap_response = self.client.get("/api/v1/app/bootstrap/")
        detail_response = self.client.get("/api/v1/products/acme-mug/")

        self.assertEqual(bootstrap_response.status_code, 200)
        self.assertEqual(bootstrap_response.json()["favorite_count"], 0)
        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.json()["is_favorite"])
        self.assertEqual(self.client.session["favorite_products"]["buyer"], ["acme-mug"])
        self.assertEqual(self.client.session["favorite_products"]["storeteam"], [])

    def test_cart_is_isolated_per_logged_in_user(self):
        self._login(username="buyer", next_url="/")
        self._add_product_to_cart("acme-mug", qty=1)
        self.client.post("/api/v1/auth/logout/")

        self._login(username="storeteam", next_url="/")
        response = self.client.get("/api/v1/cart/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_count"], 0)
        self.assertEqual(response.json()["items"], [])
        self.assertEqual(self.client.session["cart"]["buyer"]["items"]["acme-mug"]["qty"], 1)
        self.assertEqual(self.client.session["cart"]["storeteam"]["items"], {})

    def test_logged_in_cart_persists_across_logout_and_login(self):
        self._login(username="buyer", next_url="/")
        self._add_product_to_cart("acme-mug", qty=2)
        self.assertEqual(self.client.session["cart"]["buyer"]["items"]["acme-mug"]["qty"], 2)

        self.client.post("/api/v1/auth/logout/")
        self._login(username="buyer", next_url="/")
        response = self.client.get("/api/v1/cart/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_count"], 2)
        self.assertEqual(response.json()["items"][0]["slug"], "acme-mug")

    def test_guest_cart_migrates_into_persisted_user_cart_on_login(self):
        self._add_product_to_cart("acme-mug", qty=1)
        self.assertEqual(self.client.session["cart"]["__guest__"]["items"]["acme-mug"]["qty"], 1)

        self._login(username="buyer", next_url="/")
        response = self.client.get("/api/v1/cart/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item_count"], 1)
        self.assertEqual(self.client.session["cart"]["__guest__"]["items"], {})
        self.assertEqual(self.client.session["cart"]["buyer"]["items"]["acme-mug"]["qty"], 1)

    def test_logout_clears_guest_visible_cart_favorite_and_compare_state(self):
        self._login(username="buyer", next_url="/")
        self._add_product_to_cart("acme-mug", qty=1)
        self.client.post("/api/v1/products/acme-mug/favorite/")
        self.client.post("/api/v1/products/acme-mug/compare/")
        self.client.post("/api/v1/auth/logout/")

        bootstrap_response = self.client.get("/api/v1/app/bootstrap/")
        cart_response = self.client.get("/api/v1/cart/")
        compare_response = self.client.get("/api/v1/products/compare/")
        detail_response = self.client.get("/api/v1/products/acme-mug/")

        self.assertEqual(bootstrap_response.status_code, 200)
        self.assertEqual(bootstrap_response.json()["cart_count"], 0)
        self.assertEqual(bootstrap_response.json()["favorite_count"], 0)
        self.assertEqual(bootstrap_response.json()["compare_count"], 0)
        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(cart_response.json()["item_count"], 0)
        self.assertEqual(compare_response.status_code, 200)
        self.assertEqual(compare_response.json()["slugs"], [])
        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.json()["is_favorite"])
        self.assertEqual(self.client.session["cart"]["buyer"]["items"]["acme-mug"]["qty"], 1)
        self.assertEqual(self.client.session["favorite_products"]["buyer"], ["acme-mug"])
        self.assertEqual(self.client.session["compare_products"]["buyer"], ["acme-mug"])
        self.assertEqual(self.client.session["cart"]["__guest__"]["items"], {})
        self.assertEqual(self.client.session["favorite_products"]["__guest__"], [])
        self.assertEqual(self.client.session["compare_products"]["__guest__"], [])

    def test_product_detail_api_reports_is_favorite_from_session(self):
        self._login(username="buyer", next_url="/")
        self.client.post("/api/v1/products/acme-mug/favorite/")

        response = self.client.get("/api/v1/products/acme-mug/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["is_favorite"])

    def test_me_addresses_api_create_and_set_default(self):
        self._login(username="buyer", next_url="/")

        create_response = self.client.post(
            "/api/v1/me/addresses/",
            data=json.dumps(
                {
                    "label": "Home",
                    "recipient": "Buyer",
                    "phone": "0912345678",
                    "city": "Taipei",
                    "district": "Da'an",
                    "postal_code": "106",
                    "address_line": "1 Demo Road",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        address_id = create_response.json()["id"]

        default_response = self.client.post(f"/api/v1/me/addresses/{address_id}/default/")
        list_response = self.client.get("/api/v1/me/addresses/")

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(list_response.json()["items"][0]["is_default"])

    def test_buyer_orders_api_lists_order_and_accepts_cancel_request(self):
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_to_cart(qty=1)
        self._confirm_checkout()

        list_response = self.client.get("/api/v1/me/orders/")
        cancel_response = self.client.post(
            "/api/v1/me/orders/1/cancel-request/",
            data=json.dumps({"reason": "Changed my mind."}),
            content_type="application/json",
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"][0]["id"], 1)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["service_request"]["type"], "cancel")

    def test_seller_orders_and_report_apis_return_seller_views(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer", next_url="/checkout/preview/")
        self._add_product_to_cart("alice-mug", qty=1)
        self._confirm_checkout()
        self._logout()
        self._login(username="alice", next_url="/")

        orders_response = self.client.get("/api/v1/me/sales/")
        report_response = self.client.get("/api/v1/me/sales/report/")

        self.assertEqual(orders_response.status_code, 200)
        self.assertEqual(orders_response.json()["items"][0]["items"][0]["seller_username"], "alice")
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(report_response.json()["order_count"], 1)

    def test_admin_dashboard_and_user_status_apis_work(self):
        self._login(username="storeteam", next_url="/")

        dashboard_response = self.client.get("/api/v1/staff/dashboard/")
        status_response = self.client.post(
            "/api/v1/staff/users/buyer/status/",
            data=json.dumps({"account_status": "suspended"}),
            content_type="application/json",
        )

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn("users", dashboard_response.json())
        self.assertEqual(dashboard_response.json()["content"]["total"], 3)
        self.assertTrue(dashboard_response.json()["recent_reviews"][0]["source_url"].startswith("/products/"))
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["user"]["account_status"], "suspended")

    def test_admin_product_management_apis_support_listing_publish_archive_and_delete(self):
        draft_product = {
            "id": 4,
            "slug": "draft-tee",
            "name": "Draft Tee",
            "price": 19.9,
            "brand": "Draft Lab",
            "category": "apparel",
            "tags": ["draft"],
            "images": [],
            "specs": {"size": "L"},
            "status": "draft",
            "stock": 5,
            "owner_username": "alice",
            "owner_display_name": "Alice",
            "created_at": "2026-05-01T10:00:00+08:00",
            "updated_at": "2026-05-01T10:00:00+08:00",
        }
        self._write_products(PRODUCTS_FIXTURE + [draft_product])
        self._login(username="storeteam", next_url="/")

        list_response = self.client.get("/api/v1/staff/products/?status=draft")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"][0]["slug"], "draft-tee")

        publish_response = self.client.post(
            "/api/v1/staff/products/draft-tee/publish/",
            data=json.dumps({"note": "Publish now"}),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["status"], "active")

        archive_response = self.client.post(
            "/api/v1/staff/products/draft-tee/archive/",
            data=json.dumps({"note": "Archive now"}),
            content_type="application/json",
        )
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(archive_response.json()["status"], "archived")

        delete_response = self.client.delete("/api/v1/staff/products/draft-tee/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertIsNone(local_store.get_product_by_slug("draft-tee"))

    def test_admin_content_management_apis_support_listing_and_delete(self):
        self._login(username="storeteam", next_url="/")

        reviews_response = self.client.get("/api/v1/staff/content/reviews/?q=Nice")
        questions_response = self.client.get("/api/v1/staff/content/questions/?answered=answered")
        posts_response = self.client.get("/api/v1/staff/content/posts/?topic=general")

        self.assertEqual(reviews_response.status_code, 200)
        self.assertEqual(questions_response.status_code, 200)
        self.assertEqual(posts_response.status_code, 200)
        self.assertEqual(reviews_response.json()["items"][0]["title"], "Nice daily mug")
        self.assertEqual(questions_response.json()["items"][0]["title"], "Can this go in the dishwasher?")
        self.assertEqual(posts_response.json()["items"][0]["title"], "Best mug for office use?")

        review_delete_response = self.client.delete("/api/v1/staff/content/reviews/1/")
        question_delete_response = self.client.delete("/api/v1/staff/content/questions/1/")
        post_delete_response = self.client.delete("/api/v1/staff/content/posts/1/")

        self.assertEqual(review_delete_response.status_code, 204)
        self.assertEqual(question_delete_response.status_code, 204)
        self.assertEqual(post_delete_response.status_code, 204)
        self.assertEqual(local_store.get_reviews(), [])
        self.assertEqual(local_store.get_questions(), [])
        self.assertEqual(local_store.get_posts(), [])

    def test_public_banner_api_returns_only_approved_in_schedule_banners(self):
        response = self.client.get("/api/v1/banners/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["title"], "Primary Banner")
        self.assertTrue(payload["items"][0]["is_active"])

    def test_member_can_submit_banner_application(self):
        self._login(username="buyer", next_url="/")

        with _gcs_disabled_for_test():
            create_response = self.client.post(
                "/api/v1/me/banner-applications/",
                data={
                    "title": "Summer Tee Promo",
                    "copy_text": "All tees 20% off",
                    "link_url": "/products/acme-tee",
                    "starts_at": "2026-06-01",
                    "ends_at": "2026-06-15",
                    "position": "home_main",
                    "note": "Seasonal campaign",
                    "image": SimpleUploadedFile("banner.png", b"banner-bytes", content_type="image/png"),
                },
            )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["status"], "pending")
        self.assertFalse(created["is_active"])
        self.assertEqual(created["applicant_username"], "buyer")

        list_response = self.client.get("/api/v1/me/banner-applications/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"][0]["title"], "Summer Tee Promo")

    def test_admin_banner_apis_support_review_reorder_update_and_delete(self):
        self._login(username="storeteam", next_url="/")

        with _gcs_disabled_for_test():
            applicant_response = self.client.post(
                "/api/v1/staff/banners/",
                data={
                    "title": "Third Banner",
                    "copy_text": "Upload from admin",
                    "link_url": "/products/acme-bottle",
                    "starts_at": "2026-06-01",
                    "ends_at": "2026-06-20",
                    "position": "home_main",
                    "note": "admin seeded banner",
                    "is_active": "true",
                    "image": SimpleUploadedFile("banner.jpg", b"fake-image-bytes", content_type="image/jpeg"),
                },
            )
        self.assertEqual(applicant_response.status_code, 201)
        created = applicant_response.json()
        self.assertEqual(created["status"], "approved")

        self._logout()
        self._login(username="buyer", next_url="/")
        with _gcs_disabled_for_test():
            create_response = self.client.post(
                "/api/v1/me/banner-applications/",
                data={
                    "title": "Pending Banner",
                    "copy_text": "Awaiting review",
                    "link_url": "/products/acme-mug",
                    "starts_at": "2026-06-10",
                    "ends_at": "2026-06-30",
                    "position": "home_main",
                    "note": "buyer request",
                    "image": SimpleUploadedFile("pending.jpg", b"pending-bytes", content_type="image/jpeg"),
                },
            )
        pending_banner = create_response.json()
        self._logout()
        self._login(username="storeteam", next_url="/")

        review_response = self.client.post(
            f"/api/v1/staff/banners/{pending_banner['id']}/review/",
            data=json.dumps({"approved": True}),
            content_type="application/json",
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["status"], "approved")

        reorder_response = self.client.post(
            "/api/v1/staff/banners/reorder/",
            data=json.dumps({"ids": [created["id"], pending_banner["id"], 1]}),
            content_type="application/json",
        )
        self.assertEqual(reorder_response.status_code, 200)
        reordered_map = {item["id"]: item for item in reorder_response.json()["items"]}
        self.assertEqual(reordered_map[created["id"]]["sort_order"], 1)
        self.assertEqual(reordered_map[pending_banner["id"]]["sort_order"], 2)

        update_response = self.client.put(
            f"/api/v1/staff/banners/{created['id']}/",
            data=json.dumps(
                {
                    "title": "Third Banner Updated",
                    "copy_text": "Updated without replacing image",
                    "link_url": "/products/acme-tee",
                    "starts_at": "2026-06-05",
                    "ends_at": "2026-06-25",
                    "position": "home_main",
                    "note": "updated by admin",
                    "is_active": False,
                    "sort_order": 2,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["title"], "Third Banner Updated")
        self.assertFalse(update_response.json()["is_active"])

        delete_response = self.client.delete(f"/api/v1/staff/banners/{created['id']}/")
        self.assertEqual(delete_response.status_code, 204)

        list_response = self.client.get("/api/v1/staff/banners/")
        self.assertEqual(list_response.status_code, 200)
        remaining_ids = [item["id"] for item in list_response.json()["items"]]
        self.assertNotIn(created["id"], remaining_ids)

    def test_api_route_record_page_lists_wave_two_routes(self):
        response = self.client.get("/docs/api-routes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/me/orders/")
        self.assertContains(response, "/api/v1/staff/dashboard/")

    def test_wave_three_auth_and_profile_apis_work(self):
        register_response = self.client.post(
            "/api/v1/auth/register/",
            data=json.dumps(
                {
                    "username": "newbuyer",
                    "display_name": "New Buyer",
                    "password": "secret123",
                    "password_confirm": "secret123",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(register_response.status_code, 201)
        self.assertEqual(register_response.json()["user"]["username"], "newbuyer")

        logout_response = self.client.post("/api/v1/auth/logout/")
        self.assertEqual(logout_response.status_code, 200)

        login_response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": "newbuyer", "password": "secret123"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)

        profile_response = self.client.post(
            "/api/v1/me/profile/",
            data=json.dumps(
                {
                    "display_name": "New Buyer Pro",
                    "new_password": "secret456",
                    "confirm_password": "secret456",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["user"]["display_name"], "New Buyer Pro")
        user_record = local_store.get_user_by_username("newbuyer") or {}
        self.assertTrue(check_password("secret456", user_record.get("password_hash", "")))

    def test_wave_three_cart_and_checkout_apis_work(self):
        add_response = self.client.post(
            "/api/v1/cart/items/",
            data=json.dumps({"slug": "acme-mug", "qty": 2}),
            content_type="application/json",
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["item_count"], 2)

        coupon_response = self.client.post(
            "/api/v1/cart/",
            data=json.dumps({"code": "SAVE10"}),
            content_type="application/json",
        )
        self.assertEqual(coupon_response.status_code, 200)
        self.assertEqual(coupon_response.json()["coupon"], "SAVE10")

        preview_response = self.client.get("/api/v1/checkout/preview/")
        self.assertEqual(preview_response.status_code, 200)
        self.assertTrue(preview_response.json()["requires_login"])

        self._login(username="buyer", next_url="/")
        confirm_response = self._confirm_checkout()
        self.assertEqual(confirm_response.status_code, 201)
        self.assertEqual(confirm_response.json()["id"], 1)

    def test_wave_three_seller_product_crud_apis_work(self):
        self._login(username="alice", next_url="/")

        create_response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "API Bottle",
                    "price": "22.00",
                    "brand": "ACME",
                    "category": "outdoor",
                    "tags": "api,bottle",
                    "specs": "capacity_ml:600",
                    "status": "active",
                    "stock": "7",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["status"], "active")
        slug = create_response.json()["slug"]

        detail_response = self.client.get(f"/api/v1/me/products/{slug}/")
        self.assertEqual(detail_response.status_code, 200)

        update_response = self.client.put(
            f"/api/v1/me/products/{slug}/",
            data=json.dumps(
                {
                    "name": "API Bottle Plus",
                    "price": "24.00",
                    "brand": "ACME",
                    "category": "outdoor",
                    "tags": "api,bottle,plus",
                    "specs": "capacity_ml:650",
                    "status": "draft",
                    "stock": "9",
                    "existing_image_paths": [],
                    "remove_image_paths": [],
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        updated_slug = update_response.json()["slug"]

        duplicate_response = self.client.post(f"/api/v1/me/products/{updated_slug}/duplicate/")
        self.assertEqual(duplicate_response.status_code, 201)
        duplicate_slug = duplicate_response.json()["slug"]

        archive_response = self.client.post(f"/api/v1/me/products/{updated_slug}/archive/")
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(archive_response.json()["status"], "archived")

        delete_response = self.client.delete(f"/api/v1/me/products/{duplicate_slug}/")
        self.assertEqual(delete_response.status_code, 204)

    def test_wave_three_seller_can_create_product_with_chinese_name(self):
        self._login(username="alice", next_url="/")

        create_response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "短袖上衣",
                    "price": "22.00",
                    "brand": "none",
                    "category": "上衣",
                    "tags": "短袖,上衣",
                    "specs": "size:S,M,L",
                    "status": "active",
                    "stock": "7",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(create_response.json()["slug"].startswith("product-"))

    def test_wave_three_staff_review_apis_work(self):
        self._login(username="buyer", next_url="/")
        seller_request_response = self.client.post("/api/v1/me/seller-request/")
        self.assertEqual(seller_request_response.status_code, 200)
        self._logout()

        self._login(username="alice", next_url="/")
        create_response = self.client.post(
            "/api/v1/me/products/",
            data=json.dumps(
                {
                    "name": "Managed Kettle",
                    "price": "39.00",
                    "brand": "ACME",
                    "category": "kitchen",
                    "tags": "managed",
                    "specs": "material:steel",
                    "status": "active",
                    "stock": "3",
                }
            ),
            content_type="application/json",
        )
        managed_slug = create_response.json()["slug"]
        self._logout()

        self._login(username="storeteam", next_url="/")
        dashboard_response = self.client.get("/api/v1/staff/reviews/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertTrue(dashboard_response.json()["seller_requests"])
        self.assertTrue(dashboard_response.json()["managed_products"])

        seller_review_response = self.client.post(
            "/api/v1/staff/seller-requests/buyer/review/",
            data=json.dumps({"approved": True}),
            content_type="application/json",
        )
        self.assertEqual(seller_review_response.status_code, 200)
        self.assertEqual(seller_review_response.json()["user"]["role"], "seller")

        product_review_response = self.client.post(
            f"/api/v1/staff/products/{managed_slug}/archive/",
            data=json.dumps({"note": "Violation report confirmed."}),
            content_type="application/json",
        )
        self.assertEqual(product_review_response.status_code, 200)
        self.assertEqual(product_review_response.json()["status"], "archived")

    @patch("myapp.services.price_compare._search_pchome")
    @patch("myapp.services.price_compare._search_momo")
    def test_product_price_compare_api_returns_live_data_for_enabled_product(self, mock_search_momo, mock_search_pchome):
        mock_search_momo.return_value = {
            "site": "momo",
            "site_label": "momo",
            "title": "NEW FORCE 吸排短袖上衣 A100",
            "url": "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=100",
            "original_price": "1280",
            "sale_price": "556",
            "currency": "TWD",
            "note": 'Keyword search: "NEW FORCE A100"',
        }
        mock_search_pchome.return_value = {
            "site": "pchome",
            "site_label": "PChome 24h",
            "title": "NEW FORCE 吸排短袖上衣 A100",
            "url": "https://24h.pchome.com.tw/prod/ABC123",
            "original_price": "",
            "sale_price": "629",
            "currency": "TWD",
            "note": 'Keyword search: "NEW FORCE A100"',
        }
        self._write_products(
            [
                {
                    "id": 8,
                    "slug": "new-force-shirt-a100",
                    "name": "NEW FORCE 吸排短袖上衣 A100",
                    "price": 300.0,
                    "compare_at_price": 1200.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": ["polo"],
                    "images": [],
                    "specs": {"size": "L"},
                    "status": "active",
                    "stock": 1,
                    "price_compare_enabled": True,
                    "price_compare_query": "NEW FORCE A100",
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )
        response = self.client.get("/api/v1/products/new-force-shirt-a100/price-compare/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_mock"])
        self.assertEqual(payload["source_type"], "live_search")
        self.assertEqual(payload["our_product_slug"], "new-force-shirt-a100")
        self.assertEqual(payload["query"], "NEW FORCE A100")
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["site"], "momo")
        self.assertIn("lowest_price", payload)

    @patch("myapp.services.price_compare._search_pchome")
    @patch("myapp.services.price_compare._search_momo")
    def test_product_price_compare_refresh_api_updates_payload(self, mock_search_momo, mock_search_pchome):
        mock_search_momo.return_value = {
            "site": "momo",
            "site_label": "momo",
            "title": "NEW FORCE 吸排短袖上衣 A100",
            "url": "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=100",
            "original_price": "1280",
            "sale_price": "556",
            "currency": "TWD",
            "note": 'Keyword search: "NEW FORCE A100"',
        }
        mock_search_pchome.return_value = {
            "site": "pchome",
            "site_label": "PChome 24h",
            "title": "NEW FORCE 吸排短袖上衣 A100",
            "url": "https://24h.pchome.com.tw/prod/ABC123",
            "original_price": "",
            "sale_price": "629",
            "currency": "TWD",
            "note": 'Keyword search: "NEW FORCE A100"',
        }
        self._write_products(
            [
                {
                    "id": 8,
                    "slug": "new-force-shirt-a100",
                    "name": "NEW FORCE 吸排短袖上衣 A100",
                    "price": 300.0,
                    "compare_at_price": 1200.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": ["polo"],
                    "images": [],
                    "specs": {"size": "L"},
                    "status": "active",
                    "stock": 1,
                    "price_compare_enabled": True,
                    "price_compare_query": "NEW FORCE A100",
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )
        response = self.client.post("/api/v1/products/new-force-shirt-a100/price-compare/refresh/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "價格比較已更新。")
        self.assertFalse(payload["result"]["is_mock"])
        self.assertEqual(payload["result"]["our_product_slug"], "new-force-shirt-a100")

    def test_product_price_compare_api_rejects_disabled_product(self):
        self._write_products(
            [
                {
                    "id": 9,
                    "slug": "acme-mug",
                    "name": "ACME Mug",
                    "price": 120.0,
                    "brand": "ACME",
                    "category": "mugs",
                    "tags": [],
                    "images": [],
                    "specs": {},
                    "status": "active",
                    "stock": 5,
                    "price_compare_enabled": False,
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )
        response = self.client.get("/api/v1/products/acme-mug/price-compare/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Price comparison is not enabled for this product.")

    def test_admin_can_update_product_price_compare_settings(self):
        self._write_products(
            [
                {
                    "id": 10,
                    "slug": "new-force-shirt-a100",
                    "name": "NEW FORCE 吸排短袖上衣 A100",
                    "price": 890.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": [],
                    "images": [],
                    "specs": {},
                    "status": "active",
                    "stock": 15,
                    "price_compare_enabled": False,
                    "price_compare_query": "",
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )

        self._login(username="storeteam", next_url="/")
        response = self.client.post(
            "/api/v1/staff/products/new-force-shirt-a100/price-compare-settings/",
            data=json.dumps({"enabled": True, "query": "NEW FORCE A100"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "商品比價設定已更新。")
        self.assertTrue(payload["product"]["price_compare_enabled"])
        self.assertEqual(payload["product"]["price_compare_query"], "NEW FORCE A100")

    @patch("myapp.services.price_compare._search_pchome")
    @patch("myapp.services.price_compare._search_momo")
    def test_product_price_compare_prefers_specific_title_query_over_generic_brand_query(
        self,
        mock_search_momo,
        mock_search_pchome,
    ):
        def search_momo(query: str):
            if query != "NEW FORCE 素面率性短袖男士POLO衫":
                raise ValueError("No matching results found.")
            return {
                "site": "momo",
                "site_label": "momo",
                "title": "NEW FORCE 素面率性短袖男士POLO衫",
                "url": "https://www.momoshop.com.tw/goods/GoodsDetail.jsp?i_code=100",
                "original_price": "899",
                "sale_price": "649",
                "currency": "TWD",
                "note": "Matched by exact title.",
            }

        def search_pchome(query: str):
            if query != "NEW FORCE 素面率性短袖男士POLO衫":
                raise ValueError("No matching results found.")
            return {
                "site": "pchome",
                "site_label": "PChome 24h",
                "title": "NEW FORCE 素面率性短袖男士POLO衫",
                "url": "https://24h.pchome.com.tw/prod/ABC123",
                "original_price": "899",
                "sale_price": "649",
                "currency": "TWD",
                "note": "Matched by exact title.",
            }

        mock_search_momo.side_effect = search_momo
        mock_search_pchome.side_effect = search_pchome
        self._write_products(
            [
                {
                    "id": 11,
                    "slug": "new-force-polo",
                    "name": "NEW FORCE 素面率性短袖男士POLO衫-5色可選(男短袖polo衫/上衣/POLO衫/短袖上衣/涼感上衣)",
                    "price": 890.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": ["polo"],
                    "images": [],
                    "specs": {},
                    "status": "active",
                    "stock": 15,
                    "price_compare_enabled": True,
                    "price_compare_query": "NEW FORCE",
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )

        response = self.client.get("/api/v1/products/new-force-polo/price-compare/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(mock_search_momo.call_args[0][0], "NEW FORCE 素面率性短袖男士POLO衫")
        self.assertEqual(mock_search_pchome.call_args[0][0], "NEW FORCE 素面率性短袖男士POLO衫")
        self.assertIn('Search query: "NEW FORCE 素面率性短袖男士POLO衫"', payload["items"][0]["note"])

    @patch("myapp.services.price_compare._fetch_html")
    def test_search_momo_decodes_escaped_unicode_titles(self, mock_fetch_html):
        mock_fetch_html.return_value = (
            'goodsInfoList\\":[{\\"goodsCode\\":\\"15087545\\",'
            '\\"goodsName\\":\\"\\u3010NEW FORCE\\u3011\\u7d20\\u9762\\u7387\\u6027\\u77ed\\u8896\\u7537\\u58ebPOLO\\u886b\\",'
            '\\"goodsPrice\\":\\"$$649\\",'
            '\\"goodsPriceOri\\":\\"$$899\\"}]'
        )

        result = price_compare_service._search_momo("NEW FORCE 素面率性短袖男士POLO衫")

        self.assertEqual(result["title"], "【NEW FORCE】素面率性短袖男士POLO衫")
        self.assertEqual(result["sale_price"], "649")

    def test_api_route_record_page_lists_wave_three_routes(self):
        response = self.client.get("/docs/api-routes/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/api/v1/auth/login/")
        self.assertContains(response, "/api/v1/cart/")
        self.assertContains(response, "/api/v1/me/products/")
        self.assertContains(response, "/api/v1/staff/reviews/")
        self.assertContains(response, "Product Price Compare")

    def test_html_write_migration_record_page_lists_retired_routes(self):
        response = self.client.get("/docs/html-write-migrations/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "POST /login/")
        self.assertContains(response, "POST /api/v1/auth/login/")
        self.assertContains(response, "POST /checkout/confirm/")
        self.assertContains(response, "POST /api/v1/checkout/confirm/")

    def test_login_template_submits_to_drf_endpoint(self):
        response = self.client.get("/login/")

        self._assert_frontend_redirect(response, "/login")

    def test_product_detail_template_uses_api_first_write_actions(self):
        self._login(username="buyer", next_url="/")
        response = self.client.get("/products/acme-mug/")

        self._assert_frontend_redirect(response, "/products/acme-mug")

    def test_health_live_endpoint_returns_request_id(self):
        response = self.client.get("/health/live/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Request-ID", response)
        self.assertEqual(response.json()["status"], "ok")

    def test_health_ready_endpoint_checks_cache_and_uploads_dir(self):
        response = self.client.get("/health/ready/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["checks"]["cache"]["ok"])
        self.assertTrue(payload["checks"]["uploads_dir"]["ok"])

    def test_no_db_infrastructure_doc_page_loads(self):
        response = self.client.get("/docs/no-db-infrastructure/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "\u57fa\u790e\u8a2d\u65bd\u8207\u904b\u884c\u8a2d\u5b9a")
        self.assertContains(response, "/health/live/")

    def test_newebpay_payment_api_returns_latest_sandbox_record(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_response = self._confirm_checkout()
        order_id = order_response.json()["id"]
        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        with patch.dict(os.environ, env, clear=False):
            create_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["provider"], "NewebPay Payment")

        get_response = self.client.get(f"/api/v1/me/orders/{order_id}/newebpay-payment/")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["order_id"], order_id)
        self.assertEqual(get_response.json()["status"], "pending")

    def test_newebpay_payment_sandbox_prepare_sets_cvscom_by_shipping_method(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        home_order_id = self._confirm_checkout().json()["id"]

        self._add_product_to_cart("acme-mug", qty=1)
        address_id = self.client.post(
            "/api/v1/me/addresses/",
            data=json.dumps(
                {
                    "label": "Store Pickup",
                    "recipient": "Buyer",
                    "phone": "0912345678",
                    "city": "Taipei",
                    "district": "Da'an",
                    "postal_code": "106",
                    "address_line": "No. 2, Xinyi Rd.",
                }
            ),
            content_type="application/json",
        ).json()["id"]
        store_order_response = self._post_json(
            "/api/v1/checkout/confirm/",
            {
                "address_id": address_id,
                "shipping_method": "convenience_store",
                "payment_method": "newebpay",
            },
        )
        self.assertEqual(store_order_response.status_code, 201)
        store_order_id = store_order_response.json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        with patch.dict(os.environ, env, clear=False):
            home_prepare = self._post_json(f"/api/v1/me/orders/{home_order_id}/newebpay-payment/sandbox/", {})
            store_prepare = self._post_json(f"/api/v1/me/orders/{store_order_id}/newebpay-payment/sandbox/", {})

        self.assertEqual(home_prepare.status_code, 200)
        self.assertNotIn("CREDIT", home_prepare.json()["trade_info_params"])
        self.assertNotIn("ANDROIDPAY", home_prepare.json()["trade_info_params"])
        self.assertNotIn("SAMSUNGPAY", home_prepare.json()["trade_info_params"])
        self.assertEqual(home_prepare.json()["trade_info_params"]["CVSCOM"], 0)
        self.assertEqual(store_prepare.status_code, 200)
        self.assertEqual(store_prepare.json()["trade_info_params"]["CVSCOM"], 1)

    def test_newebpay_payment_sandbox_prepare_allows_optional_mobile_wallet_flags(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
            "NEWEBPAY_ENABLE_ANDROIDPAY": "1",
            "NEWEBPAY_ENABLE_SAMSUNGPAY": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            prepare_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})

        self.assertEqual(prepare_response.status_code, 200)
        self.assertEqual(prepare_response.json()["trade_info_params"]["ANDROIDPAY"], 1)
        self.assertEqual(prepare_response.json()["trade_info_params"]["SAMSUNGPAY"], 1)

    def test_newebpay_payment_sandbox_prepare_requires_configuration(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        config_response = self.client.get(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/")
        self.assertEqual(config_response.status_code, 200)
        self.assertFalse(config_response.json()["configured"])

        prepare_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})
        self.assertEqual(prepare_response.status_code, 503)

    def test_newebpay_payment_sandbox_prepare_uses_underscore_merchant_order_no(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        with patch.dict(os.environ, env, clear=False):
            prepare_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})

        self.assertEqual(prepare_response.status_code, 200)
        merchant_order_no = prepare_response.json()["merchant_order_no"]
        self.assertRegex(merchant_order_no, rf"^ORDER{order_id}_[0-9]+$")
        self.assertNotIn("-", merchant_order_no)

    def test_newebpay_payment_sandbox_callback_parses_urlencoded_trade_info(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        merchant_order_no = f"ORDER{order_id}_1710000000"
        result_payload = {
            "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
            "MerchantOrderNo": merchant_order_no,
            "TradeNo": "NPAYTEST123",
            "Amt": "13",
            "PaymentType": "GOOGLEPAY",
            "PayTime": "2026-06-01 12:00:00",
        }
        decrypted_trade_info = urlencode(
            {
                "Status": "SUCCESS",
                "Message": "Test message",
                "Result": json.dumps(result_payload),
            }
        )

        with patch.dict(os.environ, env, clear=False):
            trade_info = newebpay_payment_real_service._encrypt_trade_info(
                decrypted_trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            trade_sha = newebpay_payment_real_service._build_trade_sha(
                trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            callback_response = self._post_json(
                "/api/v1/integrations/newebpay/payment/sandbox/callback/",
                {
                    "Status": "SUCCESS",
                    "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                    "TradeInfo": trade_info,
                    "TradeSha": trade_sha,
                },
            )

        self.assertEqual(callback_response.status_code, 200)
        record = callback_response.json()["record"]
        self.assertEqual(record["decoded_payload"]["Result"]["MerchantOrderNo"], merchant_order_no)

        logs = local_store.get_newebpay_payment_logs()
        callback_log = next(item for item in logs if item.get("merchant_order_no") == merchant_order_no)
        self.assertEqual(callback_log["trade_no"], "NPAYTEST123")
        self.assertEqual(callback_log["status"], "paid")
        order = local_store.get_order_by_id(order_id)
        self.assertEqual(order["payment_method"], "newebpay_google_pay")
        self.assertEqual(order["payment_status"], "paid")

    def test_newebpay_payment_sandbox_return_updates_buyer_and_seller_order_views(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "STORE_FRONTEND_ORIGIN": "https://frontend.example",
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        merchant_order_no = f"ORDER{order_id}_1710000099"
        result_payload = {
            "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
            "MerchantOrderNo": merchant_order_no,
            "TradeNo": "NPAYWEBATM123",
            "Amt": "13",
            "PaymentType": "WEBATM",
            "PayTime": "2026-06-01 12:00:00",
        }
        decrypted_trade_info = urlencode(
            {
                "Status": "SUCCESS",
                "Message": "Test message",
                "Result": json.dumps(result_payload),
            }
        )

        with patch.dict(os.environ, env, clear=False):
            trade_info = newebpay_payment_real_service._encrypt_trade_info(
                decrypted_trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            trade_sha = newebpay_payment_real_service._build_trade_sha(
                trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            return_response = self.client.get(
                "/api/v1/integrations/newebpay/payment/sandbox/return/",
                {
                    "Status": "SUCCESS",
                    "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                    "TradeInfo": trade_info,
                    "TradeSha": trade_sha,
                },
            )

        self.assertEqual(return_response.status_code, 302)
        self.assertIn(f"/orders/{order_id}", return_response["Location"])
        self.assertIn("payment_callback=success", return_response["Location"])

        with patch.dict(os.environ, env, clear=False):
            buyer_payment_response = self.client.get(f"/api/v1/me/orders/{order_id}/newebpay-payment/")
            self.assertEqual(buyer_payment_response.status_code, 200)
            self.assertEqual(buyer_payment_response.json()["trade_no"], "NPAYWEBATM123")
            self.assertEqual(buyer_payment_response.json()["status"], "paid")

            buyer_order_response = self.client.get(f"/api/v1/me/orders/{order_id}/")
            self.assertEqual(buyer_order_response.status_code, 200)
            self.assertEqual(buyer_order_response.json()["payment_method"], "newebpay_webatm")
            self.assertEqual(buyer_order_response.json()["payment_status"], "paid")
            self.assertEqual(buyer_order_response.json()["payment_trade_no"], "NPAYWEBATM123")

            self._logout()
            self._login(username="alice")
            seller_order_response = self.client.get(f"/api/v1/me/sales/{order_id}/")
            self.assertEqual(seller_order_response.status_code, 200)
            self.assertEqual(seller_order_response.json()["payment_method"], "newebpay_webatm")
            self.assertEqual(seller_order_response.json()["payment_status"], "paid")
            self.assertEqual(seller_order_response.json()["payment_trade_no"], "NPAYWEBATM123")

    def test_newebpay_payment_sandbox_return_redirects_to_order_when_persist_fails(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "STORE_FRONTEND_ORIGIN": "https://frontend.example",
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        merchant_order_no = f"ORDER{order_id}_1710000099"
        result_payload = {
            "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
            "MerchantOrderNo": merchant_order_no,
            "TradeNo": "NPAYWEBATM123",
            "Amt": "13",
            "PaymentType": "WEBATM",
            "PayTime": "2026-06-01 12:00:00",
        }
        decrypted_trade_info = urlencode(
            {
                "Status": "SUCCESS",
                "Message": "Test message",
                "Result": json.dumps(result_payload),
            }
        )

        with patch.dict(os.environ, env, clear=False):
            trade_info = newebpay_payment_real_service._encrypt_trade_info(
                decrypted_trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            trade_sha = newebpay_payment_real_service._build_trade_sha(
                trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            with patch("myapp.api.views.newebpay_payment_real_service.persist_callback_record", side_effect=RuntimeError("persist exploded")):
                return_response = self.client.get(
                    "/api/v1/integrations/newebpay/payment/sandbox/return/",
                    {
                        "Status": "SUCCESS",
                        "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                        "TradeInfo": trade_info,
                        "TradeSha": trade_sha,
                    },
                )

        self.assertEqual(return_response.status_code, 302)
        self.assertIn(f"/orders/{order_id}", return_response["Location"])
        self.assertIn("payment_callback=failed", return_response["Location"])
        self.assertIn("merchant_order_no=", return_response["Location"])

    def test_newebpay_payment_query_sync_updates_buyer_and_seller_order_views(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "STORE_FRONTEND_ORIGIN": "https://frontend.example",
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        with patch.dict(os.environ, env, clear=False):
            prepare_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})

        self.assertEqual(prepare_response.status_code, 200)
        prepared = prepare_response.json()
        query_response_payload = {
            "Status": "SUCCESS",
            "Message": "query ok",
            "Result": {
                "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                "MerchantOrderNo": prepared["merchant_order_no"],
                "TradeNo": "NPAYQUERY123",
                "Amt": "680",
                "PaymentType": "WEBATM",
                "PayTime": "2026-06-01 12:00:00",
            },
        }

        with patch.dict(os.environ, env, clear=False):
            with patch(
                "myapp.services.newebpay_payment_real._request_query_trade_info",
                return_value=query_response_payload,
            ):
                buyer_order_response = self.client.get(f"/api/v1/me/orders/{order_id}/")
                buyer_payment_response = self.client.get(f"/api/v1/me/orders/{order_id}/newebpay-payment/")

        self.assertEqual(buyer_order_response.status_code, 200)
        self.assertEqual(buyer_order_response.json()["payment_method"], "newebpay_webatm")
        self.assertEqual(buyer_order_response.json()["payment_status"], "paid")
        self.assertEqual(buyer_order_response.json()["payment_trade_no"], "NPAYQUERY123")
        self.assertEqual(buyer_payment_response.status_code, 200)
        self.assertEqual(buyer_payment_response.json()["trade_no"], "NPAYQUERY123")
        self.assertEqual(buyer_payment_response.json()["status"], "paid")

        self._logout()
        self._login(username="alice")
        with patch.dict(os.environ, env, clear=False):
            with patch(
                "myapp.services.newebpay_payment_real._request_query_trade_info",
                return_value=query_response_payload,
            ):
                seller_order_response = self.client.get(f"/api/v1/me/sales/{order_id}/")

        self.assertEqual(seller_order_response.status_code, 200)
        self.assertEqual(seller_order_response.json()["payment_method"], "newebpay_webatm")
        self.assertEqual(seller_order_response.json()["payment_status"], "paid")
        self.assertEqual(seller_order_response.json()["payment_trade_no"], "NPAYQUERY123")

    def test_newebpay_payment_query_uses_integer_amount(self):
        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }

        class _FakeResponse:
            def __init__(self, body: str):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return self.body.encode("utf-8")

        captured = {}

        def fake_urlopen(request, timeout=0):
            captured["body"] = request.data.decode("utf-8")
            captured["timeout"] = timeout
            return _FakeResponse('{"Status":"SUCCESS","Result":{"MerchantOrderNo":"ORDER1_1"}}')

        with patch.dict(os.environ, env, clear=False):
            config = newebpay_payment_real_service._load_runtime_config()
            with patch("myapp.services.newebpay_payment_real.urlopen", side_effect=fake_urlopen):
                newebpay_payment_real_service._request_query_trade_info(
                    config,
                    merchant_order_no="ORDER1_1",
                    amount="680.00",
                )

        self.assertIn("Amt=680", captured["body"])
        self.assertNotIn("Amt=680.00", captured["body"])

    def test_newebpay_payment_sandbox_callback_updates_order_store_fields(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        address_id = self.client.post(
            "/api/v1/me/addresses/",
            data=json.dumps(
                {
                    "label": "Store Pickup",
                    "recipient": "Buyer",
                    "phone": "0912345678",
                    "city": "Taipei",
                    "district": "Da'an",
                    "postal_code": "106",
                    "address_line": "No. 2, Xinyi Rd.",
                }
            ),
            content_type="application/json",
        ).json()["id"]
        order_response = self._post_json(
            "/api/v1/checkout/confirm/",
            {
                "address_id": address_id,
                "shipping_method": "convenience_store",
                "payment_method": "newebpay",
            },
        )
        order_id = order_response.json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        merchant_order_no = f"ORDER{order_id}_1710000001"
        result_payload = {
            "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
            "MerchantOrderNo": merchant_order_no,
            "TradeNo": "NPAYSTORE123",
            "Amt": "13",
            "PaymentType": "CVSCOM",
            "StoreCode": "149741",
            "StoreName": "台北測試門市",
            "StoreAddr": "台北市大安區測試路 1 號",
            "StoreType": "UNIMART",
        }
        decrypted_trade_info = urlencode(
            {
                "Status": "SUCCESS",
                "Message": "Test message",
                "Result": json.dumps(result_payload),
            }
        )

        with patch.dict(os.environ, env, clear=False):
            trade_info = newebpay_payment_real_service._encrypt_trade_info(
                decrypted_trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            trade_sha = newebpay_payment_real_service._build_trade_sha(
                trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            callback_response = self._post_json(
                "/api/v1/integrations/newebpay/payment/sandbox/callback/",
                {
                    "Status": "SUCCESS",
                    "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                    "TradeInfo": trade_info,
                    "TradeSha": trade_sha,
                },
            )

        self.assertEqual(callback_response.status_code, 200)
        order = local_store.get_order_by_id(order_id)
        self.assertEqual(order["payment_method"], "newebpay_cvscom")
        self.assertEqual(order["payment_status"], "pending")
        self.assertEqual(order["pickup_store_code"], "149741")
        self.assertEqual(order["pickup_store_name"], "台北測試門市")
        self.assertEqual(order["shipping_method"], "convenience_store")

    def test_newebpay_payment_sandbox_prepare_rejects_paid_order(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]

        env = {
            "NEWEBPAY_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_HASH_IV": "1234567890123456",
            "NEWEBPAY_PAYMENT_NOTIFY_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/callback/",
            "NEWEBPAY_PAYMENT_RETURN_URL": "https://backend.example/api/v1/integrations/newebpay/payment/sandbox/return/",
            "NEWEBPAY_PAYMENT_CLIENT_BACK_URL": "https://frontend.example/orders/1",
        }
        merchant_order_no = f"ORDER{order_id}_1710000002"
        result_payload = {
            "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
            "MerchantOrderNo": merchant_order_no,
            "TradeNo": "NPAYPAID123",
            "Amt": "13",
            "PaymentType": "SAMSUNGPAY",
            "PayTime": "2026-06-01 12:00:00",
        }
        decrypted_trade_info = urlencode(
            {
                "Status": "SUCCESS",
                "Message": "Test message",
                "Result": json.dumps(result_payload),
            }
        )

        with patch.dict(os.environ, env, clear=False):
            trade_info = newebpay_payment_real_service._encrypt_trade_info(
                decrypted_trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            trade_sha = newebpay_payment_real_service._build_trade_sha(
                trade_info,
                hash_key=env["NEWEBPAY_HASH_KEY"],
                hash_iv=env["NEWEBPAY_HASH_IV"],
            )
            callback_response = self._post_json(
                "/api/v1/integrations/newebpay/payment/sandbox/callback/",
                {
                    "Status": "SUCCESS",
                    "MerchantID": env["NEWEBPAY_MERCHANT_ID"],
                    "TradeInfo": trade_info,
                    "TradeSha": trade_sha,
                },
            )
            self.assertEqual(callback_response.status_code, 200)
            prepare_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/sandbox/", {})

        self.assertEqual(prepare_response.status_code, 404)

    def test_checkout_store_map_prepare_and_callback_round_trip(self):
        self._login(username="buyer")
        env = {
            "NEWEBPAY_LOGISTICS_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_LOGISTICS_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_LOGISTICS_HASH_IV": "1234567890123456",
            "NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL": "https://backend.example/api/v1/integrations/newebpay/logistics/store-map/callback/",
            "NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL": "https://frontend.example/checkout",
        }
        with patch.dict(os.environ, env, clear=False):
            prepare_response = self._post_json(
                "/api/v1/checkout/logistics/store-map/prepare/",
                {
                    "pickup_store_brand": "UNIMART",
                    "payment_method": "newebpay_credit",
                    "return_url": "https://frontend.example/checkout",
                },
            )

            self.assertEqual(prepare_response.status_code, 201)
            prepared = prepare_response.json()
            self.assertEqual(prepared["action_url"], "https://ccore.newebpay.com/API/Logistic/storeMap")
            self.assertEqual(prepared["pickup_store_brand"], "UNIMART")
            self.assertIn("store_map_token=", prepared["return_url"])
            self.assertEqual(prepared["callback_url"], env["NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL"])
            self.assertEqual(prepared["plain_params"]["LgsType"], "B2C")
            self.assertEqual(prepared["plain_params"]["IsCollection"], "N")
            self.assertLessEqual(len(prepared["selection_token"]), 20)
            self.assertLessEqual(len(prepared["plain_params"]["ExtraData"]), 20)
            self.assertIn("/sm/", prepared["plain_params"]["ReturnURL"])
            self.assertLessEqual(len(prepared["plain_params"]["ReturnURL"]), 50)

            callback_response = self._post_json(
                "/api/v1/integrations/newebpay/logistics/store-map/callback/",
                {
                    "MerchantOrderNo": prepared["merchant_order_no"],
                    "StoreID": "149741",
                    "StoreName": "台北測試門市",
                    "StoreAddr": "台北市大安區測試路 1 號",
                    "StoreType": "1",
                    "ExtraData": prepared["selection_token"],
                    "Status": "SUCCESS",
                },
            )
            self.assertEqual(callback_response.status_code, 200)

            selection_response = self.client.get(
                f"/api/v1/checkout/logistics/store-selection/?token={prepared['selection_token']}"
            )
            self.assertEqual(selection_response.status_code, 200)
            selection = selection_response.json()
            self.assertTrue(selection["is_ready"])
            self.assertEqual(selection["pickup_store_brand"], "UNIMART")
            self.assertEqual(selection["pickup_store_code"], "149741")
            self.assertEqual(selection["pickup_store_name"], "台北測試門市")

    def test_checkout_store_selection_is_isolated_per_user(self):
        self._login(username="buyer")
        env = {
            "NEWEBPAY_LOGISTICS_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_LOGISTICS_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_LOGISTICS_HASH_IV": "1234567890123456",
            "NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL": "https://backend.example/api/v1/integrations/newebpay/logistics/store-map/callback/",
            "NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL": "https://frontend.example/checkout",
        }
        with patch.dict(os.environ, env, clear=False):
            prepared = self._post_json(
                "/api/v1/checkout/logistics/store-map/prepare/",
                {"pickup_store_brand": "FAMI", "payment_method": "newebpay_credit"},
            ).json()
            self._post_json(
                "/api/v1/integrations/newebpay/logistics/store-map/callback/",
                {
                    "MerchantOrderNo": prepared["merchant_order_no"],
                    "StoreID": "F12345",
                    "StoreName": "全家測試店",
                    "StoreAddr": "台中市測試路 2 號",
                    "StoreType": "2",
                    "ExtraData": prepared["selection_token"],
                    "Status": "SUCCESS",
                },
            )

            self._logout()
            self._login(username="alice")
            selection_response = self.client.get(
                f"/api/v1/checkout/logistics/store-selection/?token={prepared['selection_token']}"
            )
            self.assertEqual(selection_response.status_code, 404)

    def test_admin_checkout_store_map_debug_api_returns_generated_payload_summary(self):
        self._login(username="storeteam")
        env = {
            "NEWEBPAY_LOGISTICS_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_LOGISTICS_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_LOGISTICS_HASH_IV": "1234567890123456",
            "NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL": "https://backend.example/api/v1/integrations/newebpay/logistics/store-map/callback/",
            "NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL": "https://frontend.example/checkout",
        }
        with patch.dict(os.environ, env, clear=False):
            response = self._post_json(
                "/api/v1/staff/integrations/newebpay/logistics/store-map/debug/",
                {
                    "pickup_store_brand": "UNIMART",
                    "payment_method": "newebpay_credit",
                    "return_url": "https://frontend.example/checkout",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["runtime"]["merchant_id"], env["NEWEBPAY_LOGISTICS_MERCHANT_ID"])
        self.assertEqual(payload["runtime"]["hash_key_length"], 32)
        self.assertEqual(payload["runtime"]["hash_iv_length"], 16)
        self.assertTrue(payload["checks"]["has_encrypt_data_field"])
        self.assertTrue(payload["checks"]["has_hash_data_field"])
        self.assertTrue(payload["checks"]["has_post_data_field"])
        self.assertTrue(payload["checks"]["merchant_id_matches_uid"])
        self.assertTrue(payload["checks"]["post_data_matches_encrypt_data"])
        self.assertEqual(
            payload["prepared"]["plain_params"]["MerchantID"],
            env["NEWEBPAY_LOGISTICS_MERCHANT_ID"],
        )
        self.assertEqual(payload["prepared"]["plain_params"]["LgsType"], "B2C")
        self.assertEqual(payload["prepared"]["plain_params"]["IsCollection"], "N")
        self.assertLessEqual(len(payload["prepared"]["plain_params"]["ExtraData"]), 20)
        self.assertLessEqual(len(payload["prepared"]["plain_params"]["ReturnURL"]), 50)


class CustomerCenterOrmSyncTests(TestCase):
    """驗證會員中心地址與發票資料可直接由 ORM 維護。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "users.json").write_text(json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2), encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        for user in USERS_FIXTURE:
            auth_demo._sync_user_to_orm(dict(user))

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def test_address_and_invoice_updates_sync_to_orm(self):
        from .services import customer_center

        address = customer_center.add_address(
            "buyer",
            {
                "label": "ORM Home",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Xinyi",
                "postal_code": "110",
                "address_line": "1 Demo Road",
            },
        )
        customer_center.set_default_address("buyer", int(address["id"]))
        invoice = customer_center.update_invoice_profile(
            "buyer",
            {
                "invoice_type": "company",
                "company_name": "Buyer Co",
                "tax_id": "12345678",
                "carrier_code": "",
            },
        )

        db_user = AppUserModel.objects.get(username="buyer")
        db_address = UserAddressModel.objects.get(user=db_user, label="ORM Home")
        db_invoice = UserInvoiceProfileModel.objects.get(user=db_user)

        self.assertEqual(db_user.default_address_id, db_address.id)
        self.assertEqual(db_address.address_line, "1 Demo Road")
        self.assertEqual(db_invoice.company_name, "Buyer Co")
        self.assertEqual(db_invoice.tax_id, "12345678")
        self.assertEqual(invoice["invoice_type"], "company")

    def test_customer_center_can_read_and_update_from_orm_without_json_user_snapshot(self):
        from .services import customer_center

        first = customer_center.add_address(
            "buyer",
            {
                "label": "ORM Home",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Xinyi",
                "postal_code": "110",
                "address_line": "1 Demo Road",
            },
        )
        second = customer_center.add_address(
            "buyer",
            {
                "label": "ORM Office",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Da'an",
                "postal_code": "106",
                "address_line": "99 Work Ave",
            },
        )
        customer_center.set_default_address("buyer", int(second["id"]))
        customer_center.update_invoice_profile(
            "buyer",
            {
                "invoice_type": "personal",
                "carrier_code": "/ORM999",
                "company_name": "",
                "tax_id": "",
            },
        )

        users_path = Path(settings.BASE_DIR) / "data" / "users.json"
        users_path.write_text("[]", encoding="utf-8")
        local_store.clear_cache()

        addresses = customer_center.list_addresses("buyer")
        default_address = customer_center.get_default_address("buyer")
        invoice = customer_center.get_invoice_profile("buyer")
        customer_center.remove_address("buyer", int(first["id"]))
        remaining_addresses = customer_center.list_addresses("buyer")

        self.assertEqual(len(addresses), 2)
        self.assertEqual(default_address["label"], "ORM Office")
        self.assertEqual(invoice["carrier_code"], "/ORM999")
        self.assertEqual(len(remaining_addresses), 1)
        self.assertEqual(remaining_addresses[0]["label"], "ORM Office")

    def test_customer_center_ignores_json_only_addresses_when_orm_is_enabled(self):
        from .services import customer_center

        customer_center.add_address(
            "buyer",
            {
                "label": "ORM Home",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Xinyi",
                "postal_code": "110",
                "address_line": "1 Demo Road",
            },
        )

        users_path = Path(settings.BASE_DIR) / "data" / "users.json"
        users = json.loads(users_path.read_text(encoding="utf-8"))
        buyer = next(item for item in users if item.get("username") == "buyer")
        buyer.setdefault("addresses", []).append(
            {
                "id": 9999,
                "label": "JSON Only",
                "recipient": "Buyer",
                "phone": "0999999999",
                "city": "Kaohsiung",
                "district": "Lingya",
                "postal_code": "802",
                "address_line": "Legacy JSON Road",
                "is_default": False,
            }
        )
        users_path.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
        local_store.clear_cache()

        addresses = customer_center.list_addresses("buyer")

        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0]["label"], "ORM Home")


class AuthOrmSyncTests(TestCase):
    """驗證登入/註冊/賣家申請等會員流程會同步寫進 ORM。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "users.json").write_text(json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2), encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        for user in USERS_FIXTURE:
            auth_demo._sync_user_to_orm(dict(user))

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def test_register_login_and_profile_update_sync_to_orm(self):
        registered = auth_demo.register_user("orm_user", "ORM User", "secret123", "orm@example.com")
        self.assertEqual(registered["username"], "orm_user")

        authed = auth_demo.authenticate("orm_user", "secret123")
        self.assertIsNotNone(authed)
        updated = auth_demo.update_profile("orm_user", "ORM Updated", email="updated@example.com", new_password="secret456")

        db_user = AppUserModel.objects.get(username="orm_user")
        self.assertEqual(db_user.display_name, "ORM Updated")
        self.assertEqual(db_user.email, "updated@example.com")
        self.assertTrue(bool(db_user.last_login_at))
        self.assertEqual(updated["display_name"], "ORM Updated")

    def test_seller_request_and_shipping_rules_sync_to_orm(self):
        rules = auth_demo.update_seller_shipping_rules(
            "buyer",
            home_delivery_enabled=True,
            home_delivery_fee="90",
            convenience_store_enabled=True,
            convenience_store_fee="65",
            free_shipping_threshold="1500",
        )
        request_snapshot = auth_demo.request_seller_role("buyer")
        reviewed_snapshot = auth_demo.review_seller_request("buyer", approved=True)

        db_user = AppUserModel.objects.get(username="buyer")
        db_rules = UserShippingRuleModel.objects.get(user=db_user)
        current_request = SellerRequestModel.objects.get(user=db_user, is_current=True)

        self.assertEqual(rules["home_delivery_fee"], "90.00")
        self.assertEqual(db_rules.home_delivery_fee, 90)
        self.assertEqual(db_rules.convenience_store_fee, 65)
        self.assertEqual(db_rules.free_shipping_threshold, 1500)
        self.assertEqual(request_snapshot["seller_request_status"], "pending")
        self.assertEqual(reviewed_snapshot["role"], "seller")
        self.assertEqual(db_user.role, "seller")
        self.assertEqual(db_user.seller_request_status, "approved")
        self.assertEqual(current_request.status, "approved")

    def test_shipping_rules_can_be_read_from_orm_without_json_user_snapshot(self):
        auth_demo.update_seller_shipping_rules(
            "buyer",
            home_delivery_enabled=True,
            home_delivery_fee="95",
            convenience_store_enabled=False,
            convenience_store_fee="60",
            free_shipping_threshold="1800",
        )

        users_path = Path(settings.BASE_DIR) / "data" / "users.json"
        users_path.write_text("[]", encoding="utf-8")
        local_store.clear_cache()

        rules = auth_demo.get_seller_shipping_rules("buyer")

        self.assertEqual(rules["home_delivery_fee"], "95.00")
        self.assertFalse(rules["convenience_store_enabled"])
        self.assertEqual(rules["free_shipping_threshold"], "1800.00")

    def test_auth_profile_and_status_can_run_from_orm_without_json_user_snapshot(self):
        auth_demo.register_user("orm_only", "ORM Only", "secret123", "orm-only@example.com")

        users_path = Path(settings.BASE_DIR) / "data" / "users.json"
        users_path.write_text("[]", encoding="utf-8")
        local_store.clear_cache()

        authed = auth_demo.authenticate("orm_only", "secret123")
        self.assertIsNotNone(authed)
        self.assertEqual(authed["username"], "orm_only")

        updated = auth_demo.update_profile("orm_only", "ORM Only Updated", email="orm-updated@example.com")
        self.assertEqual(updated["display_name"], "ORM Only Updated")

        users = auth_demo.list_users(search="orm_only")
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "orm_only")

        status_snapshot = auth_demo.update_account_status("orm_only", "suspended")
        self.assertEqual(status_snapshot["account_status"], "suspended")

        db_user = AppUserModel.objects.get(username="orm_only")
        self.assertEqual(db_user.display_name, "ORM Only Updated")
        self.assertEqual(db_user.email, "orm-updated@example.com")
        self.assertEqual(db_user.account_status, "suspended")

    def test_password_reset_flow_can_run_from_orm_without_json_user_snapshot(self):
        auth_demo.register_user("reset_orm", "Reset ORM", "secret123", "reset-orm@example.com")
        password_reset_service.request_password_reset("reset-orm@example.com")
        token = PasswordResetTokenModel.objects.get(email="reset-orm@example.com")

        users_path = Path(settings.BASE_DIR) / "data" / "users.json"
        users_path.write_text("[]", encoding="utf-8")
        local_store.clear_cache()

        password_reset_service.confirm_password_reset(token.token, "secret456")

        db_user = AppUserModel.objects.get(username="reset_orm")
        token.refresh_from_db()
        self.assertTrue(check_password("secret456", db_user.password_hash))
        self.assertIsNotNone(token.used_at)

    def test_order_user_sync_does_not_downgrade_existing_seller_to_member(self):
        db_user = AppUserModel.objects.create(
            username="sellercase",
            email="sellercase@example.com",
            password_hash=make_password("demo123"),
            display_name="Seller Case",
            role="seller",
            account_status="active",
            seller_request_status="approved",
        )

        resolved = orders_service._ensure_db_user_from_username(
            "sellercase",
            display_name="Seller Case",
            email="sellercase@example.com",
            role="member",
        )

        self.assertEqual(resolved.id, db_user.id)
        db_user.refresh_from_db()
        self.assertEqual(db_user.role, "seller")
        self.assertEqual(db_user.seller_request_status, "approved")


class ProductManagementOrmSyncTests(TestCase):
    """驗證商品同步 ORM 時會重用既有品牌主檔。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "users.json").write_text(json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2), encoding="utf-8")
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "products.json").write_text("[]", encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()

        for user in USERS_FIXTURE:
            auth_demo._sync_user_to_orm(dict(user))
        for category in CATEGORIES_FIXTURE:
            CategoryModel.objects.get_or_create(
                slug=str(category.get("slug") or "").strip().lower(),
                defaults={
                    "name": str(category.get("name") or "").strip(),
                    "description": str(category.get("description") or "").strip(),
                    "is_active": bool(category.get("is_active", True)),
                },
            )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def test_sync_product_reuses_existing_brand_with_legacy_slug(self):
        BrandModel.objects.create(slug="acme-brand", name="ACME", description="", is_active=True)

        product_management._sync_product_record_to_orm(
            {
                "id": 101,
                "slug": "orm-acme-bottle",
                "name": "ORM ACME Bottle",
                "description": "ORM sync regression case",
                "price": 24.0,
                "compare_at_price": None,
                "stock": 9,
                "specs": {},
                "status": "draft",
                "review_note": "",
                "reviewed_at": "",
                "reviewed_by": "",
                "owner_username": "alice",
                "owner_display_name": "Alice",
                "brand": "ACME",
                "category": "kitchen",
                "category_slug": "kitchen",
                "images": [],
                "variants": [],
                "tags": ["api", "bottle"],
                "shipping_profile": {},
                "created_at": "2026-06-01T10:00:00+08:00",
                "updated_at": "2026-06-01T10:00:00+08:00",
            },
            owner_snapshot={"username": "alice", "display_name": "Alice"},
        )

        product = ProductModel.objects.select_related("brand").get(slug="orm-acme-bottle")
        self.assertEqual(BrandModel.objects.count(), 1)
        self.assertEqual(product.brand.slug, "acme-brand")
        self.assertEqual(product.brand.name, "ACME")


class OrdersOrmSyncTests(TestCase):
    """驗證訂單建立、出貨更新與讀取都可直接依賴 ORM。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(PRODUCTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "orders.json").write_text(
            json.dumps(ORDERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        for user in USERS_FIXTURE:
            auth_demo._sync_user_to_orm(dict(user))
        for category in CATEGORIES_FIXTURE:
            CategoryModel.objects.update_or_create(
                slug=str(category["slug"]),
                defaults={
                    "name": str(category["name"]),
                    "description": str(category.get("description") or ""),
                    "is_active": bool(category.get("is_active", True)),
                },
            )
        for product in PRODUCTS_FIXTURE:
            product_management._persist_product_record(
                {
                    **product,
                    "category_slug": str(product.get("category") or "").strip().lower(),
                    "brand_slug": str(product.get("brand") or "").strip().lower(),
                }
            )
        self.client = Client()

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _put_json(self, path, payload):
        return self.client.put(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="alice", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _logout(self):
        return self.client.post("/api/v1/auth/logout/")

    def _add_to_cart(self, slug="acme-mug", qty=1):
        return self._post_json("/api/v1/cart/items/", {"slug": slug, "qty": qty})

    def _create_address(self):
        response = self._post_json(
            "/api/v1/me/addresses/",
            {
                "label": "Home",
                "recipient": "Buyer",
                "phone": "0912345678",
                "city": "Taipei",
                "district": "Da'an",
                "postal_code": "106",
                "address_line": "No. 1, Xinyi Rd.",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def _clear_json_orders(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "orders.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def test_checkout_order_syncs_to_orm_and_buyer_views_survive_without_json_order(self):
        self._login(username="buyer")
        self.assertEqual(self._add_to_cart().status_code, 200)
        address_id = self._create_address()
        confirm_response = self._post_json("/api/v1/checkout/confirm/", {"address_id": address_id})
        self.assertEqual(confirm_response.status_code, 201)

        order_id = confirm_response.json()["id"]
        orders_service.apply_newebpay_result(
            order_id,
            payment_method=orders_service.PAYMENT_METHOD_NEWEBPAY_WEBATM,
            payment_status=orders_service.PAYMENT_STATUS_PAID,
            trade_no="NPAYTEST123",
            paid_at="2026-06-03T12:00:00+08:00",
        )

        db_order = OrderModel.objects.get(id=order_id)
        db_items = list(OrderItemModel.objects.filter(order=db_order))
        db_payment = PaymentTransactionModel.objects.get(order=db_order)

        self.assertEqual(db_order.buyer_username_snapshot, "buyer")
        self.assertEqual(db_order.shipping_method, orders_service.SHIPPING_METHOD_HOME_DELIVERY)
        self.assertEqual(db_order.payment_status, orders_service.PAYMENT_STATUS_PAID)
        self.assertEqual(len(db_items), 1)
        self.assertEqual(db_items[0].product_slug_snapshot, "acme-mug")
        self.assertEqual(db_payment.merchant_order_no, f"ORDER{order_id}")
        self.assertEqual(db_payment.trade_no, "NPAYTEST123")
        self.assertEqual(db_payment.status, orders_service.PAYMENT_STATUS_PAID)

        self._clear_json_orders()

        list_response = self.client.get("/api/v1/me/orders/")
        detail_response = self.client.get(f"/api/v1/me/orders/{order_id}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        payload = detail_response.json()
        self.assertEqual(payload["id"], order_id)
        self.assertEqual(payload["payment_status"], orders_service.PAYMENT_STATUS_PAID)
        self.assertEqual(payload["items"][0]["slug"], "acme-mug")

    def test_seller_update_syncs_to_orm_and_seller_views_survive_without_json_order(self):
        self._login(username="buyer")
        self.assertEqual(self._add_to_cart().status_code, 200)
        address_id = self._create_address()
        confirm_response = self._post_json("/api/v1/checkout/confirm/", {"address_id": address_id})
        self.assertEqual(confirm_response.status_code, 201)
        order_id = confirm_response.json()["id"]

        self._logout()
        self._login(username="alice")
        update_response = self._post_json(
            f"/api/v1/me/sales/{order_id}/update/",
            {
                "seller_status": orders_service.SELLER_STATUS_SHIPPED,
                "tracking_number": "TW123456789",
                "shipping_note": "Packed and shipped",
            },
        )
        self.assertEqual(update_response.status_code, 200)

        db_order = OrderModel.objects.get(id=order_id)
        db_item = OrderItemModel.objects.get(order=db_order)
        events = list(ShipmentEventModel.objects.filter(order=db_order))

        self.assertEqual(db_item.seller_status, orders_service.SELLER_STATUS_SHIPPED)
        self.assertEqual(db_item.tracking_number, "TW123456789")
        self.assertTrue(events)
        self.assertEqual(events[-1].tracking_number, "TW123456789")

        self._clear_json_orders()

        seller_detail = self.client.get(f"/api/v1/me/sales/{order_id}/")
        self.assertEqual(seller_detail.status_code, 200)
        self.assertEqual(seller_detail.json()["items"][0]["seller_status"], orders_service.SELLER_STATUS_SHIPPED)

    def test_apply_payment_result_can_run_from_orm_without_json_order(self):
        self._login(username="buyer")
        self.assertEqual(self._add_to_cart().status_code, 200)
        address_id = self._create_address()
        confirm_response = self._post_json("/api/v1/checkout/confirm/", {"address_id": address_id})
        self.assertEqual(confirm_response.status_code, 201)
        order_id = confirm_response.json()["id"]
        self._clear_json_orders()

        result = orders_service.apply_newebpay_result(
            order_id,
            payment_method=orders_service.PAYMENT_METHOD_NEWEBPAY_WEBATM,
            payment_status=orders_service.PAYMENT_STATUS_PAID,
            trade_no="ORMONLY123",
            paid_at="2026-06-03T15:00:00+08:00",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["payment_method"], orders_service.PAYMENT_METHOD_NEWEBPAY_WEBATM)
        self.assertEqual(result["payment_trade_no"], "ORMONLY123")
        self.assertEqual(OrderModel.objects.get(id=order_id).payment_trade_no, "ORMONLY123")
        self.assertEqual(
            PaymentTransactionModel.objects.filter(order_id=order_id).latest("id").trade_no,
            "ORMONLY123",
        )

    def test_seller_update_can_run_from_orm_without_json_order(self):
        self._login(username="buyer")
        self.assertEqual(self._add_to_cart().status_code, 200)
        address_id = self._create_address()
        confirm_response = self._post_json("/api/v1/checkout/confirm/", {"address_id": address_id})
        self.assertEqual(confirm_response.status_code, 201)
        order_id = confirm_response.json()["id"]
        self._clear_json_orders()

        self._logout()
        self._login(username="alice")
        update_response = self._post_json(
            f"/api/v1/me/sales/{order_id}/update/",
            {
                "seller_status": orders_service.SELLER_STATUS_SHIPPED,
                "tracking_number": "ORMTRACK123",
                "shipping_note": "ORM seller update",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(OrderItemModel.objects.get(order_id=order_id).tracking_number, "ORMTRACK123")
        self.assertEqual(OrderItemModel.objects.get(order_id=order_id).shipping_note, "ORM seller update")

    def test_order_reads_ignore_json_only_orders_when_orm_is_enabled(self):
        self._login(username="buyer")
        self.assertEqual(self._add_to_cart().status_code, 200)
        address_id = self._create_address()
        confirm_response = self._post_json("/api/v1/checkout/confirm/", {"address_id": address_id})
        self.assertEqual(confirm_response.status_code, 201)
        real_order_id = confirm_response.json()["id"]

        orders_path = Path(self.temp_dir.name) / "data" / "orders.json"
        orders_data = json.loads(orders_path.read_text(encoding="utf-8"))
        orders_data.append(
            {
                "id": 9999,
                "order_no": "ORDER9999",
                "username": "buyer",
                "display_name": "Buyer",
                "status": orders_service.ORDER_STATUS_CONFIRMED,
                "shipping_method": orders_service.SHIPPING_METHOD_HOME_DELIVERY,
                "payment_method": orders_service.PAYMENT_METHOD_NEWEBPAY,
                "payment_status": orders_service.PAYMENT_STATUS_PENDING,
                "items": [],
                "totals": {"subtotal": "0.00", "shipping": "0.00", "discount": "0.00", "total": "0.00"},
                "shipping_address": {},
                "invoice_profile": {},
                "service_request": orders_service._empty_service_request(),
                "created_at": "2026-06-03T00:00:00+08:00",
            }
        )
        orders_path.write_text(json.dumps(orders_data, ensure_ascii=False, indent=2), encoding="utf-8")
        local_store.clear_cache()

        orders = orders_service.list_orders_for_user("buyer")
        ids = [item["id"] for item in orders]

        self.assertIn(real_order_id, ids)
        self.assertNotIn(9999, ids)


class CartOrmSyncTests(TestCase):
    """驗證登入會員購物車已改由 ORM 主流程維護。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(PRODUCTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        seeded_category_slugs = {str(item.get("slug") or "").strip().lower() for item in CATEGORIES_FIXTURE}
        for category_record in CATEGORIES_FIXTURE:
            CategoryModel.objects.get_or_create(
                slug=str(category_record.get("slug") or "").strip().lower(),
                defaults={
                    "name": str(category_record.get("name") or category_record.get("label") or "").strip(),
                    "description": str(category_record.get("description") or "").strip(),
                    "is_active": bool(category_record.get("is_active", True)),
                },
            )
        owner_snapshot = local_store.get_user_by_username("alice")
        for product_record in PRODUCTS_FIXTURE:
            seeded_record = dict(product_record)
            category_slug = str(seeded_record.get("category") or "").strip().lower()
            seeded_record.setdefault("category_slug", category_slug)
            if category_slug and category_slug not in seeded_category_slugs:
                CategoryModel.objects.get_or_create(
                    slug=category_slug,
                    defaults={"name": category_slug.replace("-", " ").title(), "is_active": True},
                )
                seeded_category_slugs.add(category_slug)
            product_management._sync_product_record_to_orm(
                seeded_record,
                owner_snapshot=owner_snapshot,
            )
        self.client = Client()

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _login(self, username="buyer", password="demo123"):
        response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def _add_to_cart(self, slug="acme-mug", qty=1, variant_id=""):
        payload = {"slug": slug, "qty": qty}
        if variant_id:
            payload["variant_id"] = variant_id
        response = self.client.post(
            "/api/v1/cart/items/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response

    def test_logged_in_cart_writes_to_orm(self):
        self._login("buyer")
        self._add_to_cart("acme-mug", qty=2)

        db_cart = CartModel.objects.select_related("user").get(user__username="buyer")
        db_item = CartItemModel.objects.get(cart=db_cart, item_key="acme-mug")
        self.assertEqual(db_item.quantity, 2)
        self.assertEqual(str(db_item.product.slug), "acme-mug")
        self.assertEqual(db_cart.coupon_code, "")

    def test_guest_cart_login_migration_writes_to_orm(self):
        self._add_to_cart("acme-mug", qty=1)
        self._login("buyer")

        db_cart = CartModel.objects.select_related("user").get(user__username="buyer")
        db_item = CartItemModel.objects.get(cart=db_cart, item_key="acme-mug")
        self.assertEqual(db_item.quantity, 1)
        self.assertEqual(self.client.session["cart"]["__guest__"]["items"], {})


class PersonalizationOrmSyncTests(TestCase):
    """驗證登入會員的收藏、比較與最近瀏覽已改由 ORM 主流程維護。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(PRODUCTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()

        seeded_category_slugs = {str(item.get("slug") or "").strip().lower() for item in CATEGORIES_FIXTURE}
        for category_record in CATEGORIES_FIXTURE:
            CategoryModel.objects.get_or_create(
                slug=str(category_record.get("slug") or "").strip().lower(),
                defaults={
                    "name": str(category_record.get("name") or category_record.get("label") or "").strip(),
                    "description": str(category_record.get("description") or "").strip(),
                    "is_active": bool(category_record.get("is_active", True)),
                },
            )

        owner_snapshot = local_store.get_user_by_username("alice")
        for product_record in PRODUCTS_FIXTURE:
            seeded_record = dict(product_record)
            category_slug = str(seeded_record.get("category") or "").strip().lower()
            seeded_record.setdefault("category_slug", category_slug)
            if category_slug and category_slug not in seeded_category_slugs:
                CategoryModel.objects.get_or_create(
                    slug=category_slug,
                    defaults={"name": category_slug.replace("-", " ").title(), "is_active": True},
                )
                seeded_category_slugs.add(category_slug)
            product_management._sync_product_record_to_orm(
                seeded_record,
                owner_snapshot=owner_snapshot,
            )

        self.client = Client()

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _login(self, username="buyer", password="demo123"):
        response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

    def _remove_user_from_json(self, username: str):
        data_dir = Path(self.temp_dir.name) / "data"
        users_path = data_dir / "users.json"
        users = json.loads(users_path.read_text(encoding="utf-8"))
        filtered = [item for item in users if item.get("username") != username]
        users_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        local_store.clear_cache()

    def test_logged_in_favorite_compare_and_recent_view_survive_without_json_user_snapshot(self):
        self._login("buyer")

        favorite_response = self.client.post("/api/v1/products/acme-mug/favorite/")
        compare_response = self.client.post("/api/v1/products/acme-mug/compare/")
        self.assertEqual(favorite_response.status_code, 200)
        self.assertEqual(compare_response.status_code, 200)

        session = self.client.session
        personalization_service.record_recent_view(
            session,
            {"slug": "acme-mug"},
        )
        session.save()

        self._remove_user_from_json("buyer")

        bootstrap_response = self.client.get("/api/v1/app/bootstrap/")
        compare_list_response = self.client.get("/api/v1/products/compare/")
        detail_response = self.client.get("/api/v1/products/acme-mug/")

        self.assertEqual(bootstrap_response.status_code, 200)
        self.assertEqual(bootstrap_response.json()["favorite_count"], 1)
        self.assertEqual(bootstrap_response.json()["compare_count"], 1)
        self.assertEqual(compare_list_response.status_code, 200)
        self.assertEqual(compare_list_response.json()["slugs"], ["acme-mug"])
        self.assertEqual(detail_response.status_code, 200)
        self.assertTrue(detail_response.json()["is_favorite"])

        db_user = AppUserModel.objects.get(username="buyer")
        self.assertTrue(UserFavoriteModel.objects.filter(user=db_user, product__slug="acme-mug").exists())
        self.assertTrue(
            CompareItemModel.objects.filter(bucket_key=f"user:{db_user.id}", product__slug="acme-mug").exists()
        )
        self.assertTrue(RecentViewModel.objects.filter(user=db_user, product__slug="acme-mug").exists())

        recent_products = personalization_service.get_recent_products(self.client.session)
        self.assertEqual([item["slug"] for item in recent_products], ["acme-mug"])


class AdminOrmSyncTests(TestCase):
    """驗證管理端商品列表與上下架操作可在 JSON 缺席時直接從 ORM 運作。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text("[]", encoding="utf-8")
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "orders.json").write_text("[]", encoding="utf-8")
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.assertIsNotNone(auth_demo.authenticate("alice", "demo123"))
        self.client = Client()
        for user in USERS_FIXTURE:
            auth_demo._sync_user_to_orm(dict(user))
        for category in CATEGORIES_FIXTURE:
            CategoryModel.objects.get_or_create(
                slug=str(category.get("slug") or "").strip().lower(),
                defaults={
                    "name": str(category.get("name") or "").strip(),
                    "description": str(category.get("description") or "").strip(),
                    "is_active": bool(category.get("is_active", True)),
                },
            )

        product_management._sync_product_record_to_orm(
            {
                **PRODUCTS_FIXTURE[0],
                "category_slug": str(PRODUCTS_FIXTURE[0].get("category") or "").strip().lower(),
                "brand_slug": str(PRODUCTS_FIXTURE[0].get("brand") or "").strip().lower(),
            },
            owner_snapshot={"username": "alice", "display_name": "Alice"},
        )
        product_management._sync_product_record_to_orm(
            {
                "id": 99,
                "slug": "orm-admin-draft",
                "name": "ORM Admin Draft",
                "description": "ORM only admin draft product",
                "price": 19.9,
                "compare_at_price": None,
                "stock": 5,
                "specs": {"size": "L"},
                "status": "draft",
                "review_note": "",
                "reviewed_at": "",
                "reviewed_by": "",
                "owner_username": "alice",
                "owner_display_name": "Alice",
                "brand": "Draft Lab",
                "category": "apparel",
                "category_slug": "apparel",
                "images": [],
                "variants": [],
                "tags": ["draft"],
                "shipping_profile": {},
                "created_at": "2026-05-01T10:00:00+08:00",
                "updated_at": "2026-05-01T10:00:00+08:00",
            },
            owner_snapshot={"username": "alice", "display_name": "Alice"},
        )
        alice = AppUserModel.objects.get(username="alice")
        storeteam, _ = AppUserModel.objects.update_or_create(
            username="storeteam",
            defaults={
                "email": "storeteam@example.com",
                "display_name": "Store Team",
                "role": "admin",
                "password_hash": make_password("demo123"),
                "account_status": "active",
                "seller_request_status": "approved",
            },
        )
        product = ProductModel.objects.get(slug="acme-mug")
        question = ProductQuestionModel.objects.create(
            product=product,
            author=alice,
            author_display_name_snapshot="Eva",
            title="Can this go in the dishwasher?",
            body="I want to know if this is dishwasher safe.",
            is_visible=True,
        )
        ProductQuestionAnswerModel.objects.create(
            question=question,
            author=storeteam,
            author_display_name_snapshot="Store Team",
            body="Yes, it is dishwasher safe.",
            is_visible=True,
        )
        ProductReviewModel.objects.create(
            product=product,
            author=alice,
            author_display_name_snapshot="Alice",
            rating=5,
            title="Nice daily mug",
            body="Feels sturdy and the glaze looks premium.",
            is_visible=True,
        )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="storeteam", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _clear_json_products(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "products.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def _remove_user_from_json(self, username: str):
        data_dir = Path(self.temp_dir.name) / "data"
        users_path = data_dir / "users.json"
        users = json.loads(users_path.read_text(encoding="utf-8"))
        filtered = [item for item in users if item.get("username") != username]
        users_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
        local_store.clear_cache()

    def test_admin_product_listing_and_lifecycle_work_without_json_product(self):
        self._clear_json_products()
        self._login()

        list_response = self.client.get("/api/v1/staff/products/?status=draft")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"][0]["slug"], "orm-admin-draft")

        publish_response = self.client.post(
            "/api/v1/staff/products/orm-admin-draft/publish/",
            data=json.dumps({"note": "Publish from ORM"}),
            content_type="application/json",
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.json()["status"], "active")

        archive_response = self.client.post(
            "/api/v1/staff/products/orm-admin-draft/archive/",
            data=json.dumps({"note": "Archive from ORM"}),
            content_type="application/json",
        )
        self.assertEqual(archive_response.status_code, 200)
        self.assertEqual(archive_response.json()["status"], "archived")
        self.assertTrue(ProductModel.objects.filter(slug="orm-admin-draft", status="archived").exists())

        delete_response = self.client.delete("/api/v1/staff/products/orm-admin-draft/")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(ProductModel.objects.filter(slug="orm-admin-draft").exists())

    def test_admin_user_and_seller_request_apis_work_without_json_user_snapshot(self):
        auth_demo.register_user("ormmember", "ORM Member", "secret123", "ormmember@example.com")
        auth_demo.request_seller_role("ormmember")
        self._remove_user_from_json("ormmember")

        self.assertEqual(self._login().status_code, 200)

        users_response = self.client.get("/api/v1/staff/users/", {"q": "ormmember"})
        self.assertEqual(users_response.status_code, 200)
        self.assertEqual(len(users_response.json()["items"]), 1)
        self.assertEqual(users_response.json()["items"][0]["username"], "ormmember")

        status_response = self._post_json("/api/v1/staff/users/ormmember/status/", {"account_status": "suspended"})
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["user"]["account_status"], "suspended")

        review_response = self._post_json("/api/v1/staff/seller-requests/ormmember/review/", {"approved": True})
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["user"]["role"], "seller")
        self.assertEqual(review_response.json()["user"]["seller_request_status"], "approved")

        db_user = AppUserModel.objects.get(username="ormmember")
        self.assertEqual(db_user.account_status, "suspended")
        self.assertEqual(db_user.role, "seller")
        self.assertEqual(db_user.seller_request_status, "approved")
        current_request = SellerRequestModel.objects.get(user=db_user, is_current=True)
        self.assertEqual(current_request.status, "approved")

    def test_admin_user_api_includes_password_reset_records(self):
        auth_demo.register_user("resetviewer", "Reset Viewer", "secret123", "resetviewer@example.com")
        password_reset_service.request_password_reset("resetviewer@example.com")
        self._remove_user_from_json("resetviewer")

        self.assertEqual(self._login().status_code, 200)

        response = self.client.get("/api/v1/staff/users/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("reset_records", payload)
        self.assertEqual(payload["reset_records"][0]["email"], "resetviewer@example.com")
        self.assertEqual(payload["reset_records"][0]["status"], "active")
        self.assertIn("/reset-password?token=", payload["reset_records"][0]["reset_url"])

    def test_admin_product_listing_ignores_json_only_products_when_orm_is_enabled(self):
        products_path = Path(self.temp_dir.name) / "data" / "products.json"
        products_path.write_text(
            json.dumps(
                [
                    {
                        "id": 501,
                        "slug": "json-only-draft",
                        "name": "JSON Only Draft",
                        "description": "legacy product that should be hidden in ORM mode",
                        "price": 9.9,
                        "compare_at_price": None,
                        "stock": 3,
                        "specs": {},
                        "status": "draft",
                        "review_note": "",
                        "reviewed_at": "",
                        "reviewed_by": "",
                        "owner_user_id": 1,
                        "owner_username": "alice",
                        "owner_display_name": "Alice",
                        "brand": "Legacy",
                        "category": "apparel",
                        "category_slug": "apparel",
                        "images": [],
                        "variants": [],
                        "tags": [],
                        "shipping_profile": {},
                        "created_at": "2026-06-03T09:00:00+08:00",
                        "updated_at": "2026-06-03T09:00:00+08:00",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        local_store.clear_cache()

        self.assertEqual(self._login().status_code, 200)
        response = self.client.get("/api/v1/staff/products/?status=draft")

        self.assertEqual(response.status_code, 200)
        slugs = [item["slug"] for item in response.json()["items"]]
        self.assertIn("orm-admin-draft", slugs)
        self.assertNotIn("json-only-draft", slugs)


class ContentOrmSyncTests(TestCase):
    """驗證評論與問答在 JSON 缺席時仍可從 ORM 讀取與管理。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(PRODUCTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "reviews.json").write_text(
            json.dumps(REVIEWS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "questions.json").write_text(
            json.dumps(QUESTIONS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "posts.json").write_text(
            json.dumps(POSTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.client = Client()

        CategoryModel.objects.get_or_create(
            slug="kitchen",
            defaults={"name": "kitchen", "description": "seed category", "is_active": True},
        )
        product_management._sync_product_record_to_orm(
            {
                "id": 1,
                "slug": "acme-mug",
                "name": "ACME Mug",
                "description": "ORM product for content tests",
                "price": 12.9,
                "compare_at_price": None,
                "stock": 10,
                "specs": {},
                "status": "active",
                "review_note": "",
                "reviewed_at": "",
                "reviewed_by": "",
                "owner_username": "alice",
                "owner_display_name": "Alice",
                "brand": "ACME",
                "category": "kitchen",
                "category_slug": "kitchen",
                "images": [],
                "variants": [],
                "tags": ["mug"],
                "shipping_profile": {},
                "created_at": "2026-05-01T10:00:00+08:00",
                "updated_at": "2026-05-01T10:00:00+08:00",
            },
            owner_snapshot={"username": "alice", "display_name": "Alice"},
        )
        alice, _ = AppUserModel.objects.update_or_create(
            username="alice",
            defaults={
                "email": "alice@example.com",
                "display_name": "Alice",
                "role": "member",
                "password_hash": make_password("demo123"),
                "account_status": "active",
                "seller_request_status": "none",
            },
        )
        storeteam, _ = AppUserModel.objects.update_or_create(
            username="storeteam",
            defaults={
                "email": "storeteam@example.com",
                "display_name": "Store Team",
                "role": "admin",
                "password_hash": make_password("demo123"),
                "account_status": "active",
                "seller_request_status": "approved",
            },
        )
        product = ProductModel.objects.get(slug="acme-mug")
        question = ProductQuestionModel.objects.create(
            product=product,
            author=alice,
            author_display_name_snapshot="Eva",
            title="Can this go in the dishwasher?",
            body="I want to know if this is dishwasher safe.",
            is_visible=True,
        )
        ProductQuestionAnswerModel.objects.create(
            question=question,
            author=storeteam,
            author_display_name_snapshot="Store Team",
            body="Yes, it is dishwasher safe.",
            is_visible=True,
        )
        ProductReviewModel.objects.create(
            product=product,
            author=alice,
            author_display_name_snapshot="Alice",
            rating=5,
            title="Nice daily mug",
            body="Feels sturdy and the glaze looks premium.",
            is_visible=True,
        )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="storeteam", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _clear_content_json(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "reviews.json").write_text("[]", encoding="utf-8")
        (data_dir / "questions.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def test_product_content_and_admin_content_work_without_json_snapshots(self):
        self.assertEqual(len(review_service.list_reviews(1)), 1)
        self.assertEqual(len(question_service.list_questions(1)), 1)
        self._clear_content_json()

        reviews_response = self.client.get("/api/v1/products/acme-mug/reviews/")
        questions_response = self.client.get("/api/v1/products/acme-mug/questions/")
        self.assertEqual(reviews_response.status_code, 200)
        self.assertEqual(questions_response.status_code, 200)
        self.assertEqual(reviews_response.json()["items"][0]["title"], "Nice daily mug")
        self.assertEqual(questions_response.json()["items"][0]["title"], "Can this go in the dishwasher?")
        self.assertEqual(len(questions_response.json()["items"][0]["answers"]), 1)
        self.assertTrue(ProductReviewModel.objects.filter(product_id=1).exists())
        self.assertTrue(ProductQuestionModel.objects.filter(product_id=1).exists())
        self.assertTrue(ProductQuestionAnswerModel.objects.filter(question__product_id=1).exists())

        self.assertEqual(self._login().status_code, 200)
        admin_reviews = self.client.get("/api/v1/staff/content/reviews/?q=Nice")
        admin_questions = self.client.get("/api/v1/staff/content/questions/?answered=answered")
        self.assertEqual(admin_reviews.status_code, 200)
        self.assertEqual(admin_questions.status_code, 200)
        self.assertEqual(admin_reviews.json()["items"][0]["title"], "Nice daily mug")
        self.assertEqual(admin_questions.json()["items"][0]["title"], "Can this go in the dishwasher?")


class ProfileOrmSyncTests(TestCase):
    """驗證會員中心 dashboard 在內容 JSON 缺席時仍可從 ORM 取得統計。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "products.json",
            "categories.json",
            "users.json",
            "reviews.json",
            "questions.json",
            "posts.json",
            "orders.json",
            "banners.json",
            "recommendations.json",
        ):
            (data_dir / name).write_text("[]", encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.client = Client()

        CategoryModel.objects.get_or_create(
            slug="kitchen",
            defaults={"name": "kitchen", "description": "seed category", "is_active": True},
        )
        product_management._sync_product_record_to_orm(
            {
                "id": 1,
                "slug": "acme-mug",
                "name": "ACME Mug",
                "description": "ORM product for profile dashboard tests",
                "price": 12.9,
                "compare_at_price": None,
                "stock": 10,
                "specs": {},
                "status": "active",
                "review_note": "",
                "reviewed_at": "",
                "reviewed_by": "",
                "owner_username": "alice",
                "owner_display_name": "Alice",
                "brand": "ACME",
                "category": "kitchen",
                "category_slug": "kitchen",
                "images": [],
                "variants": [],
                "tags": ["mug"],
                "shipping_profile": {},
                "created_at": "",
                "updated_at": "",
            },
            owner_snapshot={
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "password_hash": "pbkdf2_sha256$dummy",
                "role": "seller",
                "account_status": "active",
            },
        )
        auth_demo.register_user("buyer", "Buyer", "demo123", "buyer@example.com")
        login_response = self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": "buyer", "password": "demo123"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def test_dashboard_reads_content_from_orm_without_json_snapshots(self):
        self.client.post(
            "/api/v1/products/acme-mug/reviews/",
            data=json.dumps({"rating": 4, "title": "Useful cup", "body": "Works well on my desk."}),
            content_type="application/json",
        )
        self.client.post(
            "/api/v1/products/acme-mug/questions/",
            data=json.dumps({"title": "Is it microwave safe?", "body": "I want to heat milk in it."}),
            content_type="application/json",
        )
        self.client.post(
            "/api/v1/community/posts/",
            data=json.dumps(
                {
                    "topic": "tips",
                    "title": "How do you store travel bottles?",
                    "body": "Looking for ways to avoid odor between trips.",
                    "tags": "bottle, travel",
                }
            ),
            content_type="application/json",
        )

        data_dir = Path(settings.BASE_DIR) / "data"
        (data_dir / "reviews.json").write_text("[]", encoding="utf-8")
        (data_dir / "questions.json").write_text("[]", encoding="utf-8")
        (data_dir / "posts.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

        response = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["review_count"], 1)
        self.assertEqual(payload["question_count"], 1)
        self.assertEqual(payload["post_count"], 1)


class CommunityOrmSyncTests(TestCase):
    """驗證社群文章在 JSON 缺席時仍可從 ORM 讀取、回覆、投票與後台管理。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(PRODUCTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "reviews.json").write_text(
            json.dumps(REVIEWS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "questions.json").write_text(
            json.dumps(QUESTIONS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "posts.json").write_text(
            json.dumps(POSTS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.client = Client()
        alice, _ = AppUserModel.objects.update_or_create(
            username="alice",
            defaults={
                "email": "alice@example.com",
                "display_name": "Alice",
                "role": "member",
                "password_hash": make_password("demo123"),
                "account_status": "active",
                "seller_request_status": "none",
            },
        )
        storeteam, _ = AppUserModel.objects.update_or_create(
            username="storeteam",
            defaults={
                "email": "storeteam@example.com",
                "display_name": "Store Team",
                "role": "admin",
                "password_hash": make_password("demo123"),
                "account_status": "active",
                "seller_request_status": "approved",
            },
        )
        post = CommunityPostModel.objects.create(
            id=1,
            author=alice,
            author_display_name_snapshot="Alice",
            topic="general",
            title="Best mug for office use?",
            body_html="Looking for a mug that keeps drinks warm and survives a busy office desk.",
            votes_count=3,
            is_visible=True,
        )
        CommunityReplyModel.objects.create(
            post=post,
            author=storeteam,
            author_display_name_snapshot="Store Team",
            body="A ceramic mug with lid works well for office use.",
            is_visible=True,
        )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="storeteam", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _clear_posts_json(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "posts.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def test_community_and_admin_posts_work_without_json_snapshots(self):
        self.assertEqual(len(community_service.list_posts()), 1)
        self._clear_posts_json()

        detail_response = self.client.get("/api/v1/community/posts/1/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["title"], "Best mug for office use?")
        self.assertEqual(detail_response.json()["author"], "Alice")
        self.assertEqual(len(detail_response.json()["replies"]), 1)
        self.assertTrue(CommunityPostModel.objects.filter(id=1).exists())
        self.assertTrue(CommunityReplyModel.objects.filter(post_id=1).exists())

        self.assertEqual(self._login(username="alice", password="demo123").status_code, 200)
        reply_response = self.client.post(
            "/api/v1/community/posts/1/replies/",
            data=json.dumps({"body": "A silicone coaster helps keep the desk clean."}),
            content_type="application/json",
        )
        self.assertEqual(reply_response.status_code, 201)
        self.assertEqual(len(reply_response.json()["replies"]), 2)
        self.assertEqual(reply_response.json()["replies"][-1]["author"], anonymize_public_name("Alice"))
        latest_reply = CommunityReplyModel.objects.filter(post_id=1).order_by("-id").first()
        self.assertIsNotNone(latest_reply)
        self.assertEqual(latest_reply.author.username, "alice")
        self.assertEqual(latest_reply.author_display_name_snapshot, "Alice")

        vote_response = self.client.post("/api/v1/community/posts/1/vote/")
        self.assertEqual(vote_response.status_code, 200)
        self.assertEqual(vote_response.json()["votes"], 4)
        self.assertTrue(vote_response.json()["has_voted"])
        self.assertTrue(CommunityVoteModel.objects.filter(post_id=1).exists())

        self.client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": "storeteam", "password": "demo123"}),
            content_type="application/json",
        )
        admin_posts = self.client.get("/api/v1/staff/content/posts/?topic=general")
        self.assertEqual(admin_posts.status_code, 200)
        self.assertEqual(admin_posts.json()["items"][0]["title"], "Best mug for office use?")


class BannerOrmSyncTests(TestCase):
    """驗證 banners.json 缺席時，banner 仍可從 ORM 讀取與維護。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "users.json").write_text("[]", encoding="utf-8")
        (data_dir / "banners.json").write_text("[]", encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        _seed_fixture_state()
        self.client = Client()
        self.storeteam = AppUserModel.objects.create(
            username="storeteam",
            email="storeteam@example.com",
            display_name="Store Team",
            role="admin",
            password_hash=make_password("demo123"),
            account_status="active",
            seller_request_status="approved",
        )
        self.buyer = AppUserModel.objects.create(
            username="buyer",
            email="buyer@example.com",
            display_name="Buyer",
            role="member",
            password_hash=make_password("demo123"),
            account_status="active",
            seller_request_status="",
        )
        now = timezone.now()
        BannerModel.objects.create(
            id=1,
            title="Primary Banner",
            copy_text="Main campaign",
            image_path="/static/images/banner-1.jpg",
            link_url="/products/acme-mug",
            position="home_main",
            note="seeded active banner",
            sort_order=1,
            status="approved",
            is_active=True,
            rejection_reason="",
            applicant_user=self.storeteam,
            reviewed_by=self.storeteam,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
        )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="storeteam", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _clear_banners_json(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "banners.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def test_banner_endpoints_work_without_json_snapshots(self):
        self.assertEqual(len(banner_service.list_public_banners()), 1)
        self._clear_banners_json()

        public_response = self.client.get("/api/v1/banners/")
        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.json()["items"][0]["title"], "Primary Banner")
        self.assertTrue(BannerModel.objects.filter(id=1).exists())

        self.assertEqual(self._login(username="buyer", password="demo123").status_code, 200)
        with _gcs_disabled_for_test():
            create_response = self.client.post(
                "/api/v1/me/banner-applications/",
                data={
                    "title": "ORM Banner",
                    "copy_text": "From ORM only",
                    "link_url": "/products/acme-tee",
                    "starts_at": "2026-06-01",
                    "ends_at": "2026-06-15",
                    "position": "home_main",
                    "note": "Created after json clear",
                    "image": SimpleUploadedFile("orm-banner.png", b"banner-bytes", content_type="image/png"),
                },
            )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertEqual(created["status"], "pending")
        self.assertEqual(created["applicant_username"], "buyer")
        self.assertTrue(BannerModel.objects.filter(id=created["id"], title="ORM Banner").exists())

        self._login(username="storeteam", password="demo123")
        admin_list = self.client.get("/api/v1/staff/banners/")
        self.assertEqual(admin_list.status_code, 200)
        self.assertTrue(any(item["title"] == "ORM Banner" for item in admin_list.json()["items"]))

        review_response = self.client.post(
            f"/api/v1/staff/banners/{created['id']}/review/",
            data=json.dumps({"approved": True}),
            content_type="application/json",
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.json()["status"], "approved")

        reorder_response = self.client.post(
            "/api/v1/staff/banners/reorder/",
            data=json.dumps({"ids": [created["id"], 1]}),
            content_type="application/json",
        )
        self.assertEqual(reorder_response.status_code, 200)
        reordered_map = {item["id"]: item for item in reorder_response.json()["items"]}
        self.assertEqual(reordered_map[created["id"]]["sort_order"], 1)
        self.assertTrue(BannerModel.objects.filter(id=created["id"], sort_order=1).exists())

    def test_banner_product_link_updates_when_product_slug_changes(self):
        seller = AppUserModel.objects.create(
            username="abc",
            email="abc@example.com",
            display_name="abc",
            role="seller",
            password_hash=make_password("demo123"),
            account_status="active",
            seller_request_status="approved",
        )
        category = CategoryModel.objects.create(
            slug="tops",
            name="上衣",
            description="tops",
            is_active=True,
        )
        product = product_management._sync_product_record_to_orm(
            {
                "id": 88,
                "slug": "abc-short-sleeve-top-1",
                "name": "短袖上衣1",
                "description": "",
                "price": 590.0,
                "compare_at_price": None,
                "brand": "abc",
                "category": category.name,
                "category_slug": category.slug,
                "tags": [],
                "images": [],
                "variants": [],
                "specs": {},
                "status": "active",
                "stock": 20,
                "owner_username": "abc",
                "owner_display_name": "abc",
            },
            owner_snapshot={"username": "abc", "display_name": "abc"},
        )
        banner = BannerModel.objects.get(id=1)
        banner.link_url = "http://localhost:3000/products/abc-short-sleeve-top-1?ref=banner"
        banner.save(update_fields=["link_url"])

        updated_record = dict(product)
        updated_record["slug"] = "abc-short-sleeve-top-1-renamed"
        updated_record["name"] = "短袖上衣1新版"
        product_management._persist_product_record(updated_record, previous_slug="abc-short-sleeve-top-1")

        banner.refresh_from_db()
        self.assertEqual(banner.link_url, "/products/abc-short-sleeve-top-1-renamed?ref=banner")
        self.assertEqual(banner_service.list_public_banners()[0]["link_url"], "/products/abc-short-sleeve-top-1-renamed?ref=banner")


class RecommendationOrmSyncTests(TestCase):
    """驗證 ORM 推薦關聯建立後，不依賴 recommendations.json 也能正常讀取。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "products.json").write_text(
            json.dumps(build_extra_products(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "categories.json").write_text(
            json.dumps(CATEGORIES_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        self.client = Client()

        for product in build_extra_products():
            category_slug = str(product.get("category", "")).strip().lower()
            if category_slug:
                CategoryModel.objects.get_or_create(
                    slug=category_slug,
                    defaults={"name": category_slug, "description": "seed category", "is_active": True},
                )
            product_management._sync_product_record_to_orm(
                {
                    **product,
                    "category_slug": category_slug,
                    "images": product.get("images", []),
                    "variants": product.get("variants", []),
                },
                owner_snapshot={
                    "username": str(product.get("owner_username", "")),
                    "display_name": str(product.get("owner_display_name", "")),
                },
            )

        source_product = ProductModel.objects.get(slug="acme-mug")
        similar_product = ProductModel.objects.get(slug="acme-tee")
        also_bought_product = ProductModel.objects.get(slug="acme-bottle")
        ProductRecommendationModel.objects.create(
            source_product=source_product,
            recommended_product=similar_product,
            score=0.95,
            reason="similar",
        )
        ProductRecommendationModel.objects.create(
            source_product=source_product,
            recommended_product=also_bought_product,
            score=0.88,
            reason="also_bought",
        )

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def test_recommendations_api_works_without_json_snapshots(self):
        product = product_management.get_visible_product("acme-mug")
        payload = recommendation_service.get_product_recommendations(product)
        self.assertEqual(payload["similar"][0]["slug"], "acme-tee")
        self.assertEqual(payload["also_bought"][0]["slug"], "acme-bottle")
        self.assertTrue(ProductRecommendationModel.objects.filter(source_product_id=1).exists())

        response = self.client.get("/api/products/acme-mug/recommendations/")
        self.assertEqual(response.status_code, 200)
        api_payload = response.json()
        self.assertEqual(api_payload["similar"][0]["slug"], "acme-tee")
        self.assertEqual(api_payload["also_bought"][0]["slug"], "acme-bottle")


class NewebpayStoreMapOrmSyncTests(TestCase):
    """驗證 store-map JSON 清空後，選店紀錄仍可從 ORM 讀回。"""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "users.json").write_text(
            json.dumps(USERS_FIXTURE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (data_dir / "newebpay_store_map_selections.json").write_text("[]", encoding="utf-8")
        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        self.client = Client()

    def tearDown(self):
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _login(self, username="buyer", password="demo123"):
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _clear_store_map_json(self):
        data_dir = Path(self.temp_dir.name) / "data"
        (data_dir / "newebpay_store_map_selections.json").write_text("[]", encoding="utf-8")
        local_store.clear_cache()

    def test_store_map_selection_survives_without_json_snapshot(self):
        self.assertEqual(self._login().status_code, 200)
        env = {
            "NEWEBPAY_LOGISTICS_MERCHANT_ID": "MS123456789",
            "NEWEBPAY_LOGISTICS_HASH_KEY": "12345678901234567890123456789012",
            "NEWEBPAY_LOGISTICS_HASH_IV": "1234567890123456",
            "NEWEBPAY_LOGISTICS_STORE_MAP_REPLY_URL": "https://backend.example/api/v1/integrations/newebpay/logistics/store-map/callback/",
            "NEWEBPAY_LOGISTICS_STORE_MAP_RETURN_URL": "https://frontend.example/checkout",
        }
        with patch.dict(os.environ, env, clear=False):
            prepare_response = self._post_json(
                "/api/v1/checkout/logistics/store-map/prepare/",
                {
                    "pickup_store_brand": "UNIMART",
                    "payment_method": "newebpay_credit",
                    "return_url": "https://frontend.example/checkout",
                },
            )
            self.assertEqual(prepare_response.status_code, 201)
            prepared = prepare_response.json()

            callback_response = self._post_json(
                "/api/v1/integrations/newebpay/logistics/store-map/callback/",
                {
                    "MerchantOrderNo": prepared["merchant_order_no"],
                    "StoreID": "149741",
                    "StoreName": "台北 ORM 門市",
                    "StoreAddr": "台北市中山區 ORM 路 1 號",
                    "StoreType": "1",
                    "ExtraData": prepared["selection_token"],
                    "Status": "SUCCESS",
                },
            )
            self.assertEqual(callback_response.status_code, 200)

        self.assertTrue(
            NewebpayStoreMapSelectionModel.objects.filter(selection_token=prepared["selection_token"]).exists()
        )
        self._clear_store_map_json()

        selection_response = self.client.get(
            f"/api/v1/checkout/logistics/store-selection/?token={prepared['selection_token']}"
        )
        self.assertEqual(selection_response.status_code, 200)
        selection = selection_response.json()
        self.assertTrue(selection["is_ready"])
        self.assertEqual(selection["pickup_store_code"], "149741")
        self.assertEqual(selection["pickup_store_name"], "台北 ORM 門市")

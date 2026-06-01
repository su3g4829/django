"""å°æ¡æ¸¬è©¦éåã

éè£¡ä¸»è¦ä½¿ç¨ `SimpleTestCase` æ­é
æ¬å° JSON fixtureï¼
é©è­é é¢æµç¨ãDRF APIãè³¼ç©è»ãè¨å®ãè³£å®¶ä¸­å¿èç®¡çå¾å°åè½ã
"""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings

from .repositories import local_store
from .services import auth_demo
from .services import newebpay_payment_real as newebpay_payment_real_service
from .services.privacy import anonymize_public_name


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


def build_extra_products():
    """å»ºç«é¡å¤åå fixtureã

    Returns:
        list[dict]: å ä¸å»¶ä¼¸ååå¾çæ¸¬è©¦è³æã
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
    """å»ºç«ååç®éæ¸¬è©¦å°ç¨ fixtureã

    Returns:
        list[dict]: åååè¡¨é æç¨å°çå®æ´æ¸¬è©¦ååè³æã
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
    """å»ºç«åæå
å«å
¬éèèç¨¿ååç fixtureã

    Returns:
        list[dict]: å¯ç¨ä¾é©è­å¯è¦æ§è¦åçååè³æã
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
    """å»ºç«è³£å®¶è¨å®ç¸éæ¸¬è©¦ååã

    Returns:
        list[dict]: å«è³£å®¶è³è¨çååè³æã
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
    """å»ºç«å«è®é«è SKU çæ¸¬è©¦ååã

    Returns:
        list[dict]: è®é«åè½æ¸¬è©¦ç¨ååè³æã
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
    """å»ºç«å±¬æ§éæ¿¾æ¸¬è©¦ç¨ååã

    Returns:
        list[dict]: å«é¡è²ãå°ºå¯¸ç­å±¬æ§çååè³æã
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


class ProductFeatureTests(SimpleTestCase):
    """é©è­ååãè³¼ç©æµç¨è API çä¸»è¦æ´åè¡çºã"""
    def setUp(self):
        """å»ºç«æ¸¬è©¦éè¦ç fixture è clientã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
        """
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        data_dir = base_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(data_dir / "products.json", PRODUCTS_FIXTURE)
        self._write_json(data_dir / "reviews.json", REVIEWS_FIXTURE)
        self._write_json(data_dir / "recommendations.json", RECOMMENDATIONS_FIXTURE)
        self._write_json(data_dir / "competitor_prices.json", COMPETITOR_PRICES_FIXTURE)
        self._write_json(data_dir / "questions.json", QUESTIONS_FIXTURE)
        self._write_json(data_dir / "posts.json", POSTS_FIXTURE)
        self._write_json(data_dir / "banners.json", BANNERS_FIXTURE)
        self._write_json(data_dir / "orders.json", ORDERS_FIXTURE)
        self._write_json(data_dir / "users.json", USERS_FIXTURE)

        self.override = override_settings(BASE_DIR=base_dir)
        self.override.enable()
        local_store.clear_cache()
        self.client = Client()

    def tearDown(self):
        """æ¸
çæ¸¬è©¦ç¨æ«å­æªè override settingsã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
        """
        local_store.clear_cache()
        self.override.disable()
        self.temp_dir.cleanup()

    def _write_json(self, path: Path, payload):
        """å°æ¸¬è©¦è³æå¯«å
¥ JSON æªæ¡ã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
            path: è¦å¯«å
¥çæªæ¡è·¯å¾ã
            payload: è¦å²å­ç Python è³æã
        """
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_products(self, products):
        """å¿«éè¦å¯« products fixture å
§å®¹ã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
            products: è¦å¯«å
¥çåå fixture æ¸
å®ã
        """
        data_dir = Path(self.temp_dir.name) / "data"
        self._write_json(data_dir / "products.json", products)
        local_store.clear_cache()

    def _post_json(self, path, payload):
        """ä»¥ JSON request body ç¼åº POST è«æ±ã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
            path: ç®æ¨è·¯ç±ã
            payload: è¦éåºç JSON payloadã
        """
        return self.client.post(path, data=json.dumps(payload), content_type="application/json")

    def _put_json(self, path, payload):
        """ä»¥ JSON request body ç¼åº PUT è«æ±ã

        Args:
            self: ç®åæ¸¬è©¦é¡å¥å¯¦ä¾ã
            path: ç®æ¨è·¯ç±ã
            payload: è¦éåºç JSON payloadã
        """
        return self.client.put(path, data=json.dumps(payload), content_type="application/json")

    def _patch_json(self, path, payload):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_patch_jsonã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
                    path: æ¸¬è©¦æè·¯ç±è·¯å¾ã
                    payload: è¦éåºæå¯«å¥çè³æã
                """
        return self.client.patch(path, data=json.dumps(payload), content_type="application/json")

    def _add_to_cart(self, qty=1):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_add_to_cartã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
                    qty: è©²æ¸¬è©¦ä½¿ç¨çåæ¸ã
                """
        return self._add_product_to_cart("acme-mug", qty=qty)

    def _add_product_to_cart(self, slug, qty=1, variant_id=""):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_add_product_to_cartã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
                    slug: åå slugã
                    qty: è©²æ¸¬è©¦ä½¿ç¨çåæ¸ã
                    variant_id: è©²æ¸¬è©¦ä½¿ç¨çåæ¸ã
                """
        payload = {"slug": slug, "qty": qty}
        if variant_id:
            payload["variant_id"] = variant_id
        return self._post_json("/api/v1/cart/items/", payload)

    def _login(self, username="alice", password="demo123", next_url="/"):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_loginã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
                    username: æå¡å¸³èã
                    password: è©²æ¸¬è©¦ä½¿ç¨çåæ¸ã
                    next_url: å®æåä½å¾è¦å°åçç¶²åã
                """
        return self._post_json("/api/v1/auth/login/", {"username": username, "password": password})

    def _logout(self):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_logoutã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
                """
        return self.client.post("/api/v1/auth/logout/")

    def _assert_frontend_redirect(self, response, path):
        """確認舊 Django HTML 路由已轉到 Next.js 前端。"""
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{settings.FRONTEND_ORIGIN}{path}")

    def _confirm_checkout(self):
        """æ¸¬è©¦è¼å©æ¹æ³ï¼_confirm_checkoutã
        
                Args:
                    self: ç¶åé¡å¥æ API view å¯¦ä¾ã
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

    def test_login_upgrades_legacy_plaintext_password(self):
        self._login()

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
                "author": "test@gmail.com",
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
        self.assertEqual(payload["similar"][0]["slug"], "acme-tee")
        self.assertEqual(payload["also_bought"][0]["slug"], "acme-bottle")

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
        self.assertEqual(response.json()["author"], anonymize_public_name("Alice"))

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
        self.assertEqual(payload["answers"][-1]["author"], anonymize_public_name("Alice"))

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
        self.assertEqual(response.json()["author"], anonymize_public_name("Alice"))

        stored_post = local_store.get_post_by_id(2)
        self.assertIsNotNone(stored_post)
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
        self.assertEqual(payload["author"], anonymize_public_name("Alice"))

    def test_community_editor_image_upload_api_saves_file(self):
        self._login()
        image = SimpleUploadedFile("forum.png", b"fake-image-bytes", content_type="image/png")

        response = self.client.post("/api/v1/community/uploads/images/", {"image": image})

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["path"].startswith("/static/uploads/community/community-"))
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
        self.assertEqual(stored_post["topic"], "care")
        self.assertEqual(stored_post["title"], "Updated storage checklist")
        self.assertEqual(stored_post["tags"], ["care", "bottle"])

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

    def test_product_price_compare_api_returns_live_data_for_supported_product(self):
        self._write_products(
            [
                {
                    "id": 8,
                    "slug": "new-forcepolo",
                    "name": "NEW FORCE Polo",
                    "price": 300.0,
                    "compare_at_price": 1200.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": ["polo"],
                    "images": [],
                    "specs": {"size": "L"},
                    "status": "active",
                    "stock": 1,
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )
        response = self.client.get("/api/v1/products/new-forcepolo/price-compare/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["is_mock"])
        self.assertEqual(payload["source_type"], "fixed_live_urls")
        self.assertEqual(payload["our_product_slug"], "new-forcepolo")
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("lowest_price", payload)

    def test_product_price_compare_refresh_api_updates_payload(self):
        self._write_products(
            [
                {
                    "id": 8,
                    "slug": "new-forcepolo",
                    "name": "NEW FORCE Polo",
                    "price": 300.0,
                    "compare_at_price": 1200.0,
                    "brand": "NEW FORCE",
                    "category": "apparel",
                    "tags": ["polo"],
                    "images": [],
                    "specs": {"size": "L"},
                    "status": "active",
                    "stock": 1,
                    "owner_username": "abc3",
                    "owner_display_name": "abc3",
                }
            ]
        )
        response = self.client.post("/api/v1/products/new-forcepolo/price-compare/refresh/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "價格比較已更新。")
        self.assertFalse(payload["result"]["is_mock"])
        self.assertEqual(payload["result"]["our_product_slug"], "new-forcepolo")

    def test_product_price_compare_api_rejects_unsupported_product(self):
        response = self.client.get("/api/v1/products/acme-mug/price-compare/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Price comparison is not enabled for this product.")

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

    def test_health_ready_endpoint_checks_cache_and_data_files(self):
        response = self.client.get("/health/ready/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["checks"]["cache"]["ok"])
        self.assertTrue(payload["checks"]["data_dir"]["ok"])

    def test_no_db_infrastructure_doc_page_loads(self):
        response = self.client.get("/docs/no-db-infrastructure/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No-DB \u57fa\u790e\u8a2d\u65bd")
        self.assertContains(response, "/health/live/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No-DB \u57fa\u790e\u8a2d\u65bd")
        self.assertContains(response, "/health/live/")

    def test_newebpay_payment_mock_api_can_create_and_fetch_record(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_response = self._confirm_checkout()
        order_id = order_response.json()["id"]

        create_response = self._post_json(
            f"/api/v1/me/orders/{order_id}/newebpay-payment/",
            {"return_url": "https://example.com/server-return", "client_back_url": "https://example.com/front-return"},
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["provider"], "NewebPay Payment")
        self.assertEqual(create_response.json()["status"], "pending")

        get_response = self.client.get(f"/api/v1/me/orders/{order_id}/newebpay-payment/")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["order_id"], order_id)

    def test_newebpay_payment_mock_callback_updates_status(self):
        self._login(username="buyer")
        self._add_product_to_cart("acme-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]
        create_response = self._post_json(f"/api/v1/me/orders/{order_id}/newebpay-payment/", {})
        trade_no = create_response.json()["trade_no"]

        callback_response = self._post_json(
            "/api/v1/integrations/newebpay/payment/callback/",
            {"trade_no": trade_no, "status": "paid", "paid_amount": "12.90", "result_message": "mock paid"},
        )
        self.assertEqual(callback_response.status_code, 200)
        self.assertEqual(callback_response.json()["record"]["status"], "paid")

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

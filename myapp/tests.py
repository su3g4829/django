"""å°æ¡æ¸¬è©¦éåã

éè£¡ä¸»è¦ä½¿ç¨ `SimpleTestCase` æ­é
æ¬å° JSON fixtureï¼
é©è­é é¢æµç¨ãDRF APIãè³¼ç©è»ãè¨å®ãè³£å®¶ä¸­å¿èç®¡çå¾å°åè½ã
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, override_settings

from .repositories import local_store


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
    }
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
            "id": 2,
            "slug": "acme-tee",
            "name": "ACME Tee",
            "price": 24.0,
            "brand": "ACME",
            "category": "apparel",
            "tags": ["shirt"],
            "images": [],
            "specs": {"size": "M"},
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
        return self.client.post("/api/v1/checkout/confirm/")

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
        self.assertEqual(response.json()["status"], "pending")
        product = local_store.get_product_by_slug("seller-mug")
        self.assertEqual(product["owner_username"], "alice")
        self.assertEqual(product["status"], "pending")
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
        self.assertEqual(updated["status"], "pending")
        self.assertEqual(updated["stock"], 3)

        self._logout()
        self._login(username="storeteam", next_url="/staff/reviews/")
        review_response = self._post_json(
            "/api/v1/staff/products/seller-active-mug/review/",
            {"approved": True, "note": "Looks good."},
        )
        self.assertEqual(review_response.status_code, 200)

        reviewed = local_store.get_product_by_slug("seller-active-mug")
        self.assertEqual(reviewed["status"], "active")

        self._logout()
        self._login(next_url="/me/products/")

        archive_response = self.client.post("/api/v1/me/products/seller-active-mug/archive/")
        self.assertEqual(archive_response.status_code, 200)

        archived = local_store.get_product_by_slug("seller-active-mug")
        self.assertEqual(archived["status"], "archived")
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
                "status": "pending",
                "specs": "material:ceramic",
                "stock": "2",
            },
        )
        self._logout()
        self._login(username="storeteam", next_url="/staff/reviews/")

        response = self._post_json(
            "/api/v1/staff/products/needs-review-mug/review/",
            {"approved": False, "note": "Please add clearer photos."},
        )

        self.assertEqual(response.status_code, 200)
        product = local_store.get_product_by_slug("needs-review-mug")
        self.assertEqual(product["status"], "rejected")
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
        self.assertEqual(payload["author"], "Alice")

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
        self.assertEqual(payload["answers"][-1]["author"], "Alice")

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
        self.assertEqual(payload["author"], "Alice")

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
        self.assertEqual(payload["replies"][-1]["author"], "Alice")

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

        response = self.client.post("/api/v1/checkout/confirm/")

        self.assertEqual(response.status_code, 201)
        stored_orders = local_store.get_orders_by_username("alice")
        self.assertEqual(len(stored_orders), 1)
        self.assertEqual(stored_orders[0]["display_name"], "Alice")
        self.assertEqual(stored_orders[0]["items"][0]["qty"], 2)
        self.assertEqual(self.client.session["cart"]["items"], {})

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

    def test_product_detail_and_cart_support_selected_variant(self):
        self._write_products(build_variant_products())

        detail_response = self.client.get("/products/acme-hoodie/")
        self._assert_frontend_redirect(detail_response, "/products/acme-hoodie")

        self._add_product_to_cart("acme-hoodie", qty=1, variant_id="navy-l")
        cart = self.client.session["cart"]
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
        self.assertEqual(payload["author"], "Buyer")

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
        self.assertEqual(compare_response.status_code, 200)
        self.assertTrue(compare_response.json()["active"])
        self.assertIn("acme-mug", self.client.session["compare_products"])

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
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["user"]["account_status"], "suspended")

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
        confirm_response = self.client.post("/api/v1/checkout/confirm/")
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
        self.assertEqual(create_response.json()["status"], "pending")
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
                    "name": "Pending Kettle",
                    "price": "39.00",
                    "brand": "ACME",
                    "category": "kitchen",
                    "tags": "pending",
                    "specs": "material:steel",
                    "status": "active",
                    "stock": "3",
                }
            ),
            content_type="application/json",
        )
        pending_slug = create_response.json()["slug"]
        self._logout()

        self._login(username="storeteam", next_url="/")
        dashboard_response = self.client.get("/api/v1/staff/reviews/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertTrue(dashboard_response.json()["seller_requests"])
        self.assertTrue(dashboard_response.json()["pending_products"])

        seller_review_response = self.client.post(
            "/api/v1/staff/seller-requests/buyer/review/",
            data=json.dumps({"approved": True}),
            content_type="application/json",
        )
        self.assertEqual(seller_review_response.status_code, 200)
        self.assertEqual(seller_review_response.json()["user"]["role"], "seller")

        product_review_response = self.client.post(
            f"/api/v1/staff/products/{pending_slug}/review/",
            data=json.dumps({"approved": True, "note": "Looks good."}),
            content_type="application/json",
        )
        self.assertEqual(product_review_response.status_code, 200)
        self.assertEqual(product_review_response.json()["status"], "active")

    def test_product_price_compare_api_returns_mock_data(self):
        response = self.client.get("/api/v1/products/acme-mug/price-compare/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_mock"])
        self.assertEqual(payload["our_product_slug"], "acme-mug")
        self.assertEqual(len(payload["items"]), 2)
        self.assertIn("lowest_price", payload)

    def test_product_price_compare_refresh_api_updates_payload(self):
        response = self.client.post("/api/v1/products/acme-mug/price-compare/refresh/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["detail"], "模擬抓價已更新。")
        self.assertTrue(payload["result"]["is_mock"])
        self.assertEqual(payload["result"]["our_product_slug"], "acme-mug")

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

    def test_newebpay_logistics_mock_api_can_create_and_fetch_record(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer")
        self._add_product_to_cart("alice-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]
        self._logout()

        self._login(username="alice")
        create_response = self._post_json(
            f"/api/v1/me/sales/{order_id}/newebpay-logistics/",
            {"store_type": "UNIMARTC2C", "temperature": "normal", "shipment_note": "mock shipment"},
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["provider"], "NewebPay Logistics")
        self.assertEqual(create_response.json()["status"], "created")

        get_response = self.client.get(f"/api/v1/me/sales/{order_id}/newebpay-logistics/")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["order_id"], order_id)

    def test_newebpay_logistics_mock_callback_updates_status(self):
        self._write_products(build_seller_order_products())
        self._login(username="buyer")
        self._add_product_to_cart("alice-mug", qty=1)
        order_id = self._confirm_checkout().json()["id"]
        self._logout()

        self._login(username="alice")
        create_response = self._post_json(f"/api/v1/me/sales/{order_id}/newebpay-logistics/", {})
        logistics_no = create_response.json()["logistics_no"]

        callback_response = self._post_json(
            "/api/v1/integrations/newebpay/logistics/callback/",
            {"logistics_no": logistics_no, "status": "picked_up", "result_message": "mock picked up"},
        )
        self.assertEqual(callback_response.status_code, 200)
        self.assertEqual(callback_response.json()["record"]["status"], "picked_up")

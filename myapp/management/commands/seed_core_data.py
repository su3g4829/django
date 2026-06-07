from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from django.contrib.auth.hashers import make_password

from myapp.models import (
    AppUser,
    AppUserRole,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductStatus,
    ProductTagRelation,
    ProductVariant,
    Tag,
)


class Command(BaseCommand):
    help = "建立第一波核心展示資料：abc / abc2 / abc3 賣家帳號、分類、品牌與商品。"

    @transaction.atomic
    def handle(self, *args, **options):
        tops = self._category("tops", "上衣")
        pants = self._category("pants", "褲子")

        abc = self._seller("abc", "abc@example.com", "abc")
        abc2 = self._seller("abc2", "abc2@example.com", "abc2")
        abc3 = self._seller("abc3", "abc3@example.com", "abc3")

        brand_abc = self._brand("abc-brand", "abc")
        brand_abc2 = self._brand("abc2-brand", "abc2")
        brand_abc3 = self._brand("abc3-brand", "abc3")

        self._simple_product(
            owner=abc,
            brand=brand_abc,
            category=tops,
            slug="abc-short-sleeve-top-1",
            name="短袖上衣1",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("590.00"),
            stock=20,
            image_paths=["/static/images/abc-短袖上衣1.png"],
            tags=["basic", "tops"],
        )
        self._simple_product(
            owner=abc,
            brand=brand_abc,
            category=tops,
            slug="abc-short-sleeve-top-2",
            name="短袖上衣2",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("590.00"),
            stock=20,
            image_paths=["/static/images/abc-短袖上衣2.png"],
            tags=["basic", "tops"],
        )
        self._simple_product(
            owner=abc,
            brand=brand_abc,
            category=tops,
            slug="abc-short-sleeve-top-3",
            name="短袖上衣3",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("590.00"),
            stock=20,
            image_paths=["/static/images/abc-短袖上衣3.png"],
            tags=["basic", "tops"],
        )
        self._simple_product(
            owner=abc,
            brand=brand_abc,
            category=pants,
            slug="abc-shorts-1",
            name="短褲1",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("490.00"),
            stock=18,
            image_paths=["/static/images/abc-短褲1.png"],
            tags=["basic", "pants"],
        )
        self._simple_product(
            owner=abc,
            brand=brand_abc,
            category=pants,
            slug="abc-shorts-2",
            name="短褲2",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("490.00"),
            stock=18,
            image_paths=["/static/images/abc-短褲2.png"],
            tags=["basic", "pants"],
        )

        self._variant_product(
            owner=abc2,
            brand=brand_abc2,
            category=tops,
            slug="abc2-long-sleeve-top",
            name="長袖上衣",
            description="同一商品下建立多個色系變體。",
            base_price=Decimal("790.00"),
            base_stock=24,
            variant_rows=[
                {"external_id": "white", "name": "白", "price": Decimal("790.00"), "stock": 6, "image": "/static/images/abc2-長袖上衣(白).png"},
                {"external_id": "gray", "name": "灰", "price": Decimal("790.00"), "stock": 6, "image": "/static/images/abc2-長袖上衣(灰).png"},
                {"external_id": "black", "name": "黑", "price": Decimal("790.00"), "stock": 6, "image": "/static/images/abc2-長袖上衣(黑).png"},
                {"external_id": "blue", "name": "藍", "price": Decimal("790.00"), "stock": 6, "image": "/static/images/abc2-長袖上衣(藍).png"},
            ],
            tags=["long-sleeve", "tops"],
        )

        self._simple_product(
            owner=abc3,
            brand=brand_abc3,
            category=tops,
            slug="abc3-new-force",
            name="NEW FORCE",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("890.00"),
            stock=15,
            image_paths=["/static/images/abc3-NEW FORCE.png"],
            tags=["tops", "new-force"],
        )
        self._simple_product(
            owner=abc3,
            brand=brand_abc3,
            category=pants,
            slug="abc3-shorts",
            name="短褲",
            description="以現有 static 圖片建立的展示商品。",
            price=Decimal("520.00"),
            stock=12,
            image_paths=["/static/images/abc3-短褲.png"],
            tags=["pants"],
        )

        self.stdout.write(self.style.SUCCESS("核心 seed 已建立：abc / abc2 / abc3 帳號與對應商品。"))
        self.stdout.write("已刻意略過 banner 檔案，不會把 banner 圖當商品圖匯入。")

    def _seller(self, username: str, email: str, display_name: str) -> AppUser:
        user, created = AppUser.objects.update_or_create(
            username=username,
            defaults={
                "email": email,
                "password_hash": make_password("demo12345"),
                "display_name": display_name,
                "role": AppUserRole.SELLER,
            },
        )
        verb = "建立" if created else "更新"
        self.stdout.write(f"{verb}賣家帳號：{username}")
        return user

    def _category(self, slug: str, name: str) -> Category:
        category, created = Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "is_active": True},
        )
        verb = "建立" if created else "更新"
        self.stdout.write(f"{verb}分類：{name}")
        return category

    def _brand(self, slug: str, name: str) -> Brand:
        brand, created = Brand.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "is_active": True},
        )
        verb = "建立" if created else "更新"
        self.stdout.write(f"{verb}品牌：{name}")
        return brand

    def _tag(self, raw_name: str) -> Tag:
        slug = slugify(raw_name) or raw_name.lower().replace(" ", "-")
        tag, _ = Tag.objects.get_or_create(slug=slug, defaults={"name": raw_name})
        return tag

    def _attach_tags(self, product: Product, tag_names: list[str]) -> None:
        for tag_name in tag_names:
            tag = self._tag(tag_name)
            ProductTagRelation.objects.get_or_create(product=product, tag=tag)

    def _simple_product(
        self,
        *,
        owner: AppUser,
        brand: Brand,
        category: Category,
        slug: str,
        name: str,
        description: str,
        price: Decimal,
        stock: int,
        image_paths: list[str],
        tags: list[str],
    ) -> Product:
        product, created = Product.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "price": price,
                "stock": stock,
                "status": ProductStatus.ACTIVE,
                "brand": brand,
                "category": category,
                "owner": owner,
                "owner_username_snapshot": owner.username,
                "owner_display_name_snapshot": owner.display_name,
            },
        )
        self._sync_images(product, image_paths)
        self._attach_tags(product, tags)
        verb = "建立" if created else "更新"
        self.stdout.write(f"{verb}商品：{owner.username} / {name}")
        return product

    def _variant_product(
        self,
        *,
        owner: AppUser,
        brand: Brand,
        category: Category,
        slug: str,
        name: str,
        description: str,
        base_price: Decimal,
        base_stock: int,
        variant_rows: list[dict[str, object]],
        tags: list[str],
    ) -> Product:
        product = self._simple_product(
            owner=owner,
            brand=brand,
            category=category,
            slug=slug,
            name=name,
            description=description,
            price=base_price,
            stock=base_stock,
            image_paths=[str(row["image"]) for row in variant_rows],
            tags=tags,
        )
        image_map = {image.file_path: image for image in product.images.all()}
        for row in variant_rows:
            image_path = str(row["image"])
            variant, created = ProductVariant.objects.update_or_create(
                product=product,
                external_variant_id=str(row["external_id"]),
                defaults={
                    "name": str(row["name"]),
                    "sku": f"{product.slug}-{row['external_id']}",
                    "price": row["price"],
                    "stock": row["stock"],
                    "image": image_map.get(image_path),
                    "image_path_snapshot": image_path,
                    "attributes": {"color": str(row["name"])},
                },
            )
            verb = "建立" if created else "更新"
            self.stdout.write(f"  {verb}變體：{product.slug} / {variant.name}")
        return product

    def _sync_images(self, product: Product, image_paths: list[str]) -> None:
        for index, image_path in enumerate(image_paths):
            ProductImage.objects.get_or_create(
                product=product,
                file_path=image_path,
                defaults={
                    "sort_order": index,
                    "alt_text": product.name,
                    "is_primary": index == 0,
                },
            )

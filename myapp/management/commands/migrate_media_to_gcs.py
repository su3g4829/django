from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from myapp.models import Banner, CommunityPost, CommunityReply, MediaAsset, ProductImage, ProductVariant
from myapp.repositories import local_store
from myapp.services import cloud_storage as cloud_storage_service


LOCAL_MEDIA_PREFIXES = (
    "/static/uploads/products/",
    "/static/uploads/banners/",
    "/static/uploads/community/",
    "/static/images/",
)
LOCAL_ORIGIN_PREFIXES = (
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
)


def normalize_legacy_media_path(value: str | None) -> str | None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return None
    parsed = urlsplit(clean_value)
    if parsed.scheme in {"http", "https"}:
        return unquote(parsed.path) if parsed.path.startswith("/static/") else None
    return unquote(clean_value) if clean_value.startswith("/static/") else None


def infer_object_name_from_legacy_path(value: str | None) -> str | None:
    legacy_path = normalize_legacy_media_path(value)
    if not legacy_path:
        return None
    file_name = Path(legacy_path).name
    if not file_name:
        return None
    if legacy_path.startswith("/static/uploads/products/"):
        return f"products/{file_name}"
    if legacy_path.startswith("/static/uploads/banners/"):
        return f"banners/{file_name}"
    if legacy_path.startswith("/static/uploads/community/"):
        return f"community/{file_name}"
    if legacy_path.startswith("/static/images/"):
        return f"images/{file_name}"
    return f"misc/{file_name}"


def replace_media_references(text: str | None, path_mapping: dict[str, str]) -> str:
    updated = str(text or "")
    if not updated:
        return updated
    for old_path, new_url in path_mapping.items():
        for origin in LOCAL_ORIGIN_PREFIXES:
            updated = updated.replace(f"{origin}{old_path}", new_url)
        updated = updated.replace(old_path, new_url)
    return updated


class Command(BaseCommand):
    help = "Upload legacy local media files to Google Cloud Storage and rewrite stored paths."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the migration without uploading files or saving updated records.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        if not cloud_storage_service.is_enabled():
            raise CommandError("GCS is not configured. Set GCS_BUCKET_NAME and a service account credential first.")

        self.path_mapping: dict[str, str] = {}
        self.missing_paths: list[str] = []
        self.uploaded_count = 0
        self.updated_records = 0

        json_changes = self._migrate_local_json(dry_run=dry_run)
        orm_changes = self._migrate_orm_records(dry_run=dry_run)

        if self.missing_paths:
            for path in sorted(set(self.missing_paths)):
                self.stdout.write(self.style.WARNING(f"Missing local file, skipped: {path}"))

        mode_label = "Dry run complete" if dry_run else "Migration complete"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode_label}. Uploaded {self.uploaded_count} unique file(s), "
                f"updated {self.updated_records} record(s), changed {json_changes + orm_changes} value(s)."
            )
        )

    def _resolve_local_file(self, value: str | None) -> Path | None:
        legacy_path = normalize_legacy_media_path(value)
        if not legacy_path:
            return None
        parts = [part for part in legacy_path.lstrip("/").split("/") if part]
        return Path(settings.BASE_DIR, *parts)

    def _ensure_gcs_url(self, value: str | None, *, dry_run: bool) -> str | None:
        legacy_path = normalize_legacy_media_path(value)
        if not legacy_path:
            return None
        if legacy_path in self.path_mapping:
            return self.path_mapping[legacy_path]

        object_name = infer_object_name_from_legacy_path(legacy_path)
        local_file = self._resolve_local_file(legacy_path)
        if not object_name or local_file is None or not local_file.exists():
            self.missing_paths.append(legacy_path)
            return None

        public_url = cloud_storage_service.build_public_url(object_name)
        if not dry_run:
            uploaded_url = cloud_storage_service.upload_file_path(local_file, object_name)
            if not uploaded_url:
                raise CommandError(f"Failed to upload {legacy_path} to GCS.")
            public_url = uploaded_url
            self.uploaded_count += 1
        self.path_mapping[legacy_path] = public_url
        return public_url

    def _migrate_local_json(self, *, dry_run: bool) -> int:
        changed_values = 0

        products = deepcopy(local_store.get_products())
        for product in products:
            images = list(product.get("images") or [])
            next_images = []
            touched = False
            for image_path in images:
                new_url = self._ensure_gcs_url(image_path, dry_run=dry_run)
                next_images.append(new_url or image_path)
                touched = touched or bool(new_url and new_url != image_path)
            if touched:
                product["images"] = next_images
                changed_values += 1

            variants = list(product.get("variants") or [])
            for variant in variants:
                image_path = str(variant.get("image") or "").strip()
                new_url = self._ensure_gcs_url(image_path, dry_run=dry_run)
                if new_url and new_url != image_path:
                    variant["image"] = new_url
                    if variant.get("image_path_snapshot"):
                        variant["image_path_snapshot"] = new_url
                    changed_values += 1
        if changed_values and not dry_run:
            local_store.save_products(products)
            self.updated_records += 1

        banner_changes = 0
        banners = deepcopy(local_store.get_banners())
        for banner in banners:
            image_path = str(banner.get("image_path") or "").strip()
            new_url = self._ensure_gcs_url(image_path, dry_run=dry_run)
            if new_url and new_url != image_path:
                banner["image_path"] = new_url
                banner_changes += 1
        if banner_changes and not dry_run:
            local_store.save_banners(banners)
            self.updated_records += 1
        changed_values += banner_changes

        post_changes = 0
        posts = deepcopy(local_store.get_posts())
        for post in posts:
            body = str(post.get("body") or "")
            new_body = replace_media_references(body, self._preview_mapping(body, dry_run=dry_run))
            if new_body != body:
                post["body"] = new_body
                post_changes += 1
            for reply in list(post.get("replies") or []):
                reply_body = str(reply.get("body") or "")
                new_reply_body = replace_media_references(reply_body, self._preview_mapping(reply_body, dry_run=dry_run))
                if new_reply_body != reply_body:
                    reply["body"] = new_reply_body
                    post_changes += 1
        if post_changes and not dry_run:
            local_store.save_posts(posts)
            self.updated_records += 1
        return changed_values + post_changes

    def _preview_mapping(self, text: str, *, dry_run: bool) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for prefix in LOCAL_MEDIA_PREFIXES:
            start = 0
            while True:
                index = text.find(prefix, start)
                if index < 0:
                    break
                end = index
                while end < len(text) and text[end] not in {'"', "'", "<", ">", " ", ")"}:
                    end += 1
                legacy_path = text[index:end]
                new_url = self._ensure_gcs_url(legacy_path, dry_run=dry_run)
                if new_url:
                    mapping[normalize_legacy_media_path(legacy_path) or legacy_path] = new_url
                start = end
        return mapping

    @transaction.atomic
    def _migrate_orm_records(self, *, dry_run: bool) -> int:
        changed_values = 0

        for image in ProductImage.objects.all():
            new_url = self._ensure_gcs_url(image.file_path, dry_run=dry_run)
            if new_url and new_url != image.file_path:
                changed_values += 1
                if not dry_run:
                    image.file_path = new_url
                    image.save(update_fields=["file_path", "updated_at"])

        for variant in ProductVariant.objects.exclude(image_path_snapshot=""):
            new_url = self._ensure_gcs_url(variant.image_path_snapshot, dry_run=dry_run)
            if new_url and new_url != variant.image_path_snapshot:
                changed_values += 1
                if not dry_run:
                    variant.image_path_snapshot = new_url
                    variant.save(update_fields=["image_path_snapshot", "updated_at"])

        for banner in Banner.objects.all():
            new_url = self._ensure_gcs_url(banner.image_path, dry_run=dry_run)
            if new_url and new_url != banner.image_path:
                changed_values += 1
                if not dry_run:
                    banner.image_path = new_url
                    banner.save(update_fields=["image_path", "updated_at"])

        for asset in MediaAsset.objects.all():
            new_url = self._ensure_gcs_url(asset.file_path, dry_run=dry_run)
            if new_url and new_url != asset.file_path:
                changed_values += 1
                if not dry_run:
                    asset.file_path = new_url
                    asset.file_name = Path(urlsplit(new_url).path).name
                    asset.save(update_fields=["file_path", "file_name", "updated_at"])

        for post in CommunityPost.objects.all():
            new_body = replace_media_references(post.body_html, self._preview_mapping(post.body_html, dry_run=dry_run))
            if new_body != post.body_html:
                changed_values += 1
                if not dry_run:
                    post.body_html = new_body
                    post.save(update_fields=["body_html", "updated_at"])

        for reply in CommunityReply.objects.all():
            new_body = replace_media_references(reply.body, self._preview_mapping(reply.body, dry_run=dry_run))
            if new_body != reply.body:
                changed_values += 1
                if not dry_run:
                    reply.body = new_body
                    reply.save(update_fields=["body", "updated_at"])

        if changed_values and not dry_run:
            self.updated_records += 5
        return changed_values

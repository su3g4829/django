from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from functools import lru_cache
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from django.core.files.uploadedfile import UploadedFile


PUBLIC_STORAGE_HOST = "storage.googleapis.com"


def _clean_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def get_project_id() -> str:
    return _clean_env("GCS_PROJECT_ID")


def get_bucket_name() -> str:
    return _clean_env("GCS_BUCKET_NAME")


def get_service_account_file() -> str:
    return _clean_env("GCS_SERVICE_ACCOUNT_FILE") or _clean_env("GOOGLE_APPLICATION_CREDENTIALS")


def get_public_base_url() -> str:
    custom_base = _clean_env("GCS_PUBLIC_BASE_URL").rstrip("/")
    if custom_base:
        return custom_base
    bucket_name = get_bucket_name()
    if not bucket_name:
        return ""
    return f"https://{PUBLIC_STORAGE_HOST}/{bucket_name}"


def is_enabled() -> bool:
    return bool(get_bucket_name() and (get_service_account_file() or _clean_env("GCS_SERVICE_ACCOUNT_JSON")))


@lru_cache(maxsize=1)
def _service_account_info() -> dict[str, Any] | None:
    raw = _clean_env("GCS_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    return json.loads(raw)


@lru_cache(maxsize=1)
def _storage_client():
    try:
        from google.cloud import storage
    except ModuleNotFoundError as exc:
        raise RuntimeError("google-cloud-storage is required when GCS storage is enabled.") from exc

    info = _service_account_info()
    project_id = get_project_id() or None
    if info is not None:
        return storage.Client.from_service_account_info(info, project=project_id)

    key_file = get_service_account_file()
    if key_file:
        return storage.Client.from_service_account_json(key_file, project=project_id)

    return storage.Client(project=project_id)


def build_public_url(object_name: str) -> str:
    base = get_public_base_url()
    encoded_object = quote(object_name.lstrip("/"), safe="/")
    return f"{base}/{encoded_object}" if base else ""


def upload_image(uploaded_file: UploadedFile, object_name: str) -> str | None:
    if not is_enabled():
        return None

    bucket_name = get_bucket_name()
    blob = _storage_client().bucket(bucket_name).blob(object_name.lstrip("/"))
    payload = b"".join(uploaded_file.chunks())
    blob.cache_control = "public, max-age=31536000"
    blob.upload_from_string(payload, content_type=str(uploaded_file.content_type or "application/octet-stream"))
    return build_public_url(object_name)


def upload_file_path(file_path: str | Path, object_name: str, content_type: str | None = None) -> str | None:
    if not is_enabled():
        return None

    path = Path(file_path)
    payload = path.read_bytes()
    guessed_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    blob = _storage_client().bucket(get_bucket_name()).blob(object_name.lstrip("/"))
    blob.cache_control = "public, max-age=31536000"
    blob.upload_from_string(payload, content_type=guessed_type)
    return build_public_url(object_name)


def object_name_from_public_url(public_url: str) -> str | None:
    if not public_url:
        return None

    parsed = urlsplit(str(public_url).strip())
    if parsed.scheme not in {"http", "https"}:
        return None

    bucket_name = get_bucket_name()
    if not bucket_name:
        return None

    host = parsed.netloc.lower()
    path = parsed.path.lstrip("/")
    if host != PUBLIC_STORAGE_HOST or not path.startswith(f"{bucket_name}/"):
        custom_base = get_public_base_url()
        if not custom_base or not str(public_url).startswith(custom_base):
            return None
        prefix = f"{custom_base}/"
        return unquote(str(public_url)[len(prefix):]) if str(public_url).startswith(prefix) else None

    return unquote(path[len(bucket_name) + 1 :])


def delete_by_public_url(public_url: str) -> bool:
    if not is_enabled():
        return False

    object_name = object_name_from_public_url(public_url)
    if not object_name:
        return False

    try:
        _storage_client().bucket(get_bucket_name()).blob(object_name).delete()
    except Exception:
        return False
    return True

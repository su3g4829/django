"""隱私相關 helper。

目前主要提供公開頁面作者名稱的去識別化處理，讓評論、問答、社群等
模組可以共用一致的顯示規則。
"""

from __future__ import annotations

import re


CHINESE_NAME_RE = re.compile(r"^[\u4e00-\u9fff]+$")
ENGLISH_NAME_RE = re.compile(r"^[A-Za-z]+(?:\s+[A-Za-z]+)*$")


def anonymize_public_name(name: str) -> str:
    # 公開頁面顯示作者名稱時，依資料型態選擇不同遮罩規則。
    normalized = (name or "").strip()
    if not normalized:
        return ""

    if "@" in normalized:
        local_part, _, domain = normalized.partition("@")
        visible_local = local_part[:2]
        return f"{visible_local}***@{domain}" if domain else f"{visible_local}***"

    if CHINESE_NAME_RE.fullmatch(normalized):
        return f"{normalized[0]}**"

    if ENGLISH_NAME_RE.fullmatch(normalized):
        return " ".join(f"{part[0]}***" for part in normalized.split())

    visible_prefix = normalized[:2]
    visible_suffix = normalized[-1] if len(normalized) > 2 else ""
    return f"{visible_prefix}***{visible_suffix}"

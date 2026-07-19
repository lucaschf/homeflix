"""Identifier enum for runtime-configurable setting buckets.

Each value corresponds to exactly one configuration VO persisted as a
single row in ``app_settings``. See ADR-013 for the grouping rationale.
"""

from enum import StrEnum


class SettingKey(StrEnum):
    """Stable, semantic identifier for a configuration bucket.

    The string value doubles as the primary key in ``app_settings`` and
    as the URL slug under ``/admin/settings/<key>``. Renaming a member
    is therefore a breaking change at the API and storage layers.
    """

    SCHEDULER = "scheduler"
    THUMBNAIL_BACKFILL = "thumbnail_backfill"
    INTRO_DETECTION = "intro_detection"
    CREDITS_DETECTION = "credits_detection"
    STREAMING = "streaming"
    AVATAR = "avatar"
    SCAN_DEDUP = "scan_dedup"
    SUBTITLE_OCR = "subtitle_ocr"
    ARTWORK_MIRROR = "artwork_mirror"


__all__ = ["SettingKey"]

"""Streaming module ORM models.

Importing this package registers the streaming tables on the shared
``Base.metadata`` (same pattern as the other modules), so a
``Base.metadata.create_all`` after importing it includes the
``subtitle_ocr_runs`` table.
"""

from src.modules.streaming.infrastructure.persistence.models.subtitle_ocr_run import (
    SubtitleOcrRunModel,
)

__all__ = ["SubtitleOcrRunModel"]

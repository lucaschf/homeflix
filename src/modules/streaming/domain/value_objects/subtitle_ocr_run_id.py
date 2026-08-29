"""SubtitleOcrRunId external id."""

from typing import ClassVar

from src.building_blocks.domain.external_id import ExternalId


class SubtitleOcrRunId(ExternalId):
    """External ID for subtitle-OCR audit runs.

    One row is appended per media file the OCR job (or manual trigger)
    processes that carries image-based subtitles. Format:
    ``sor_{base62_12chars}``.
    """

    EXPECTED_PREFIX: ClassVar[str] = "sor"


__all__ = ["SubtitleOcrRunId"]

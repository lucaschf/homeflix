"""Outcome enums for subtitle-OCR audit runs (ADR-027)."""

from enum import StrEnum


class SubtitleOcrOutcome(StrEnum):
    """Terminal outcome of OCR-ing one media file.

    Only files that carry image-based subtitles (or that fail) are
    recorded, so ``NO_IMAGE_SUBTITLES`` is not persisted — it exists to
    describe the in-memory result before the job decides whether to write
    an audit row.

    Attributes:
        COMPLETED: The file had image subtitles and each was processed
            (see per-track results for what actually extracted).
        NO_IMAGE_SUBTITLES: The file had no image subtitles — nothing to
            do. Not persisted as a run.
        FAILED: An unexpected error aborted processing the file.
    """

    COMPLETED = "completed"
    NO_IMAGE_SUBTITLES = "no_image_subtitles"
    FAILED = "failed"


class SubtitleTrackOutcome(StrEnum):
    """Per-track result of an OCR attempt.

    Attributes:
        EXTRACTED: OCR produced a text sidecar with at least one cue.
        NO_TEXT: OCR ran but produced no readable text (empty result).
        UNSUPPORTED_FORMAT: The bitmap format is not decodable (e.g.
            VOBSUB/IDX).
        NO_LANGUAGE_MODEL: The track language has no mappable / installed
            tesseract model.
        SKIPPED_LANGUAGE: The track language is outside the operator's
            configured ``languages`` allow-list.
        FAILED: Demux/parse/OCR raised for this track.
    """

    EXTRACTED = "extracted"
    NO_TEXT = "no_text"
    UNSUPPORTED_FORMAT = "unsupported_format"
    NO_LANGUAGE_MODEL = "no_language_model"
    SKIPPED_LANGUAGE = "skipped_language"
    FAILED = "failed"


__all__ = ["SubtitleOcrOutcome", "SubtitleTrackOutcome"]

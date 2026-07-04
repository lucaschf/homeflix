"""Subtitle OCR tunables — image-subtitle → text sidecar job (ADR-027 bucket)."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class SubtitleOcrConfig(CompoundValueObject):
    """Operational knobs for the image-subtitle OCR backfill job (ADR-027).

    Image-based subtitles (PGS/SUP) are not selectable in the player
    because HLS serves text WebVTT only. This job OCRs them to text
    sidecars that the probe then surfaces as external text tracks. OCR is
    expensive (tens of seconds per track) and best-effort, so the job is
    off by default and processes a small batch per tick.

    ``languages`` is a tuple (not a list) so the VO stays hashable like
    every other ``CompoundValueObject``. Empty means "OCR any track whose
    language maps to an installed tesseract model"; a non-empty tuple
    restricts to those ISO 639-1 codes.

    Attributes:
        enabled: Toggle for the periodic job. Off by default; requires
            ffmpeg + tesseract (with the relevant language data) on the
            host. See ADR-027.
        batch_size: Max media files processed per OCR tick. Each file may
            hold several image tracks and each OCRs hundreds of cues, so
            keep this small.
        interval_minutes: How often the OCR job runs.
        subdir: Subdirectory (relative to each media file's parent folder)
            where OCR sidecars + the per-file ``.ocr_done`` marker are
            written, nested under a per-stem leaf so episodes sharing a
            season folder do not collide.
        languages: ISO 639-1 codes to OCR. Empty = every track with a
            mappable, installed tesseract model.
        tesseract_binary: Name or absolute path of the tesseract
            executable (shelled out to like ffmpeg).
        per_cue_timeout_seconds: Hard timeout for a single tesseract
            invocation (one subtitle cue image). Bounds a stuck OCR call.

    Example:
        >>> cfg = SubtitleOcrConfig()
        >>> on = cfg.with_updates(enabled=True, languages=("en", "pt"))
    """

    enabled: bool = Field(default=False)
    batch_size: int = Field(default=2, ge=1)
    interval_minutes: int = Field(default=60, ge=1)
    subdir: str = Field(default=".homeflix/subtitles", min_length=1)
    languages: tuple[str, ...] = Field(default=())
    tesseract_binary: str = Field(default="tesseract", min_length=1)
    per_cue_timeout_seconds: int = Field(default=30, ge=1)


__all__ = ["SubtitleOcrConfig"]

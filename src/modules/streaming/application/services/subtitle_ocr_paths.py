"""Deterministic on-disk paths for OCR subtitle sidecars (ADR-027).

Pure path helpers shared by the OCR service, the surfacing step, the
backfill job, and the manual-trigger use case. Kept here (application)
rather than in the infrastructure OCR service so the application layer
can compute the sidecar location without importing infrastructure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.shared_kernel.value_objects.tracks import SubtitleTrack

#: Sentinel written into a file's OCR output dir once it has been
#: processed by the backfill job, so subsequent ticks skip it.
OCR_DONE_MARKER = ".ocr_done"


def ocr_subtitle_output_dir(source: Path, subdir: str) -> Path:
    """Return the deterministic per-stem OCR sidecar directory for a source.

    Mirrors ``scrub_preview_output_dir`` — ``<source-dir>/<subdir>/<stem>/``,
    one folder per media stem so episodes sharing a season directory don't
    collide. Centralised so the surfacing step (ADR-027) can predict an
    already-generated sidecar's location and the backfill job's per-file
    ``.ocr_done`` marker lives in a stable spot.

    Args:
        source: Absolute path to the source media file.
        subdir: Configured OCR sub-directory (e.g. ``.homeflix/subtitles``).

    Returns:
        The directory that holds (or would hold) this file's OCR sidecars.
    """
    return source.parent / subdir / source.stem


def ocr_sidecar_filename(track: SubtitleTrack) -> str:
    """Return the deterministic sidecar filename for an OCR'd track.

    Keyed by the source track's ``index`` and language so the surfacing
    step (ADR-027) can predict the path from the probed image track and
    check whether the OCR has already been produced. Example:
    ``ocr_s4_pt.vtt``.
    """
    return f"ocr_s{track.index}_{track.language.value.lower()}.vtt"


__all__ = ["OCR_DONE_MARKER", "ocr_sidecar_filename", "ocr_subtitle_output_dir"]

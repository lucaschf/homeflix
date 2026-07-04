"""Surface already-OCR'd image subtitles as external text tracks (ADR-027).

The OCR backfill job writes a text WebVTT sidecar next to each media
file for every image-based subtitle it processes. This module is the
read-time bridge: given a probe result, it appends — for each image
track whose sidecar exists on disk — a sibling *external text* track
pointing at that sidecar. The original image track is left untouched
(still filtered out downstream); the new text track flows through the
existing ``/tracks`` serialization, the HLS external-subtitle branch and
the ADR-026 default-subtitle selection unchanged.

Pure and idempotent: it reads only the base probe (which never carries
OCR tracks — the cache stores the base) plus the filesystem, and derives
the text tracks fresh each call, so applying it to ``/tracks`` and to the
HLS master playlist yields the same stable ``sub_N`` indices. Gated on
``SubtitleOcrConfig.enabled`` so it is a no-op until the operator turns
OCR on.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from src.modules.media.infrastructure.streaming.subtitle_ocr_service import (
    ocr_sidecar_filename,
    ocr_subtitle_output_dir,
)
from src.shared_kernel.value_objects.file_path import FilePath
from src.shared_kernel.value_objects.tracks import SubtitleTrack

if TYPE_CHECKING:
    from src.modules.media.application.ports.media_probe_port import ProbeResult
    from src.modules.settings.domain.value_objects import SubtitleOcrConfig

_logger = logging.getLogger(__name__)


def attach_ocr_subtitles(
    probe: ProbeResult,
    source_file: str,
    config: SubtitleOcrConfig,
) -> ProbeResult:
    """Return ``probe`` augmented with OCR text tracks for image subtitles.

    For each image-based subtitle whose deterministic OCR sidecar exists
    on disk, appends an external text ``SubtitleTrack`` (``format="vtt"``,
    ``is_external=True``, ``file_path`` = the sidecar) with a fresh index
    past every existing track, so it never collides with an existing
    ``sub_N`` rendition. The original image track is preserved.

    Args:
        probe: The base probe result (must not already carry OCR tracks).
        source_file: Absolute path to the source media file, used to
            locate the deterministic sidecar directory.
        config: Current subtitle-OCR config. When ``enabled`` is false,
            or no image track has a sidecar, ``probe`` is returned
            unchanged.

    Returns:
        Either ``probe`` itself or a copy with the OCR text tracks added
        to ``external_subtitles``.
    """
    if not config.enabled:
        return probe

    image_tracks = [t for t in probe.all_subtitles if t.is_image_based]
    if not image_tracks:
        return probe

    output_dir = ocr_subtitle_output_dir(Path(source_file), config.subdir)
    existing_indices = [t.index for t in probe.all_subtitles]
    next_index = max(existing_indices) + 1 if existing_indices else 0

    ocr_tracks: list[SubtitleTrack] = []
    for track in image_tracks:
        sidecar = output_dir / ocr_sidecar_filename(track)
        if not sidecar.is_file():
            continue
        ocr_tracks.append(
            SubtitleTrack(
                index=next_index,
                language=track.language,
                format="vtt",
                title=track.title,
                is_forced=track.is_forced,
                is_external=True,
                file_path=FilePath(str(sidecar)),
            )
        )
        next_index += 1

    if not ocr_tracks:
        return probe

    _logger.debug(
        "[subtitle-ocr] surfacing OCR text tracks",
        extra={"count": len(ocr_tracks), "source": source_file},
    )
    return replace(
        probe,
        external_subtitles=[*probe.external_subtitles, *ocr_tracks],
    )


__all__ = ["attach_ocr_subtitles"]

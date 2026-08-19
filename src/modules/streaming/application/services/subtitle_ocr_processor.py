"""Application service: OCR one media file's image subtitles (ADR-027).

Shared by the periodic backfill job and the manual trigger so both
produce the same per-track report (which feeds the ``subtitle_ocr_runs``
audit log). Synchronous — probe + OCR are subprocess-bound — so callers
dispatch it via ``asyncio.to_thread``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.modules.streaming.domain.entities.subtitle_ocr_run import SubtitleTrackOcrResult
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import (
    SubtitleOcrOutcome,
    SubtitleTrackOutcome,
)

if TYPE_CHECKING:
    from pathlib import Path

    from src.modules.streaming.application.ports.subtitle_ocr_port import (
        SubtitleOcrOptions,
        SubtitleOcrPort,
    )
    from src.shared_kernel.media_probe.media_probe_port import MediaProbePort


@dataclass(frozen=True)
class FileOcrReport:
    """Result of OCR-ing one media file's image subtitle tracks.

    Attributes:
        outcome: ``NO_IMAGE_SUBTITLES`` when the file carries none;
            ``COMPLETED`` when image tracks were processed.
        image_track_count: How many image subtitle tracks the file had.
        track_results: Per-track OCR detail (empty when no image tracks).
    """

    outcome: SubtitleOcrOutcome
    image_track_count: int = 0
    track_results: list[SubtitleTrackOcrResult] = field(default_factory=list)

    @property
    def extracted_count(self) -> int:
        """Tracks that produced a text sidecar."""
        return sum(1 for r in self.track_results if r.outcome == SubtitleTrackOutcome.EXTRACTED)


class SubtitleOcrProcessor:
    """OCR every image subtitle track of a single file (best-effort).

    Args:
        probe_service: Discovers the file's subtitle tracks.
        ocr_service: The OCR engine.
    """

    def __init__(self, probe_service: MediaProbePort, ocr_service: SubtitleOcrPort) -> None:
        self._probe = probe_service
        self._ocr = ocr_service

    def process_file(
        self,
        source_file: str,
        output_dir: Path,
        options: SubtitleOcrOptions,
        language_filter: frozenset[str] | None,
    ) -> FileOcrReport:
        """Probe ``source_file`` and OCR each image subtitle track.

        Args:
            source_file: Absolute path to the media file.
            output_dir: Directory sidecars are written into.
            options: OCR knobs.
            language_filter: Lowercased ISO codes to OCR, or ``None`` for
                every mappable language. Tracks outside the set are
                recorded as ``SKIPPED_LANGUAGE`` without running OCR.

        Returns:
            A :class:`FileOcrReport` with the per-track outcomes.
        """
        probe = self._probe.probe(source_file)
        image_tracks = [t for t in probe.all_subtitles if t.is_image_based]
        if not image_tracks:
            return FileOcrReport(outcome=SubtitleOcrOutcome.NO_IMAGE_SUBTITLES)

        results: list[SubtitleTrackOcrResult] = []
        for track in image_tracks:
            language = track.language.value
            if language_filter is not None and language.lower() not in language_filter:
                results.append(
                    SubtitleTrackOcrResult(
                        track_index=track.index,
                        language=language,
                        outcome=SubtitleTrackOutcome.SKIPPED_LANGUAGE,
                    )
                )
                continue
            result = self._ocr.ocr_track(source_file, track, output_dir, options)
            results.append(
                SubtitleTrackOcrResult(
                    track_index=track.index,
                    language=language,
                    outcome=result.outcome,
                    cue_count=result.cue_count,
                )
            )
        return FileOcrReport(
            outcome=SubtitleOcrOutcome.COMPLETED,
            image_track_count=len(image_tracks),
            track_results=results,
        )


__all__ = ["FileOcrReport", "SubtitleOcrProcessor"]

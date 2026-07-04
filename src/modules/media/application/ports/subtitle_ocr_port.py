"""Port for OCR-ing an image-based subtitle track into a text sidecar.

The subtitle-OCR backfill job (ADR-027) hands the port a source media
file plus one image-based subtitle track and receives, on success, the
path to a WebVTT sidecar it wrote. The implementation owns the full
pipeline — demuxing the bitmap stream, decoding it, running OCR — behind
this single abstraction, so the orchestrating job never binds to a
particular OCR engine.

The concrete implementation lives in the infrastructure layer
(:class:`TesseractPgsOcrService`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from src.shared_kernel.value_objects.tracks import SubtitleTrack


@dataclass(frozen=True)
class SubtitleOcrOptions:
    """Per-call OCR knobs forwarded by the job from runtime settings.

    Passed per :meth:`SubtitleOcrPort.ocr_track` call so the
    implementation stays stateless with respect to configuration — the
    job snapshots :class:`SubtitleOcrConfig` and forwards the relevant
    fields, letting admin edits apply on the next tick.

    Attributes:
        tesseract_binary: Name or absolute path of the tesseract
            executable.
        per_cue_timeout_seconds: Hard timeout for a single tesseract
            invocation (one cue image).
        ffmpeg_threads: Cap forwarded to the extraction ffmpeg call, or
            ``None`` for ffmpeg's default. Mirrors the shared streaming
            thread cap so OCR extraction respects the same limit.
    """

    tesseract_binary: str = "tesseract"
    per_cue_timeout_seconds: int = 30
    ffmpeg_threads: int | None = None


class SubtitleOcrPort(ABC):
    """OCR a single image-based subtitle track into a WebVTT sidecar."""

    @abstractmethod
    def ocr_track(
        self,
        source_file: str,
        track: SubtitleTrack,
        output_dir: Path,
        options: SubtitleOcrOptions,
    ) -> Path | None:
        """OCR one image-based subtitle track to a WebVTT file on disk.

        Implementations own the full pipeline: demux/read the bitmap
        stream (from ``source_file`` at ``track.index`` for embedded
        tracks, or from ``track.file_path`` for external ones), decode
        it, OCR each cue, and write a ``.vtt`` into ``output_dir`` at a
        deterministic name derived from the track. Degrades to ``None``
        rather than raising when the track cannot be processed (missing
        source, unsupported bitmap format, no installed language model,
        empty OCR result).

        Args:
            source_file: Absolute path to the source media file.
            track: The image-based subtitle track to OCR. Its
                ``language`` selects the OCR model and its ``index`` /
                external ``file_path`` locate the bitmap stream.
            output_dir: Directory the sidecar is written into (created if
                absent).
            options: OCR knobs snapshotted from runtime settings.

        Returns:
            The path to the written WebVTT sidecar, or ``None`` if the
            track could not be OCR'd.
        """
        ...


__all__ = ["SubtitleOcrOptions", "SubtitleOcrPort"]

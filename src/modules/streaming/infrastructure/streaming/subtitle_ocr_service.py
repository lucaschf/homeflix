"""Tesseract-backed OCR of image-based (PGS) subtitles into WebVTT.

Implements :class:`SubtitleOcrPort` (ADR-027). Given a source media file
and one image-based subtitle track, it demuxes the PGS bitmap stream
with ffmpeg, decodes it (:mod:`pgs_parser`), OCRs each cue with tesseract,
and writes a WebVTT sidecar next to the media at a deterministic path.

Synchronous (subprocess-based), like :class:`ThumbnailGenerationService`;
callers that must not block the event loop dispatch it via
``asyncio.to_thread``. Every failure mode degrades to ``None`` rather
than raising — OCR is best-effort and must never break the calling job.

Only PGS/SUP bitmap subtitles are supported. VOBSUB/IDX use a different
bitmap layout and return ``None`` (logged) for now.
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from src.modules.streaming.application.ports.subtitle_ocr_port import (
    OcrTrackResult,
    SubtitleOcrOptions,
    SubtitleOcrPort,
)
from src.modules.streaming.application.services.subtitle_ocr_paths import (
    ocr_sidecar_filename,
    ocr_subtitle_output_dir,
)
from src.modules.streaming.domain.value_objects.subtitle_ocr_outcome import SubtitleTrackOutcome
from src.modules.streaming.infrastructure.streaming._subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)
from src.modules.streaming.infrastructure.streaming.pgs_parser import parse_pgs

if TYPE_CHECKING:
    from src.modules.streaming.infrastructure.streaming.pgs_parser import PgsCue
    from src.shared_kernel.value_objects.tracks import SubtitleTrack

_logger = logging.getLogger(__name__)

# Seconds allowed for the demux of one subtitle stream. The demux reads
# through the whole container, so this is generous.
_EXTRACT_TIMEOUT = 1800

# PGS/SUP formats this service can decode. Others (vobsub/idx) are a
# different bitmap layout and skipped.
_SUPPORTED_FORMATS = frozenset({"pgs", "sup"})

# ISO 639-1 (LanguageCode) → tesseract 639-2/T model name. Only the
# common subtitle languages; unmapped codes are skipped (logged).
_ISO_TO_TESSERACT: dict[str, str] = {
    "en": "eng",
    "pt": "por",
    "fr": "fra",
    "es": "spa",
    "de": "deu",
    "it": "ita",
    "nl": "nld",
    "pl": "pol",
    "ru": "rus",
    "sv": "swe",
    "no": "nor",
    "da": "dan",
    "fi": "fin",
    "tr": "tur",
    "cs": "ces",
    "ja": "jpn",
    "ko": "kor",
    "zh": "chi_sim",
    "ar": "ara",
    "hi": "hin",
}


class TesseractPgsOcrService(SubtitleOcrPort):
    """OCR PGS subtitle tracks to WebVTT sidecars with tesseract.

    Caches the set of installed tesseract language models per binary so
    a track whose language model is missing is skipped cheaply without
    running OCR that would only yield garbage.
    """

    def __init__(self) -> None:
        self._installed_langs: dict[str, frozenset[str]] = {}

    def available_languages(self, tesseract_binary: str) -> frozenset[str]:
        """See :meth:`SubtitleOcrPort.available_languages`."""
        return self._available_langs(tesseract_binary)

    def ocr_track(
        self,
        source_file: str,
        track: SubtitleTrack,
        output_dir: Path,
        options: SubtitleOcrOptions,
    ) -> OcrTrackResult:
        """See :meth:`SubtitleOcrPort.ocr_track`."""
        decoded = self._decode_cues(source_file, track, output_dir, options)
        if isinstance(decoded, SubtitleTrackOutcome):
            return OcrTrackResult(outcome=decoded)
        model, cues = decoded

        vtt_cues = self._ocr_cues(cues, model, options)
        if not vtt_cues:
            _logger.info(
                "[subtitle-ocr] OCR produced no text; skipping",
                extra={"index": track.index, "source": source_file},
            )
            return OcrTrackResult(outcome=SubtitleTrackOutcome.NO_TEXT)

        output_dir.mkdir(parents=True, exist_ok=True)
        vtt_path = output_dir / ocr_sidecar_filename(track)
        vtt_path.write_text(_render_vtt(vtt_cues), encoding="utf-8")
        _logger.info(
            "[subtitle-ocr] wrote OCR sidecar",
            extra={"cues": len(vtt_cues), "path": str(vtt_path)},
        )
        return OcrTrackResult(
            outcome=SubtitleTrackOutcome.EXTRACTED,
            vtt_path=vtt_path,
            cue_count=len(vtt_cues),
        )

    def _decode_cues(
        self,
        source_file: str,
        track: SubtitleTrack,
        output_dir: Path,
        options: SubtitleOcrOptions,
    ) -> tuple[str, list[PgsCue]] | SubtitleTrackOutcome:
        """Resolve the OCR model and decode the track's bitmap cues.

        Returns ``(model, cues)`` when the track is a supported bitmap
        format with an installed language model and at least one decodable
        cue; otherwise a :class:`SubtitleTrackOutcome` (logged) naming the
        first guard that failed.
        """
        if track.format.lower() not in _SUPPORTED_FORMATS:
            _logger.debug(
                "[subtitle-ocr] unsupported bitmap format; skipping",
                extra={"format": track.format, "index": track.index},
            )
            return SubtitleTrackOutcome.UNSUPPORTED_FORMAT

        model = self._resolve_model(track, options.tesseract_binary)
        if model is None:
            return SubtitleTrackOutcome.NO_LANGUAGE_MODEL

        raw = self._read_pgs_bytes(source_file, track, output_dir, options.ffmpeg_threads)
        if raw is None:
            return SubtitleTrackOutcome.FAILED

        try:
            cues = parse_pgs(raw)
        except ValueError:
            _logger.warning(
                "[subtitle-ocr] not a valid PGS stream; skipping",
                extra={"index": track.index, "source": source_file},
            )
            return SubtitleTrackOutcome.FAILED
        if not cues:
            return SubtitleTrackOutcome.NO_TEXT
        return model, cues

    # -- language models -------------------------------------------------------

    def _resolve_model(self, track: SubtitleTrack, binary: str) -> str | None:
        """Map the track language to an installed tesseract model, or None."""
        model = _ISO_TO_TESSERACT.get(track.language.value.lower())
        if model is None:
            _logger.info(
                "[subtitle-ocr] no tesseract model for language; skipping",
                extra={"language": track.language.value, "index": track.index},
            )
            return None
        if model not in self._available_langs(binary):
            _logger.warning(
                "[subtitle-ocr] tesseract model not installed; skipping",
                extra={"model": model, "language": track.language.value},
            )
            return None
        return model

    def _available_langs(self, binary: str) -> frozenset[str]:
        """Installed tesseract models for ``binary`` (cached per process)."""
        cached = self._installed_langs.get(binary)
        if cached is not None:
            return cached
        langs: frozenset[str] = frozenset()
        try:
            result = subprocess.run(
                [binary, "--list-langs"],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=30,
            )
            # tesseract prints a header line then one model per line;
            # some builds emit it on stderr. Keep bare model tokens.
            combined = f"{result.stdout}\n{result.stderr}"
            langs = frozenset(
                line.strip()
                for line in combined.splitlines()
                if re.fullmatch(r"[a-z_]{2,}", line.strip())
            )
        except (OSError, subprocess.SubprocessError):
            _logger.exception("[subtitle-ocr] could not list tesseract languages")
        self._installed_langs[binary] = langs
        return langs

    # -- bitmap source ---------------------------------------------------------

    def _read_pgs_bytes(
        self,
        source_file: str,
        track: SubtitleTrack,
        output_dir: Path,
        ffmpeg_threads: int | None,
    ) -> bytes | None:
        """Return the raw PGS stream for the track, demuxing if embedded."""
        if track.is_external:
            if track.file_path is None:
                return None
            try:
                return _read_file(track.file_path.value)
            except OSError:
                _logger.warning(
                    "[subtitle-ocr] external subtitle unreadable; skipping",
                    extra={"path": track.file_path.value},
                )
                return None
        return self._demux_embedded(source_file, track.index, output_dir, ffmpeg_threads)

    def _demux_embedded(
        self,
        source_file: str,
        stream_index: int,
        output_dir: Path,
        ffmpeg_threads: int | None,
    ) -> bytes | None:
        """Copy an embedded PGS stream to a temp ``.sup`` and read it back."""
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_sup = output_dir / f"_extract_s{stream_index}.sup"
        cmd = with_ffmpeg_threads(
            [
                "ffmpeg",
                "-i",
                source_file,
                "-map",
                f"0:s:{stream_index}",
                "-c:s",
                "copy",
                "-f",
                "sup",
                "-loglevel",
                "error",
                "-y",
                str(temp_sup),
            ],
            ffmpeg_threads,
        )
        try:
            result = subprocess.run(
                cmd,
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=_EXTRACT_TIMEOUT,
            )
            if result.returncode != 0 or not temp_sup.is_file():
                _logger.warning(
                    "[subtitle-ocr] PGS demux failed; skipping",
                    extra={"index": stream_index, "source": source_file},
                )
                return None
            return temp_sup.read_bytes()
        except subprocess.TimeoutExpired:
            _logger.warning(
                "[subtitle-ocr] PGS demux timed out; skipping",
                extra={"index": stream_index, "source": source_file},
            )
            return None
        finally:
            temp_sup.unlink(missing_ok=True)

    # -- OCR -------------------------------------------------------------------

    def _ocr_cues(
        self,
        cues: list[PgsCue],
        model: str,
        options: SubtitleOcrOptions,
    ) -> list[tuple[int, int, str]]:
        """OCR each cue, dropping ones that yield no text."""
        out: list[tuple[int, int, str]] = []
        for cue in cues:
            text = self._ocr_one(cue, model, options)
            if text:
                out.append((cue.start_ms, cue.end_ms, text))
        return out

    def _ocr_one(self, cue: PgsCue, model: str, options: SubtitleOcrOptions) -> str:
        """Run tesseract on a single cue image, returning cleaned text."""
        png = _to_ocr_png(cue.image)
        try:
            result = subprocess.run(
                [options.tesseract_binary, "stdin", "stdout", "-l", model, "--psm", "6"],
                input=png,
                capture_output=True,
                check=False,
                timeout=options.per_cue_timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError):
            _logger.exception("[subtitle-ocr] tesseract invocation failed")
            return ""
        return _clean_ocr_text(result.stdout.decode("utf-8", errors="replace"))


def _read_file(path: str) -> bytes:
    return Path(path).read_bytes()


def _to_ocr_png(image: Image.Image) -> bytes:
    """Composite the RGBA subtitle over black and invert to dark-on-light.

    PGS glyphs are light with a dark outline on a transparent
    background; compositing over black then inverting yields black text
    on white, which tesseract reads best.
    """
    background = Image.new("RGB", image.size, (0, 0, 0))
    background.paste(image, mask=image.split()[3])
    prepared = ImageOps.invert(ImageOps.grayscale(background))
    buffer = io.BytesIO()
    prepared.save(buffer, format="PNG")
    return buffer.getvalue()


# tesseract reads a standalone "I" as a pipe; in subtitle text a pipe is
# almost always a misread I, so normalise it back.
_PIPE_RE = re.compile(r"\|")


def _clean_ocr_text(text: str) -> str:
    """Trim tesseract output and fix its standard ``I`` → ``|`` misread."""
    fixed = _PIPE_RE.sub("I", text)
    lines = [line.strip() for line in fixed.splitlines() if line.strip()]
    return "\n".join(lines)


def _ms_to_vtt(ms: int) -> str:
    """Format milliseconds as a WebVTT timestamp ``HH:MM:SS.mmm``."""
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    seconds, ms = divmod(ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"


def _render_vtt(cues: list[tuple[int, int, str]]) -> str:
    """Render OCR'd cues as a WebVTT document."""
    blocks = ["WEBVTT", ""]
    for start_ms, end_ms, text in cues:
        blocks.append(f"{_ms_to_vtt(start_ms)} --> {_ms_to_vtt(end_ms)}")
        blocks.append(text)
        blocks.append("")
    return "\n".join(blocks)


__all__ = [
    "TesseractPgsOcrService",
    "ocr_sidecar_filename",
    "ocr_subtitle_output_dir",
]

"""ffmpeg wrapper that extracts a leading audio segment to a temp WAV.

The audio is downmixed to mono at a low sample rate suited to acoustic
fingerprinting (Chromaprint internally resamples to 11025 Hz). Output
is a regular WAV so any downstream consumer can read it without
binding to a specific codec.

The wrapper is synchronous; async callers should use
``await asyncio.to_thread(extractor.extract, ...)`` — same pattern as
``HlsService._start_generation``.
"""

from __future__ import annotations

import functools
import logging
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from src.modules.media.infrastructure.streaming._subprocess import (
    SUBPROCESS_TEXT_KWARGS,
    with_ffmpeg_threads,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from src.modules.settings.infrastructure.runtime_settings import RuntimeSettings

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 60
_DEFAULT_SAMPLE_RATE = 11025
_TEMP_FILE_PREFIX = "homeflix_intro_audio_"


@functools.lru_cache(maxsize=1)
def _ffmpeg_path() -> str | None:
    """Return the resolved path to ffmpeg, or ``None`` if not on PATH.

    Cached so the lookup runs once per process and the missing-binary
    warning is logged at most once even across many extractions.
    """
    path = shutil.which("ffmpeg")
    if path is None:
        _logger.warning("ffmpeg not found — audio extraction disabled")
    return path


class AudioExtractor:
    """Extract a leading mono WAV segment from a media file via ffmpeg.

    Attributes:
        timeout_seconds: Per-extraction subprocess timeout. Defaults to 60s
            because audio decode of a 10-min window on a typical host
            comfortably finishes in well under a minute.
        sample_rate: Output sample rate (Hz). Defaults to 11025 — high
            enough for fingerprinting and low enough to keep the temp
            file small.
        runtime_settings: Snapshot facade for :class:`StreamingConfig`;
            ``ffmpeg_threads`` is read via the sync snapshot on every
            extraction so admin edits take effect on the next call.

    Example:
        >>> extractor = AudioExtractor(runtime_settings=runtime_settings)
        >>> with extractor.extract_temporary(
        ...     "/series/show/s01e01.mkv",
        ...     duration_seconds=600,
        ... ) as wav_path:
        ...     # consumer reads wav_path, file is unlinked on exit
        ...     ...
    """

    def __init__(
        self,
        runtime_settings: RuntimeSettings,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._runtime_settings = runtime_settings
        self._timeout = timeout_seconds
        self._sample_rate = sample_rate

    def extract(self, file_path: str, duration_seconds: int) -> Path | None:
        """Extract the first ``duration_seconds`` of audio to a temp WAV.

        Args:
            file_path: Absolute path to the source media file.
            duration_seconds: Length of the leading audio window to keep.

        Returns:
            Absolute :class:`Path` to a newly-created temp WAV, or
            ``None`` if ffmpeg is missing or the extraction failed.
            Callers own the returned file and must unlink it; use
            :meth:`extract_temporary` for automatic cleanup.
        """
        ffmpeg = _ffmpeg_path()
        if ffmpeg is None:
            return None

        if duration_seconds <= 0:
            _logger.error("duration_seconds must be positive (got %d)", duration_seconds)
            return None

        # ``delete=False`` because ffmpeg writes to the path we hand it;
        # the caller (or extract_temporary) is responsible for cleanup.
        # Closing the handle right away avoids holding a Windows file
        # lock that would block ffmpeg on win32 hosts.
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=_TEMP_FILE_PREFIX,
            suffix=".wav",
            delete=False,
        )
        output_path = Path(handle.name)
        handle.close()

        cmd = with_ffmpeg_threads(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                file_path,
                "-t",
                str(duration_seconds),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(self._sample_rate),
                "-f",
                "wav",
                str(output_path),
            ],
            self._runtime_settings.streaming_snapshot_sync().ffmpeg_threads,
        )

        if _run_ffmpeg(cmd, file_path, output_path, self._timeout):
            return output_path

        output_path.unlink(missing_ok=True)
        return None

    @contextmanager
    def extract_temporary(self, file_path: str, duration_seconds: int) -> Iterator[Path | None]:
        """Context-manager wrapper around :meth:`extract` with cleanup.

        Yields the temp WAV path (or ``None`` on failure) and unlinks
        the file when the block exits, regardless of whether the
        consumer raised.
        """
        output = self.extract(file_path, duration_seconds)
        try:
            yield output
        finally:
            if output is not None:
                output.unlink(missing_ok=True)


def _run_ffmpeg(
    cmd: list[str],
    source_path: str,
    output_path: Path,
    timeout: int,
) -> bool:
    """Run ffmpeg and verify the output is a non-empty file.

    Returns ``True`` only when the subprocess exited cleanly *and* the
    output path exists with non-zero size. ffmpeg occasionally exits 0
    while writing nothing (codec edge cases, truncated source); treating
    that as a failure keeps downstream consumers from seeing a path that
    points to nothing useful.

    Args:
        cmd: Full ffmpeg argv (already wrapped with the threads cap).
        source_path: Original source file, only used for log context.
        output_path: Path ffmpeg was told to write to.
        timeout: subprocess timeout in seconds.

    Returns:
        ``True`` on a clean run with non-empty output; ``False``
        otherwise (the caller is expected to unlink ``output_path``).
    """
    try:
        result = subprocess.run(
            cmd,
            **SUBPROCESS_TEXT_KWARGS,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        _logger.warning("ffmpeg audio extraction timed out for %s", source_path)
        return False
    except OSError:
        _logger.exception("ffmpeg audio extraction crashed for %s", source_path)
        return False

    if result.returncode != 0:
        _logger.error(
            "ffmpeg audio extraction failed for %s (exit=%d): %s",
            source_path,
            result.returncode,
            result.stderr.strip() if result.stderr else "",
        )
        return False

    if not output_path.exists() or output_path.stat().st_size == 0:
        _logger.error(
            "ffmpeg exited 0 but produced no audio output for %s",
            source_path,
        )
        return False

    return True


__all__ = ["AudioExtractor"]

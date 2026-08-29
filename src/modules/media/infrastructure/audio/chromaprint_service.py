"""fpcalc (Chromaprint) wrapper that produces raw audio fingerprints.

The raw fingerprint is a sequence of unsigned 32-bit hashes, one per
~0.124s of audio, designed for cross-correlation across recordings.
We surface them as ``list[int]`` together with the duration that
fpcalc reported so callers can align timestamps with sample indices.

The wrapper is synchronous; async callers should use
``await asyncio.to_thread(service.fingerprint, ...)``.
"""

import functools
import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.modules.streaming.infrastructure.streaming._subprocess import SUBPROCESS_TEXT_KWARGS

_logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30


@functools.lru_cache(maxsize=1)
def _fpcalc_path() -> str | None:
    """Return the resolved path to ``fpcalc``, or ``None`` if not on PATH.

    Cached so the lookup runs once per process and the missing-binary
    warning is logged at most once even across many fingerprinting
    calls.
    """
    path = shutil.which("fpcalc")
    if path is None:
        _logger.warning("fpcalc not found — audio fingerprinting disabled")
    return path


@dataclass(frozen=True)
class ChromaprintFingerprint:
    """Raw acoustic fingerprint emitted by ``fpcalc``.

    Attributes:
        duration_seconds: Length of audio scanned, as reported by
            fpcalc. May be slightly less than the requested length when
            the source is shorter than the request.
        hashes: Raw 32-bit fingerprint hashes, one per ~0.124s of audio.
            Suitable for hamming-distance comparison against fingerprints
            from other recordings.
    """

    duration_seconds: float
    hashes: list[int]

    @property
    def hash_count(self) -> int:
        """Return the number of fingerprint hashes."""
        return len(self.hashes)


class ChromaprintService:
    """Compute raw Chromaprint fingerprints by shelling out to ``fpcalc``.

    Attributes:
        timeout_seconds: Per-call subprocess timeout. fpcalc is fast
            (< 1s for a 10-min window on a typical desktop), so 30s is
            a comfortable safety net for slow disks or contended hosts.

    Example:
        >>> service = ChromaprintService()
        >>> fp = service.fingerprint(Path("/tmp/audio.wav"))
        >>> fp.hash_count > 0
        True
    """

    def __init__(self, *, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_seconds

    def fingerprint(self, audio_path: str | Path) -> ChromaprintFingerprint | None:
        """Compute the raw fingerprint for ``audio_path``.

        Args:
            audio_path: Path to a decoded audio file (WAV/FLAC/etc.) that
                fpcalc can read directly.

        Returns:
            A :class:`ChromaprintFingerprint`, or ``None`` if fpcalc is
            missing or the call failed.
        """
        fpcalc = _fpcalc_path()
        if fpcalc is None:
            return None

        try:
            result = subprocess.run(
                [fpcalc, "-raw", "-json", str(audio_path)],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            _logger.warning("fpcalc timed out for %s", audio_path)
            return None
        except OSError:
            _logger.exception("fpcalc crashed for %s", audio_path)
            return None

        if result.returncode != 0:
            _logger.error(
                "fpcalc failed for %s (exit=%d): %s",
                audio_path,
                result.returncode,
                result.stderr.strip() if result.stderr else "",
            )
            return None

        return _parse_fpcalc_json(result.stdout, audio_path)


def _parse_fpcalc_json(stdout: str, source: str | Path) -> ChromaprintFingerprint | None:
    """Parse the JSON document fpcalc emits under ``-raw -json``.

    Modern fpcalc (>= 1.5) emits ``"fingerprint": [int, int, ...]``;
    some packagings still emit a comma-separated string. Both shapes
    are accepted so the wrapper survives version drift across the
    distros we test on.

    Args:
        stdout: Raw stdout from fpcalc.
        source: Audio path being fingerprinted (used for log context).

    Returns:
        Parsed fingerprint or ``None`` if the payload was malformed.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        _logger.exception("fpcalc returned non-JSON output for %s", source)
        return None

    raw_fingerprint = payload.get("fingerprint")
    duration = payload.get("duration")
    if raw_fingerprint is None or duration is None:
        _logger.error("fpcalc payload missing required fields for %s: %r", source, payload)
        return None

    try:
        hashes = _coerce_hashes(raw_fingerprint)
        duration_seconds = float(duration)
    except (TypeError, ValueError):
        _logger.exception("fpcalc payload had unparseable fields for %s", source)
        return None

    if not hashes:
        _logger.error("fpcalc emitted an empty fingerprint for %s", source)
        return None

    return ChromaprintFingerprint(duration_seconds=duration_seconds, hashes=hashes)


def _coerce_hashes(raw: object) -> list[int]:
    """Normalise the ``fingerprint`` field to ``list[int]``.

    Raises:
        TypeError: Unsupported shape (neither list nor str).
        ValueError: Items can't be parsed as integers.
    """
    if isinstance(raw, list):
        return [int(h) for h in raw]
    if isinstance(raw, str):
        return [int(token) for token in raw.split(",") if token]
    raise TypeError(f"unexpected fingerprint type: {type(raw).__name__}")


__all__ = ["ChromaprintFingerprint", "ChromaprintService"]

"""Integration tests for :class:`ChromaprintService` against the real fpcalc binary.

Skipped automatically when ``fpcalc`` is not on ``PATH``. Install via
``apt install libchromaprint-tools`` / ``brew install chromaprint`` to
exercise these locally.
"""

import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from src.modules.media.infrastructure.audio.chromaprint_service import (
    ChromaprintFingerprint,
    ChromaprintService,
    _fpcalc_path,
)

pytestmark = pytest.mark.skipif(
    shutil.which("fpcalc") is None,
    reason="fpcalc not on PATH; install Chromaprint to exercise fingerprint integration tests",
)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def _clear_fpcalc_path_cache() -> None:
    _fpcalc_path.cache_clear()


def _write_sine_wav(path: Path, duration_seconds: float = 5.0, freq: int = 440) -> None:
    """Synthesize a mono 22050 Hz sine-wave WAV via the stdlib."""
    sample_rate = 22050
    amplitude = 8000
    n_frames = int(sample_rate * duration_seconds)

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(n_frames):
            sample = int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate))
            wav.writeframesraw(struct.pack("<h", sample))


@pytest.mark.integration
class TestChromaprintServiceReal:
    """End-to-end tests for ChromaprintService with the real fpcalc binary."""

    def test_produces_non_empty_fingerprint(self, tmp_path: Path) -> None:
        source = tmp_path / "sine.wav"
        _write_sine_wav(source, duration_seconds=5.0)

        result = ChromaprintService().fingerprint(source)

        assert isinstance(result, ChromaprintFingerprint)
        assert result.hash_count > 0
        assert result.duration_seconds == pytest.approx(5.0, abs=0.5)

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = ChromaprintService().fingerprint(tmp_path / "missing.wav")
        assert result is None

    def test_two_runs_on_same_input_match(self, tmp_path: Path) -> None:
        # Determinism is part of the contract: a Phase 4b detector that
        # cross-correlates fingerprints relies on identical input
        # producing identical hashes.
        source = tmp_path / "sine.wav"
        _write_sine_wav(source, duration_seconds=4.0)

        service = ChromaprintService()
        first = service.fingerprint(source)
        second = service.fingerprint(source)

        assert first is not None
        assert second is not None
        assert first.hashes == second.hashes

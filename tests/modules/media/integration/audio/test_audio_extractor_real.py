"""Integration tests for :class:`AudioExtractor` against a real ffmpeg binary.

Skipped automatically when ffmpeg is not on ``PATH`` so CI machines or
minimal Docker images that don't ship ffmpeg can still run the rest of
the suite. Locally, ensure ``ffmpeg`` is installed (``apt install
ffmpeg`` / ``brew install ffmpeg``) to exercise these.
"""

import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from src.modules.media.infrastructure.audio.audio_extractor import (
    AudioExtractor,
    _ffmpeg_path,
)

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="ffmpeg not on PATH; install it to exercise audio extraction integration tests",
)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def _clear_ffmpeg_path_cache() -> None:
    _ffmpeg_path.cache_clear()


def _write_sine_wav(path: Path, duration_seconds: float = 3.0, freq: int = 440) -> None:
    """Synthesize a small mono 22050 Hz WAV containing a sine wave.

    Uses only the stdlib so the integration suite doesn't pull in
    numpy. Loud enough that fpcalc / ffmpeg pipelines treat it as
    real content rather than silence.
    """
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
class TestAudioExtractorReal:
    """End-to-end tests for AudioExtractor with the real ffmpeg binary."""

    def test_extracts_mono_wav_from_real_audio(self, tmp_path: Path) -> None:
        source = tmp_path / "source.wav"
        _write_sine_wav(source, duration_seconds=3.0)

        extractor = AudioExtractor()
        with extractor.extract_temporary(str(source), duration_seconds=2) as wav_path:
            assert wav_path is not None
            assert wav_path.exists()
            assert wav_path.stat().st_size > 0

            with wave.open(str(wav_path), "rb") as wav:
                # Mono + 11025 Hz are the AudioExtractor defaults.
                assert wav.getnchannels() == 1
                assert wav.getframerate() == 11025
                # Duration roughly matches what we asked for; ffmpeg
                # may overshoot by a few ms because of frame boundaries.
                duration = wav.getnframes() / wav.getframerate()
                assert 1.5 <= duration <= 2.5

    def test_returns_none_when_input_does_not_exist(self, tmp_path: Path) -> None:
        result = AudioExtractor().extract(str(tmp_path / "missing.mkv"), duration_seconds=5)
        assert result is None

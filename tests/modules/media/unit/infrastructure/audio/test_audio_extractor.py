"""Tests for AudioExtractor."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.modules.media.infrastructure.audio.audio_extractor import (
    AudioExtractor,
    _ffmpeg_path,
)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def _clear_ffmpeg_path_cache() -> None:
    """Reset the cached ffmpeg lookup so each test sees its own ``shutil.which`` patch."""
    _ffmpeg_path.cache_clear()


@pytest.fixture
def fake_ffmpeg() -> MagicMock:
    """Return a ``shutil.which`` patcher resolving ffmpeg to a fake path."""
    with patch(
        "src.modules.media.infrastructure.audio.audio_extractor.shutil.which",
        return_value="/usr/bin/ffmpeg",
    ) as mocked:
        yield mocked


def _completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["ffmpeg"],
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


@pytest.mark.unit
class TestAudioExtractor:
    """Unit tests for AudioExtractor."""

    def test_returns_none_when_ffmpeg_missing(self) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.shutil.which",
            return_value=None,
        ):
            result = AudioExtractor().extract("/series/show/s01e01.mkv", duration_seconds=10)

        assert result is None

    def test_returns_none_for_non_positive_duration(self, fake_ffmpeg: MagicMock) -> None:
        with patch("src.modules.media.infrastructure.audio.audio_extractor.subprocess.run") as run:
            result = AudioExtractor().extract("/series/show/s01e01.mkv", duration_seconds=0)

        assert result is None
        run.assert_not_called()

    def test_returns_temp_path_on_success(self, fake_ffmpeg: MagicMock) -> None:
        captured: dict[str, list[str]] = {}

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            # Touch the output path so the extractor's caller can stat it.
            Path(cmd[-1]).write_bytes(b"RIFF")
            captured["cmd"] = cmd
            return _completed(returncode=0)

        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
            side_effect=run_side_effect,
        ):
            extractor = AudioExtractor()
            result = extractor.extract("/series/show/s01e01.mkv", duration_seconds=10)

        try:
            assert result is not None
            assert result.exists()
            assert result.suffix == ".wav"

            cmd = captured["cmd"]
            assert "-i" in cmd
            assert cmd[cmd.index("-i") + 1] == "/series/show/s01e01.mkv"
            assert "-t" in cmd
            assert cmd[cmd.index("-t") + 1] == "10"
            assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
            assert "-vn" in cmd
        finally:
            if result is not None:
                result.unlink(missing_ok=True)

    def test_returns_none_and_cleans_up_when_ffmpeg_fails(self, fake_ffmpeg: MagicMock) -> None:
        leftover: list[Path] = []

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            output = Path(cmd[-1])
            output.write_bytes(b"partial")
            leftover.append(output)
            return _completed(returncode=1, stderr="boom")

        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
            side_effect=run_side_effect,
        ):
            result = AudioExtractor().extract("/series/show/s01e01.mkv", duration_seconds=10)

        assert result is None
        assert leftover, "ffmpeg side-effect should have created the output stub"
        assert not leftover[0].exists(), "extractor must clean up its temp file on failure"

    def test_returns_none_and_cleans_up_on_timeout(self, fake_ffmpeg: MagicMock) -> None:
        leftover: list[Path] = []

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            output = Path(cmd[-1])
            output.write_bytes(b"")
            leftover.append(output)
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
            side_effect=run_side_effect,
        ):
            result = AudioExtractor(timeout_seconds=1).extract(
                "/series/show/s01e01.mkv", duration_seconds=10
            )

        assert result is None
        assert not leftover[0].exists()

    def test_returns_none_and_cleans_up_on_oserror(self, fake_ffmpeg: MagicMock) -> None:
        leftover: list[Path] = []

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            output = Path(cmd[-1])
            output.write_bytes(b"")
            leftover.append(output)
            raise OSError("disk full")

        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
            side_effect=run_side_effect,
        ):
            result = AudioExtractor().extract("/series/show/s01e01.mkv", duration_seconds=10)

        assert result is None
        assert not leftover[0].exists()

    def test_passes_threads_cap_when_configured(self, fake_ffmpeg: MagicMock) -> None:
        captured: dict[str, list[str]] = {}

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            Path(cmd[-1]).write_bytes(b"RIFF")
            captured["cmd"] = cmd
            return _completed(returncode=0)

        with patch(
            "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
            side_effect=run_side_effect,
        ):
            extractor = AudioExtractor(ffmpeg_threads=2)
            result = extractor.extract("/series/show/s01e01.mkv", duration_seconds=5)

        try:
            cmd = captured["cmd"]
            # ``-threads N`` is injected right after the binary by
            # with_ffmpeg_threads, before the ``-y`` global flag.
            assert cmd[1] == "-threads"
            assert cmd[2] == "2"
        finally:
            if result is not None:
                result.unlink(missing_ok=True)


@pytest.mark.unit
class TestAudioExtractorContextManager:
    """Tests for AudioExtractor.extract_temporary."""

    def test_unlinks_file_after_block(self, fake_ffmpeg: MagicMock) -> None:
        produced: list[Path] = []

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            output = Path(cmd[-1])
            output.write_bytes(b"RIFF")
            produced.append(output)
            return _completed(returncode=0)

        with (
            patch(
                "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
                side_effect=run_side_effect,
            ),
            AudioExtractor().extract_temporary(
                "/series/show/s01e01.mkv", duration_seconds=5
            ) as wav_path,
        ):
            assert wav_path is not None
            assert wav_path.exists()

        assert not produced[0].exists()

    def test_yields_none_on_failure_and_does_not_raise(self, fake_ffmpeg: MagicMock) -> None:
        with (
            patch(
                "src.modules.media.infrastructure.audio.audio_extractor.subprocess.run",
                side_effect=OSError("boom"),
            ),
            AudioExtractor().extract_temporary(
                "/series/show/s01e01.mkv", duration_seconds=5
            ) as wav_path,
        ):
            assert wav_path is None

"""Tests for ChromaprintService."""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.modules.media.infrastructure.audio.chromaprint_service import (
    ChromaprintFingerprint,
    ChromaprintService,
    _fpcalc_path,
)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def _clear_fpcalc_path_cache() -> None:
    """Reset the cached fpcalc lookup so each test sees its own ``shutil.which`` patch."""
    _fpcalc_path.cache_clear()


@pytest.fixture
def fake_fpcalc() -> MagicMock:
    """Patcher resolving fpcalc to a fake path."""
    with patch(
        "src.modules.media.infrastructure.audio.chromaprint_service.shutil.which",
        return_value="/usr/bin/fpcalc",
    ) as mocked:
        yield mocked


def _completed(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fpcalc"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


@pytest.mark.unit
class TestChromaprintService:
    """Unit tests for ChromaprintService.fingerprint."""

    def test_returns_none_when_fpcalc_missing(self) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.shutil.which",
            return_value=None,
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_parses_array_fingerprint(self, fake_fpcalc: MagicMock) -> None:
        payload = json.dumps({"duration": 12.5, "fingerprint": [1, 2, 3, 4, 5]})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert isinstance(result, ChromaprintFingerprint)
        assert result.duration_seconds == pytest.approx(12.5)
        assert result.hashes == [1, 2, 3, 4, 5]
        assert result.hash_count == 5

    def test_parses_csv_fingerprint(self, fake_fpcalc: MagicMock) -> None:
        # Older fpcalc builds emit the fingerprint as a comma-separated
        # string even under -json. The wrapper accepts both shapes so it
        # survives version drift across distros.
        payload = json.dumps({"duration": 5.04, "fingerprint": "1,2,3"})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is not None
        assert result.hashes == [1, 2, 3]

    def test_returns_none_when_fpcalc_fails(self, fake_fpcalc: MagicMock) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(returncode=1, stderr="format error"),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_on_timeout(self, fake_fpcalc: MagicMock) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["fpcalc"], timeout=1),
        ):
            result = ChromaprintService(timeout_seconds=1).fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_on_oserror(self, fake_fpcalc: MagicMock) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            side_effect=OSError("ENOMEM"),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_on_malformed_json(self, fake_fpcalc: MagicMock) -> None:
        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout="not json"),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_when_payload_missing_fields(self, fake_fpcalc: MagicMock) -> None:
        payload = json.dumps({"duration": 10.0})  # no fingerprint

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_when_fingerprint_is_empty(self, fake_fpcalc: MagicMock) -> None:
        payload = json.dumps({"duration": 10.0, "fingerprint": []})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_when_fingerprint_has_wrong_type(self, fake_fpcalc: MagicMock) -> None:
        # fpcalc shouldn't ever do this, but guard against truly broken
        # output rather than letting a TypeError leak out.
        payload = json.dumps({"duration": 10.0, "fingerprint": {"foo": 1}})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_when_fingerprint_contains_non_integer_tokens(
        self, fake_fpcalc: MagicMock
    ) -> None:
        # The legacy CSV branch and the modern array branch both run
        # through int() coercion; a non-numeric token raises ValueError
        # which the wrapper must swallow rather than propagate.
        payload = json.dumps({"duration": 10.0, "fingerprint": ["1", "foo", "3"]})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_returns_none_when_csv_fingerprint_has_garbage_tokens(
        self, fake_fpcalc: MagicMock
    ) -> None:
        payload = json.dumps({"duration": 5.04, "fingerprint": "1,foo,3"})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is None

    def test_invokes_fpcalc_with_raw_and_json_flags(self, fake_fpcalc: MagicMock) -> None:
        captured: dict[str, list[str]] = {}

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            captured["cmd"] = cmd
            return _completed(stdout=json.dumps({"duration": 1.0, "fingerprint": [42]}))

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            side_effect=run_side_effect,
        ):
            ChromaprintService().fingerprint("/tmp/audio.wav")

        cmd = captured["cmd"]
        assert "-raw" in cmd
        assert "-json" in cmd
        assert cmd[-1] == "/tmp/audio.wav"

    def test_passes_requested_length_to_fpcalc(self, fake_fpcalc: MagicMock) -> None:
        # Without -length, fpcalc fingerprints only the leading two
        # minutes and silently discards the rest of the window.
        captured: dict[str, list[str]] = {}

        def run_side_effect(cmd, **_kwargs):  # type: ignore[no-untyped-def]
            captured["cmd"] = cmd
            return _completed(stdout=json.dumps({"duration": 600.0, "fingerprint": [42]}))

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            side_effect=run_side_effect,
        ):
            ChromaprintService().fingerprint("/tmp/audio.wav", length_seconds=600)

        cmd = captured["cmd"]
        assert cmd[cmd.index("-length") + 1] == "600"

    def test_duration_is_clamped_to_the_fingerprinted_length(self, fake_fpcalc: MagicMock) -> None:
        # fpcalc reports the input's full duration even though it only
        # fingerprinted `-length` seconds of it. Reporting the unclamped
        # value would make callers derive a hash rate several times too
        # low and misplace every timestamp they compute from it.
        payload = json.dumps({"duration": 1200.0, "fingerprint": [1, 2, 3]})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav", length_seconds=300)

        assert result is not None
        assert result.duration_seconds == pytest.approx(300.0)

    def test_duration_falls_back_to_the_fpcalc_default_cap(self, fake_fpcalc: MagicMock) -> None:
        # No length requested → fpcalc applied its own 120s default.
        payload = json.dumps({"duration": 1200.0, "fingerprint": [1, 2, 3]})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav")

        assert result is not None
        assert result.duration_seconds == pytest.approx(120.0)

    def test_duration_is_left_alone_when_source_is_shorter(self, fake_fpcalc: MagicMock) -> None:
        payload = json.dumps({"duration": 42.0, "fingerprint": [1, 2, 3]})

        with patch(
            "src.modules.media.infrastructure.audio.chromaprint_service.subprocess.run",
            return_value=_completed(stdout=payload),
        ):
            result = ChromaprintService().fingerprint("/tmp/audio.wav", length_seconds=600)

        assert result is not None
        assert result.duration_seconds == pytest.approx(42.0)

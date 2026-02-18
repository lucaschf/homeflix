"""Tests for FileSelector domain service."""

import pytest

from src.domain.media.services import FileSelector
from src.domain.media.value_objects import (
    FilePath,
    HdrFormat,
    MediaFile,
    Resolution,
    VideoCodec,
)


def _make_file(
    path: str = "/movies/test.mkv",
    resolution: str = "1080p",
    bitrate: int | None = None,
    hdr: HdrFormat | None = None,
    codec: VideoCodec | None = None,
) -> MediaFile:
    """Create a MediaFile for testing."""
    return MediaFile(
        file_path=FilePath(path),
        file_size=1_000_000_000,
        resolution=Resolution(resolution),
        video_codec=codec,
        video_bitrate=bitrate,
        hdr_format=hdr,
        is_primary=True,
    )


@pytest.mark.unit
class TestFileSelectorEmptyInput:
    """Tests for empty file list handling."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_returns_none_for_empty_list(self) -> None:
        result = self.selector.select_file(files=[])
        assert result is None


@pytest.mark.unit
class TestFileSelectorMaxResolution:
    """Tests for max resolution filtering."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_filters_files_above_max_resolution(self) -> None:
        file_720 = _make_file("/m/720.mkv", "720p", bitrate=5000)
        file_1080 = _make_file("/m/1080.mkv", "1080p", bitrate=10000)
        file_4k = _make_file("/m/4k.mkv", "4K", bitrate=20000)

        result = self.selector.select_file(
            files=[file_720, file_1080, file_4k],
            max_resolution=Resolution("1080p"),
        )

        assert result is not None
        # 4K filtered out; 1080p wins by bitrate tiebreaker
        assert result.resolution == Resolution("1080p")

    def test_returns_none_when_all_exceed_max(self) -> None:
        file_4k = _make_file("/m/4k.mkv", "4K")

        result = self.selector.select_file(
            files=[file_4k],
            max_resolution=Resolution("720p"),
        )

        assert result is None

    def test_keeps_files_at_exact_max_resolution(self) -> None:
        file_1080 = _make_file("/m/1080.mkv", "1080p")

        result = self.selector.select_file(
            files=[file_1080],
            max_resolution=Resolution("1080p"),
        )

        assert result is file_1080


@pytest.mark.unit
class TestFileSelectorPreferredResolution:
    """Tests for preferred resolution matching."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_selects_exact_preferred_resolution(self) -> None:
        file_720 = _make_file("/m/720.mkv", "720p")
        file_1080 = _make_file("/m/1080.mkv", "1080p")
        file_4k = _make_file("/m/4k.mkv", "4K")

        result = self.selector.select_file(
            files=[file_720, file_1080, file_4k],
            preferred_resolution=Resolution("1080p"),
        )

        assert result is not None
        assert result.resolution == Resolution("1080p")

    def test_falls_back_to_closest_lower_resolution(self) -> None:
        file_720 = _make_file("/m/720.mkv", "720p")
        file_4k = _make_file("/m/4k.mkv", "4K")

        result = self.selector.select_file(
            files=[file_720, file_4k],
            preferred_resolution=Resolution("1080p"),
        )

        assert result is not None
        assert result.resolution == Resolution("720p")

    def test_returns_higher_when_no_lower_available(self) -> None:
        file_4k = _make_file("/m/4k.mkv", "4K")

        result = self.selector.select_file(
            files=[file_4k],
            preferred_resolution=Resolution("1080p"),
        )

        assert result is file_4k

    def test_selects_best_when_no_preference(self) -> None:
        file_720 = _make_file("/m/720.mkv", "720p", bitrate=5000)
        file_1080 = _make_file("/m/1080.mkv", "1080p", bitrate=10000)

        result = self.selector.select_file(
            files=[file_720, file_1080],
            preferred_resolution=None,
        )

        # No preferred → bitrate tiebreaker picks 1080p (10000 > 5000)
        assert result is not None
        assert result.resolution == Resolution("1080p")


@pytest.mark.unit
class TestFileSelectorHdrPreference:
    """Tests for HDR prioritization."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_prefers_hdr_when_enabled(self) -> None:
        sdr = _make_file("/m/sdr.mkv", "1080p", bitrate=10000)
        hdr = _make_file("/m/hdr.mkv", "1080p", bitrate=10000, hdr=HdrFormat.HDR10)

        result = self.selector.select_file(
            files=[sdr, hdr],
            prefer_hdr=True,
        )

        assert result is hdr

    def test_ignores_hdr_when_disabled(self) -> None:
        sdr = _make_file("/m/sdr.mkv", "1080p", bitrate=20000)
        hdr = _make_file("/m/hdr.mkv", "1080p", bitrate=10000, hdr=HdrFormat.HDR10)

        result = self.selector.select_file(
            files=[sdr, hdr],
            prefer_hdr=False,
        )

        # SDR has higher bitrate, HDR is not prioritized
        assert result is sdr

    def test_falls_back_to_sdr_when_no_hdr(self) -> None:
        sdr = _make_file("/m/sdr.mkv", "1080p")

        result = self.selector.select_file(
            files=[sdr],
            prefer_hdr=True,
        )

        assert result is sdr


@pytest.mark.unit
class TestFileSelectorBitrateTiebreaker:
    """Tests for bitrate-based tie breaking."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_selects_highest_bitrate_among_same_resolution(self) -> None:
        low = _make_file("/m/low.mkv", "1080p", bitrate=5000)
        high = _make_file("/m/high.mkv", "1080p", bitrate=15000)

        result = self.selector.select_file(
            files=[low, high],
            preferred_resolution=Resolution("1080p"),
        )

        assert result is high

    def test_treats_none_bitrate_as_zero(self) -> None:
        no_bitrate = _make_file("/m/a.mkv", "1080p", bitrate=None)
        with_bitrate = _make_file("/m/b.mkv", "1080p", bitrate=5000)

        result = self.selector.select_file(
            files=[no_bitrate, with_bitrate],
            preferred_resolution=Resolution("1080p"),
        )

        assert result is with_bitrate


@pytest.mark.unit
class TestFileSelectorCombined:
    """Tests for combined criteria."""

    def setup_method(self) -> None:
        self.selector = FileSelector()

    def test_max_and_preferred_together(self) -> None:
        file_720 = _make_file("/m/720.mkv", "720p", bitrate=5000)
        file_1080 = _make_file("/m/1080.mkv", "1080p", bitrate=10000)
        file_4k = _make_file("/m/4k.mkv", "4K", bitrate=20000)

        result = self.selector.select_file(
            files=[file_720, file_1080, file_4k],
            preferred_resolution=Resolution("4K"),
            max_resolution=Resolution("1080p"),
        )

        # 4K filtered out by max, 1080p is closest to preferred
        assert result is not None
        assert result.resolution == Resolution("1080p")

    def test_hdr_preferred_within_resolution_match(self) -> None:
        sdr = _make_file("/m/sdr.mkv", "1080p", bitrate=15000)
        hdr = _make_file("/m/hdr.mkv", "1080p", bitrate=10000, hdr=HdrFormat.DOLBY_VISION)

        result = self.selector.select_file(
            files=[sdr, hdr],
            preferred_resolution=Resolution("1080p"),
            prefer_hdr=True,
        )

        # HDR wins even with lower bitrate
        assert result is hdr

    def test_single_file_always_selected(self) -> None:
        only = _make_file("/m/only.mkv", "720p")

        result = self.selector.select_file(files=[only])

        assert result is only

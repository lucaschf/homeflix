"""Tests for HdrFormat enum."""

from src.domain.media.value_objects import HdrFormat


class TestHdrFormat:
    """Tests for HdrFormat enumeration."""

    def test_should_have_hdr10(self):
        assert HdrFormat.HDR10.value == "hdr10"

    def test_should_have_hdr10_plus(self):
        assert HdrFormat.HDR10_PLUS.value == "hdr10+"

    def test_should_have_dolby_vision(self):
        assert HdrFormat.DOLBY_VISION.value == "dolby_vision"

    def test_should_have_hlg(self):
        assert HdrFormat.HLG.value == "hlg"

    def test_should_create_from_string(self):
        fmt = HdrFormat("dolby_vision")

        assert fmt is HdrFormat.DOLBY_VISION

    def test_should_be_string_compatible(self):
        fmt = HdrFormat.HDR10

        assert str(fmt) == "hdr10"
        assert isinstance(fmt, str)

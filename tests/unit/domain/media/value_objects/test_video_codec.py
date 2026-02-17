"""Tests for VideoCodec enum."""

from src.domain.media.value_objects import VideoCodec


class TestVideoCodec:
    """Tests for VideoCodec enumeration."""

    def test_should_have_h264(self):
        assert VideoCodec.H264.value == "h264"

    def test_should_have_h265(self):
        assert VideoCodec.H265.value == "h265"

    def test_should_have_av1(self):
        assert VideoCodec.AV1.value == "av1"

    def test_should_have_vp9(self):
        assert VideoCodec.VP9.value == "vp9"

    def test_should_have_mpeg4(self):
        assert VideoCodec.MPEG4.value == "mpeg4"

    def test_should_create_from_string(self):
        codec = VideoCodec("h265")

        assert codec is VideoCodec.H265

    def test_should_be_string_compatible(self):
        codec = VideoCodec.H264

        assert str(codec) == "h264"
        assert isinstance(codec, str)

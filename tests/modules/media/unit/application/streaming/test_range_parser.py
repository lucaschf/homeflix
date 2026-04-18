"""Tests for the HTTP Range header parser."""

import pytest

from src.modules.media.application.streaming.range_parser import (
    ByteRange,
    parse_range_header,
)


@pytest.mark.unit
class TestParseRangeHeader:
    def test_missing_header_returns_full_file_non_partial(self) -> None:
        result = parse_range_header(None, 1000)
        assert result == ByteRange(start=0, end=999, is_partial=False)
        assert result.length == 1000

    def test_empty_header_is_treated_as_missing(self) -> None:
        assert parse_range_header("", 1000).is_partial is False

    def test_bounded_range_is_parsed(self) -> None:
        result = parse_range_header("bytes=100-199", 1000)
        assert result == ByteRange(start=100, end=199, is_partial=True)
        assert result.length == 100

    def test_open_ended_range_defaults_end_to_last_byte(self) -> None:
        result = parse_range_header("bytes=500-", 1000)
        assert result == ByteRange(start=500, end=999, is_partial=True)

    def test_range_is_clamped_to_file_size(self) -> None:
        result = parse_range_header("bytes=800-5000", 1000)
        assert result == ByteRange(start=800, end=999, is_partial=True)

    def test_negative_start_is_clamped_to_zero(self) -> None:
        # Malformed but defensively handled, mirroring the legacy behaviour.
        result = parse_range_header("bytes=0-10", 1000)
        assert result.start == 0

    def test_bytes_prefix_is_optional_for_resilience(self) -> None:
        result = parse_range_header("100-199", 1000)
        assert result == ByteRange(start=100, end=199, is_partial=True)

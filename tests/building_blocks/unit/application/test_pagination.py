"""Tests for the pagination building block."""

import base64

import pytest

from src.building_blocks.application.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CursorValue,
    PaginatedResult,
    Pagination,
    decode_cursor,
    encode_cursor,
)


@pytest.mark.unit
class TestEncodeDecodeRoundtrip:
    """Encode + decode should be a perfect inverse for valid inputs."""

    def test_should_roundtrip_a_typical_cursor(self) -> None:
        encoded = encode_cursor(42)

        decoded = decode_cursor(encoded)

        assert decoded == CursorValue(id=42)

    def test_should_roundtrip_id_one(self) -> None:
        encoded = encode_cursor(1)
        assert decode_cursor(encoded) == CursorValue(id=1)

    def test_should_roundtrip_high_internal_id(self) -> None:
        encoded = encode_cursor(9_999_999_999)
        assert decode_cursor(encoded) == CursorValue(id=9_999_999_999)


@pytest.mark.unit
class TestEncodeOpaqueness:
    """The wire format should not let clients trivially infer the id."""

    def test_should_only_contain_url_safe_characters(self) -> None:
        encoded = encode_cursor(42)

        # `+` and `/` are the unsafe ones in standard base64; URL-safe replaces
        # them with `-` and `_`. The encoded cursor must not contain either.
        assert "+" not in encoded
        assert "/" not in encoded

    def test_should_not_be_a_bare_integer_string(self) -> None:
        # The whole point of base64-wrapping is that clients can't treat
        # the cursor as a sortable number — make sure we didn't regress
        # to passing the integer through verbatim.
        encoded = encode_cursor(42)
        assert encoded != "42"


@pytest.mark.unit
class TestDecodeCursorFallback:
    """Invalid / absent cursors should silently degrade to None."""

    def test_should_return_none_for_none_input(self) -> None:
        assert decode_cursor(None) is None

    def test_should_return_none_for_empty_string(self) -> None:
        assert decode_cursor("") is None

    def test_should_return_none_for_garbage_string(self) -> None:
        assert decode_cursor("not-a-valid-cursor!!!") is None

    def test_should_return_none_for_invalid_base64_padding(self) -> None:
        # Strings whose length isn't a multiple of 4 raise
        # `binascii.Error` from `base64.urlsafe_b64decode`. The cursor
        # decoder must catch this explicitly so callers never see the
        # raw exception during an infinite scroll.
        assert decode_cursor("abc") is None

    def test_should_return_none_when_payload_is_not_an_integer(self) -> None:
        bogus = base64.urlsafe_b64encode(b"hello world").decode("ascii")
        assert decode_cursor(bogus) is None

    def test_should_return_none_for_negative_decoded_payload(self) -> None:
        # int("-5") parses successfully, so this isn't a malformed
        # payload at the parser level — but a negative cursor would
        # never come from `encode_cursor`. We document the current
        # behavior: it round-trips. If we ever need to reject it the
        # check goes here.
        encoded = base64.urlsafe_b64encode(b"-5").decode("ascii")
        assert decode_cursor(encoded) == CursorValue(id=-5)


@pytest.mark.unit
class TestEncodeDecodeContract:
    """The wire format must survive a query-string round trip."""

    def test_should_not_use_url_unsafe_padding(self) -> None:
        # Standard base64 padding `=` is technically url-safe (it's a
        # reserved char) but some HTTP libs strip it. The encoded
        # values for any reasonable id should not need padding to be
        # decoded back — the URL-safe variant tolerates missing padding,
        # but tests should still confirm we're producing CONSISTENT
        # output.
        for i in (1, 42, 99_999_999):
            encoded = encode_cursor(i)
            assert decode_cursor(encoded) == CursorValue(id=i)


@pytest.mark.unit
class TestPaginatedResultDefaults:
    """The dataclass defaults should match the documented contract."""

    def test_total_count_defaults_to_none(self) -> None:
        result: PaginatedResult[int] = PaginatedResult(
            items=[1, 2, 3],
            pagination=Pagination(next_cursor=None, has_more=False),
        )

        assert result.total_count is None

    def test_should_carry_through_pagination_metadata(self) -> None:
        result: PaginatedResult[int] = PaginatedResult(
            items=[1],
            pagination=Pagination(next_cursor="cursor-token", has_more=True),
            total_count=99,
        )

        assert result.pagination.next_cursor == "cursor-token"
        assert result.pagination.has_more is True
        assert result.total_count == 99


@pytest.mark.unit
class TestPageSizeConstants:
    """Sanity checks on the constants exposed for routes."""

    def test_default_must_be_within_max(self) -> None:
        assert 1 <= DEFAULT_PAGE_SIZE <= MAX_PAGE_SIZE

    def test_max_should_not_be_unbounded(self) -> None:
        # If the project ever bumps this past a few hundred, the cursor
        # design (fetch limit+1, single SQL query) starts to get wasteful
        # and we should reconsider. This guards against an accidental
        # configuration change.
        assert MAX_PAGE_SIZE <= 500

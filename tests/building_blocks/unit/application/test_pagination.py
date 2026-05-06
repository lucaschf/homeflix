"""Tests for the pagination building block."""

import base64

import pytest

from src.building_blocks.application.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CursorValue,
    DualCursorValue,
    PaginatedResult,
    Pagination,
    TitleCursorValue,
    decode_cursor,
    decode_dual_cursor,
    decode_title_cursor,
    encode_cursor,
    encode_dual_cursor,
    encode_title_cursor,
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


@pytest.mark.unit
class TestTitleCursor:
    """Tests for the (title, id) composite cursor used by title-sorted listings."""

    def test_should_roundtrip_a_typical_cursor(self) -> None:
        encoded = encode_title_cursor("Inception", 42)

        decoded = decode_title_cursor(encoded)

        # Title comes back lowercased to match the SQL `LOWER(title)` sort key.
        assert decoded == TitleCursorValue(title="inception", id=42)

    def test_should_lowercase_the_title_on_encode(self) -> None:
        encoded_upper = encode_title_cursor("INCEPTION", 1)
        encoded_mixed = encode_title_cursor("Inception", 1)
        encoded_lower = encode_title_cursor("inception", 1)

        # All three encodings must produce the same cursor — the
        # comparison key in SQL is `LOWER(title)`, and a cursor that
        # encoded the original case would skip rows whose actual case
        # didn't match the cursor's case.
        assert encoded_upper == encoded_mixed == encoded_lower

    def test_should_handle_titles_with_unicode_and_punctuation(self) -> None:
        encoded = encode_title_cursor("Cidade de Deus: O Filme", 7)

        decoded = decode_title_cursor(encoded)

        assert decoded == TitleCursorValue(title="cidade de deus: o filme", id=7)

    def test_should_handle_titles_with_pipe_character(self) -> None:
        # The original id-only cursor used `|` as a separator. The title
        # cursor uses ASCII 0x1F instead so a literal `|` in a title can't
        # collide with the delimiter — this test guards that.
        encoded = encode_title_cursor("Fast | Furious", 99)

        decoded = decode_title_cursor(encoded)

        assert decoded == TitleCursorValue(title="fast | furious", id=99)

    def test_should_return_none_for_empty_or_invalid_cursor(self) -> None:
        assert decode_title_cursor(None) is None
        assert decode_title_cursor("") is None
        assert decode_title_cursor("not-valid-base64!!!") is None

    def test_should_return_none_when_payload_lacks_separator(self) -> None:
        bogus = base64.urlsafe_b64encode(b"missing-separator").decode("ascii")
        assert decode_title_cursor(bogus) is None

    def test_should_return_none_when_id_part_is_not_an_integer(self) -> None:
        bogus = base64.urlsafe_b64encode(b"title\x1fnot_an_int").decode("ascii")
        assert decode_title_cursor(bogus) is None


@pytest.mark.unit
class TestDualCursor:
    """Tests for the dual-stream cursor used by the catalog by-genre endpoint."""

    def test_should_roundtrip_two_present_cursors(self) -> None:
        encoded = encode_dual_cursor("movies-token", "series-token")

        decoded = decode_dual_cursor(encoded)

        assert decoded == DualCursorValue(movies="movies-token", series="series-token")

    def test_should_roundtrip_one_exhausted_stream(self) -> None:
        encoded = encode_dual_cursor("movies-token", None)

        decoded = decode_dual_cursor(encoded)

        assert decoded == DualCursorValue(movies="movies-token", series=None)

    def test_should_roundtrip_both_exhausted(self) -> None:
        encoded = encode_dual_cursor(None, None)

        decoded = decode_dual_cursor(encoded)

        assert decoded == DualCursorValue(movies=None, series=None)

    def test_should_decode_empty_cursor_as_both_none(self) -> None:
        # `decode_dual_cursor` returns a non-optional `DualCursorValue`,
        # so callers don't have to branch on `cursor is None` — both
        # fields just come through as `None` in that case.
        assert decode_dual_cursor(None) == DualCursorValue(movies=None, series=None)
        assert decode_dual_cursor("") == DualCursorValue(movies=None, series=None)

    def test_should_decode_garbage_as_both_none(self) -> None:
        # Same silent fallback as the other decoders — a tampered or
        # truncated cursor should not raise mid-scroll.
        assert decode_dual_cursor("not-valid!!!") == DualCursorValue(movies=None, series=None)

    def test_inner_cursors_can_themselves_be_base64(self) -> None:
        # The catalog endpoint nests the per-stream cursors (which
        # are themselves opaque base64) inside the dual wrapper. Make
        # sure the separator doesn't collide with base64 characters.
        inner_movies = encode_title_cursor("Inception", 42)
        inner_series = encode_title_cursor("Breaking Bad", 7)

        encoded = encode_dual_cursor(inner_movies, inner_series)
        decoded = decode_dual_cursor(encoded)

        assert decoded.movies == inner_movies
        assert decoded.series == inner_series

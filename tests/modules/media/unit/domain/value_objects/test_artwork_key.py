"""Unit tests for the :class:`ArtworkKey` value object (ADR-029)."""

from __future__ import annotations

import hashlib

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects.artwork_key import ArtworkKey


class TestForContent:
    def test_should_be_content_addressed_sha256_plus_extension(self) -> None:
        content = b"poster-bytes"
        expected_digest = hashlib.sha256(content).hexdigest()

        key = ArtworkKey.for_content(
            content, content_type="image/jpeg", source_url="https://x/y.jpg"
        )

        assert str(key) == f"{expected_digest}.jpg"

    def test_should_derive_extension_from_content_type(self) -> None:
        key = ArtworkKey.for_content(
            b"x", content_type="image/png", source_url="https://x/y"
        )

        assert str(key).endswith(".png")

    def test_should_ignore_charset_suffix_on_content_type(self) -> None:
        key = ArtworkKey.for_content(
            b"x", content_type="image/webp; charset=binary", source_url="https://x/y"
        )

        assert str(key).endswith(".webp")

    def test_should_fall_back_to_url_suffix_when_content_type_unknown(self) -> None:
        key = ArtworkKey.for_content(
            b"x", content_type=None, source_url="https://image.tmdb.org/t/p/original/z.png"
        )

        assert str(key).endswith(".png")

    def test_should_fall_back_to_jpg_when_no_extension_anywhere(self) -> None:
        key = ArtworkKey.for_content(
            b"x", content_type="application/octet-stream", source_url="https://x/no-ext"
        )

        assert str(key).endswith(".jpg")

    def test_should_be_deterministic_for_identical_bytes(self) -> None:
        a = ArtworkKey.for_content(b"same", content_type="image/jpeg", source_url="https://a/x.jpg")
        b = ArtworkKey.for_content(b"same", content_type="image/jpeg", source_url="https://b/z.jpg")

        assert str(a) == str(b)

    def test_should_change_when_bytes_change(self) -> None:
        a = ArtworkKey.for_content(b"one", content_type="image/jpeg", source_url="https://a/x.jpg")
        b = ArtworkKey.for_content(b"two", content_type="image/jpeg", source_url="https://a/x.jpg")

        assert str(a) != str(b)

    def test_should_produce_a_key_matching_the_route_charset(self) -> None:
        from src.modules.media.domain.value_objects.artwork_key import ARTWORK_KEY_PATTERN

        key = ArtworkKey.for_content(
            b"x", content_type="image/jpeg", source_url="https://x/y.jpg"
        )

        assert ARTWORK_KEY_PATTERN.match(str(key))


class TestValidation:
    @pytest.mark.parametrize("bad", ["", "..", ".", "a/b", "a b", "a?b", "../x"])
    def test_should_reject_unsafe_or_all_dots_keys(self, bad: str) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkKey(bad)

    def test_should_accept_a_hash_and_extension_token(self) -> None:
        assert str(ArtworkKey("ab12CD._-def.jpg")) == "ab12CD._-def.jpg"

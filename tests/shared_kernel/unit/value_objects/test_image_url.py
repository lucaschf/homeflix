"""Tests for ImageUrl value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects import ImageUrl


class TestImageUrlCreation:
    """Tests for ImageUrl instantiation."""

    def test_should_create_with_https_url(self):
        url = ImageUrl("https://image.tmdb.org/t/p/original/abc.jpg")
        assert url.value == "https://image.tmdb.org/t/p/original/abc.jpg"

    def test_should_create_with_http_url(self):
        url = ImageUrl("http://example.com/poster.jpg")
        assert url.value == "http://example.com/poster.jpg"

    def test_should_create_with_unix_path(self):
        url = ImageUrl("/thumbnails/poster.jpg")
        assert url.value == "/thumbnails/poster.jpg"

    def test_should_create_with_windows_path(self):
        url = ImageUrl("C:\\images\\poster.jpg")
        assert url.value == "C:\\images\\poster.jpg"

    def test_should_raise_for_relative_path(self):
        with pytest.raises(DomainValidationException):
            ImageUrl("images/poster.jpg")

    def test_should_raise_for_empty(self):
        with pytest.raises(DomainValidationException):
            ImageUrl("")

    def test_should_raise_for_plain_text(self):
        with pytest.raises(DomainValidationException):
            ImageUrl("not a url or path")

    def test_should_raise_for_non_string_input(self):
        with pytest.raises(DomainValidationException, match="must be a string"):
            ImageUrl(123)  # type: ignore[arg-type]


class TestImageUrlBehavior:
    """Tests for ImageUrl behavior."""

    def test_is_remote_true_for_url(self):
        url = ImageUrl("https://image.tmdb.org/t/p/original/abc.jpg")
        assert url.is_remote is True

    def test_is_remote_false_for_path(self):
        url = ImageUrl("/thumbnails/poster.jpg")
        assert url.is_remote is False

    def test_str_returns_value(self):
        assert str(ImageUrl("https://example.com/img.jpg")) == "https://example.com/img.jpg"

    def test_equality(self):
        assert ImageUrl("https://a.com/img.jpg") == ImageUrl("https://a.com/img.jpg")

    def test_inequality(self):
        assert ImageUrl("https://a.com/1.jpg") != ImageUrl("https://a.com/2.jpg")

    def test_hashable(self):
        urls = {ImageUrl("https://a.com/img.jpg"), ImageUrl("https://a.com/img.jpg")}
        assert len(urls) == 1

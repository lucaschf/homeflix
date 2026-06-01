"""Tests for the ``LanguageTag`` value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.shared_kernel.value_objects.language_tag import LanguageTag


@pytest.mark.unit
class TestLanguageTagValidation:
    """Shape validation rejects anything that isn't a BCP-47-ish tag."""

    @pytest.mark.parametrize("raw", ["pt", "en", "pt-BR", "en-US", "zh-Hans", "zh-Hans-CN"])
    def test_accepts_valid_tags(self, raw: str) -> None:
        assert LanguageTag(raw).value == raw

    @pytest.mark.parametrize("raw", ["", "portugues", "p", "pt_BR", "123", "-BR", "pt-"])
    def test_rejects_garbage(self, raw: str) -> None:
        with pytest.raises(DomainValidationException):
            LanguageTag(raw)

    def test_rejects_non_string(self) -> None:
        with pytest.raises(DomainValidationException):
            LanguageTag(42)  # type: ignore[arg-type]


@pytest.mark.unit
class TestLanguageTagNormalization:
    """BCP-47 casing is canonicalized so equal tags compare equal."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("PT", "pt"),
            ("pt-br", "pt-BR"),
            ("EN-us", "en-US"),
            ("zh-hans", "zh-Hans"),
        ],
    )
    def test_normalizes_casing(self, raw: str, expected: str) -> None:
        assert LanguageTag(raw).value == expected

    def test_strips_whitespace(self) -> None:
        assert LanguageTag("  pt-BR  ").value == "pt-BR"

    def test_equal_after_normalization(self) -> None:
        assert LanguageTag("pt-br") == LanguageTag("PT-BR")


@pytest.mark.unit
class TestLanguageTagPrimarySubtag:
    """``primary_subtag`` bridges to the strict ISO 639-1 LanguageCode."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("pt-BR", "pt"), ("en-US", "en"), ("pt", "pt"), ("zh-Hans-CN", "zh")],
    )
    def test_returns_language_part(self, raw: str, expected: str) -> None:
        assert LanguageTag(raw).primary_subtag == expected

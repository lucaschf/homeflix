"""Tests for ExternalId base class."""

from typing import ClassVar

import pytest
from pydantic import model_validator

from src.domain.shared.exceptions.domain import DomainValidationException
from src.domain.shared.models.external_id import (
    BASE62_ALPHABET,
    RANDOM_PART_LENGTH,
    ExternalId,
)


class SampleExternalId(ExternalId):
    """Test external ID with 'tst' prefix."""

    EXPECTED_PREFIX: ClassVar[str] = "tst"

    @model_validator(mode="after")
    def validate_prefix(self) -> "SampleExternalId":
        if self.prefix != self.EXPECTED_PREFIX:
            raise ValueError(f"SampleExternalId must have '{self.EXPECTED_PREFIX}' prefix")
        return self


class SampleExternalIdConstants:
    """Tests for ExternalId module constants."""

    def test_base62_alphabet_contains_all_alphanumeric_chars(self):
        assert len(BASE62_ALPHABET) == 62
        assert all(c.isalnum() for c in BASE62_ALPHABET)

    def test_random_part_length_is_12(self):
        assert RANDOM_PART_LENGTH == 12


class SampleExternalIdCreation:
    """Tests for ExternalId instantiation."""

    def test_should_create_with_valid_format(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert ext_id.value == "tst_abc123abc123"

    def test_should_strip_whitespace(self):
        ext_id = SampleExternalId("  tst_abc123abc123  ")

        assert ext_id.value == "tst_abc123abc123"

    def test_should_raise_error_when_missing_separator(self):
        with pytest.raises(DomainValidationException, match="underscore"):
            SampleExternalId("tstabc123abc123")

    def test_should_raise_error_when_random_part_too_short(self):
        with pytest.raises(DomainValidationException, match="12"):
            SampleExternalId("tst_abc123")

    def test_should_raise_error_when_random_part_too_long(self):
        with pytest.raises(DomainValidationException, match="12"):
            SampleExternalId("tst_abc123abc123abc")

    def test_should_raise_error_when_random_part_has_invalid_chars(self):
        with pytest.raises(DomainValidationException, match="Base62"):
            SampleExternalId("tst_abc123abc!@#")

    def test_should_raise_error_for_wrong_prefix(self):
        with pytest.raises(DomainValidationException, match="prefix"):
            SampleExternalId("xxx_abc123abc123")

    def test_should_raise_error_for_non_string_input(self):
        with pytest.raises(DomainValidationException, match="string"):
            SampleExternalId(123)


class SampleExternalIdGeneration:
    """Tests for ExternalId.generate()."""

    def test_should_generate_with_correct_prefix(self):
        ext_id = SampleExternalId.generate()

        assert ext_id.prefix == "tst"

    def test_should_generate_with_correct_format(self):
        ext_id = SampleExternalId.generate()

        assert "_" in ext_id.value
        parts = ext_id.value.split("_")
        assert len(parts) == 2

    def test_should_generate_with_correct_random_part_length(self):
        ext_id = SampleExternalId.generate()

        assert len(ext_id.random_part) == RANDOM_PART_LENGTH

    def test_should_generate_with_base62_characters_only(self):
        ext_id = SampleExternalId.generate()

        assert all(c in BASE62_ALPHABET for c in ext_id.random_part)

    def test_should_generate_unique_ids(self):
        ids = [SampleExternalId.generate() for _ in range(100)]
        unique_ids = {id_.value for id_ in ids}

        assert len(unique_ids) == 100


class SampleExternalIdProperties:
    """Tests for ExternalId properties."""

    def test_value_property_returns_full_id(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert ext_id.value == "tst_abc123abc123"

    def test_prefix_property_extracts_prefix(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert ext_id.prefix == "tst"

    def test_random_part_property_extracts_random_part(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert ext_id.random_part == "abc123abc123"


class SampleExternalIdStringRepresentation:
    """Tests for ExternalId string conversion."""

    def test_should_convert_to_string(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert str(ext_id) == "tst_abc123abc123"

    def test_should_have_descriptive_repr(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert repr(ext_id) == "SampleExternalId('tst_abc123abc123')"


class SampleExternalIdEquality:
    """Tests for ExternalId equality and hashing."""

    def test_should_be_equal_when_same_value(self):
        id1 = SampleExternalId("tst_abc123abc123")
        id2 = SampleExternalId("tst_abc123abc123")

        assert id1 == id2

    def test_should_not_be_equal_when_different_value(self):
        id1 = SampleExternalId("tst_abc123abc123")
        id2 = SampleExternalId("tst_xyz789xyz789")

        assert id1 != id2

    def test_should_be_hashable(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        id_set = {ext_id}

        assert ext_id in id_set

    def test_should_have_same_hash_when_equal(self):
        id1 = SampleExternalId("tst_abc123abc123")
        id2 = SampleExternalId("tst_abc123abc123")

        assert hash(id1) == hash(id2)

    def test_should_return_not_implemented_for_non_external_id(self):
        ext_id = SampleExternalId("tst_abc123abc123")

        assert ext_id.__eq__("tst_abc123abc123") == NotImplemented


class SampleExternalIdWithMultiplePrefixes:
    """Tests for ExternalId with different prefix classes."""

    def test_same_random_part_with_different_prefix_should_not_be_equal(self):
        # Create another ExternalId subclass with different prefix
        class OtherExternalId(ExternalId):
            EXPECTED_PREFIX: ClassVar[str] = "oth"

            @model_validator(mode="after")
            def validate_prefix(self) -> "OtherExternalId":
                if self.prefix != self.EXPECTED_PREFIX:
                    raise ValueError(f"OtherExternalId must have '{self.EXPECTED_PREFIX}' prefix")
                return self

        tst_id = SampleExternalId("tst_abc123abc123")
        oth_id = OtherExternalId("oth_abc123abc123")

        # They have the same random part but different class and prefix
        assert tst_id.random_part == oth_id.random_part
        # The ExternalId __eq__ compares values, not types
        # So these should not be equal since full values differ
        assert tst_id != oth_id

"""Tests for PreferencesId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.value_objects import PreferencesId


@pytest.mark.unit
class TestPreferencesId:
    def test_should_accept_canonical_default_id(self) -> None:
        assert PreferencesId("prf_default").value == "prf_default"

    def test_for_user_key_builds_prefixed_id(self) -> None:
        assert PreferencesId.for_user_key("alice").value == "prf_alice"

    def test_should_reject_missing_prefix(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("default")

    def test_should_reject_empty_user_key(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("prf_")

    def test_should_reject_unsupported_characters(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("prf_with space")

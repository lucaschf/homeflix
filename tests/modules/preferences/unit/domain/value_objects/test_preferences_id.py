"""Tests for PreferencesId value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.preferences.domain.value_objects import PreferencesId
from src.shared_kernel.value_objects.profile_id import ProfileId


@pytest.mark.unit
class TestPreferencesId:
    def test_should_accept_legacy_default_id(self) -> None:
        # The regex still allows the historical ``prf_default`` shape so
        # rows persisted before the per-profile migration stay readable.
        assert PreferencesId("prf_default").value == "prf_default"

    def test_should_accept_profile_mirroring_id(self) -> None:
        assert PreferencesId("prf_test12345678").value == "prf_test12345678"

    def test_for_profile_mirrors_profile_id_value(self) -> None:
        profile_id = ProfileId("prf_test12345678")
        assert PreferencesId.for_profile(profile_id).value == profile_id.value

    def test_should_reject_missing_prefix(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("default")

    def test_should_reject_empty_slug(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("prf_")

    def test_should_reject_unsupported_characters(self) -> None:
        with pytest.raises(DomainValidationException):
            PreferencesId("prf_with space")

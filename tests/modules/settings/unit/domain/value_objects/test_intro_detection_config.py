"""Unit tests for :class:`IntroDetectionConfig`."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import IntroDetectionConfig


class TestIntroDetectionConfig:
    def test_default_values_satisfy_invariants(self) -> None:
        config = IntroDetectionConfig()

        assert config.enabled is False
        assert config.min_intro_seconds < config.max_intro_seconds

    def test_min_greater_than_max_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            IntroDetectionConfig(min_intro_seconds=120, max_intro_seconds=60)

    def test_min_equal_to_max_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            IntroDetectionConfig(min_intro_seconds=90, max_intro_seconds=90)

    def test_with_updates_revalidates_bounds(self) -> None:
        config = IntroDetectionConfig()

        with pytest.raises(DomainValidationException):
            config.with_updates(min_intro_seconds=config.max_intro_seconds + 10)

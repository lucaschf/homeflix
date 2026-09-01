"""Unit tests for :class:`IntroDetectionConfig`."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import (
    IntroDetectionAlgorithm,
    IntroDetectionConfig,
)


class TestIntroDetectionConfig:
    def test_default_values_satisfy_invariants(self) -> None:
        config = IntroDetectionConfig()

        assert config.enabled is False
        assert config.min_intro_seconds < config.max_intro_seconds

    def test_defaults_pair_the_two_detectors_as_primary_and_fallback(self) -> None:
        # The detectors fail on disjoint material, so out of the box a
        # season the video pass cannot crack is retried against audio.
        config = IntroDetectionConfig()

        assert config.algorithm == IntroDetectionAlgorithm.FRAME_HASH
        assert config.fallback_algorithm == IntroDetectionAlgorithm.CHROMAPRINT

    def test_fallback_can_be_disabled(self) -> None:
        assert IntroDetectionConfig(fallback_algorithm=None).fallback_algorithm is None

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

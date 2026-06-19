"""Tests for the CreditsDetectionConfig value object."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import CreditsDetectionConfig


@pytest.mark.unit
class TestCreditsDetectionConfig:
    def test_defaults_are_off_and_sane(self) -> None:
        cfg = CreditsDetectionConfig()
        assert cfg.enabled is False
        assert cfg.analysis_window_seconds == 600
        assert cfg.frame_sample_fps == 1.0
        assert cfg.min_credits_seconds == 15.0
        assert 0.0 <= cfg.min_confidence <= 1.0
        assert cfg.edge_rel_factor > 1.0
        assert 0.0 < cfg.motion_rel_factor < 1.0

    def test_with_updates_is_immutable_copy(self) -> None:
        cfg = CreditsDetectionConfig()
        picky = cfg.with_updates(min_confidence=0.8, enabled=True)
        assert picky.min_confidence == 0.8
        assert picky.enabled is True
        assert cfg.min_confidence != 0.8  # original untouched

    @pytest.mark.parametrize(
        "field,value",
        [
            ("min_confidence", 1.5),
            ("min_confidence", -0.1),
            ("analysis_window_seconds", 10),  # below the 60s floor
            ("frame_sample_fps", 0.0),
            ("motion_rel_factor", 1.0),  # must be < 1
            ("edge_rel_factor", 1.0),  # must be > 1
            ("min_credits_seconds", 0.0),  # must be >= 1
        ],
    )
    def test_rejects_out_of_range(self, field: str, value: float) -> None:
        with pytest.raises(DomainValidationException):
            CreditsDetectionConfig(**{field: value})

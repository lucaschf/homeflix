"""Unit tests for :class:`ScanDedupConfig`."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import ScanDedupConfig


class TestScanDedupConfig:
    def test_default_values_match_adr_thresholds(self) -> None:
        config = ScanDedupConfig()

        assert config.runtime_delta_abs_minutes == 5.0
        assert config.runtime_delta_relative == 0.10
        assert config.title_year_fallback_enabled is True
        assert config.sweep_enabled is False
        assert config.sweep_interval_minutes == 1440

    def test_fallback_can_be_disabled(self) -> None:
        config = ScanDedupConfig(title_year_fallback_enabled=False)

        assert config.title_year_fallback_enabled is False

    def test_sweep_can_be_enabled_and_interval_tuned(self) -> None:
        config = ScanDedupConfig(sweep_enabled=True, sweep_interval_minutes=60)

        assert config.sweep_enabled is True
        assert config.sweep_interval_minutes == 60

    def test_sweep_interval_below_floor_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            ScanDedupConfig(sweep_interval_minutes=5)

    def test_negative_abs_minutes_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            ScanDedupConfig(runtime_delta_abs_minutes=-1.0)

    def test_relative_above_one_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            ScanDedupConfig(runtime_delta_relative=1.5)

    def test_relative_below_zero_raises(self) -> None:
        with pytest.raises(DomainValidationException):
            ScanDedupConfig(runtime_delta_relative=-0.01)

    def test_with_updates_revalidates_bounds(self) -> None:
        config = ScanDedupConfig()

        with pytest.raises(DomainValidationException):
            config.with_updates(runtime_delta_relative=2.0)

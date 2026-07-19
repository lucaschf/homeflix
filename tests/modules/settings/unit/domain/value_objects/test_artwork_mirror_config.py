"""Tests for the ArtworkMirrorConfig VO (ADR-029 bucket)."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.settings.domain.value_objects import ArtworkMirrorConfig


@pytest.mark.unit
class TestArtworkMirrorConfig:
    def test_defaults(self) -> None:
        cfg = ArtworkMirrorConfig()

        assert cfg.enabled is True
        assert cfg.batch_size == 20
        assert cfg.interval_minutes == 30
        assert cfg.max_bytes == 10 * 1024 * 1024

    def test_with_updates_returns_a_modified_copy(self) -> None:
        cfg = ArtworkMirrorConfig()

        updated = cfg.with_updates(batch_size=50, interval_minutes=15)

        assert updated.batch_size == 50
        assert updated.interval_minutes == 15
        assert cfg.batch_size == 20  # original untouched

    @pytest.mark.parametrize("bad", [0, -1])
    def test_batch_size_must_be_positive(self, bad: int) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkMirrorConfig(batch_size=bad)

    def test_interval_must_be_positive(self) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkMirrorConfig(interval_minutes=0)

    def test_max_bytes_must_be_positive(self) -> None:
        with pytest.raises(DomainValidationException):
            ArtworkMirrorConfig(max_bytes=0)

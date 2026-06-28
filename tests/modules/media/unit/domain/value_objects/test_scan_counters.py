"""Tests for the ScanCounters / EnrichCounters value objects."""

import pytest

from src.building_blocks.domain.errors import DomainValidationException
from src.modules.media.domain.value_objects.scan_counters import (
    EnrichCounters,
    ScanCounters,
)


@pytest.mark.unit
class TestScanCounters:
    def test_to_summary_has_the_canonical_scan_keys(self) -> None:
        counters = ScanCounters(
            movies_created=2,
            movies_updated=1,
            episodes_created=4,
            episodes_updated=3,
        )
        assert counters.to_summary() == {
            "movies_created": 2,
            "movies_updated": 1,
            "episodes_created": 4,
            "episodes_updated": 3,
        }

    def test_defaults_are_zero(self) -> None:
        assert ScanCounters().to_summary() == {
            "movies_created": 0,
            "movies_updated": 0,
            "episodes_created": 0,
            "episodes_updated": 0,
        }

    def test_negative_count_is_rejected(self) -> None:
        with pytest.raises(DomainValidationException):
            ScanCounters(movies_created=-1)


@pytest.mark.unit
class TestEnrichCounters:
    def test_to_summary_has_the_canonical_enrich_keys(self) -> None:
        counters = EnrichCounters(movies_enriched=4, series_enriched=2, skipped=1)
        assert counters.to_summary() == {
            "movies_enriched": 4,
            "series_enriched": 2,
            "skipped": 1,
        }

    def test_defaults_are_zero(self) -> None:
        assert EnrichCounters().to_summary() == {
            "movies_enriched": 0,
            "series_enriched": 0,
            "skipped": 0,
        }

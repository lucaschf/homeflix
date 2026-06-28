"""Tests for the ScanRun aggregate's terminal transitions."""

import pytest

from src.modules.media.domain.entities.scan_run import (
    ScanRun,
    ScanRunKind,
    ScanRunStatus,
    ScanRunTrigger,
)
from src.modules.media.domain.value_objects.scan_counters import (
    EnrichCounters,
    ScanCounters,
)


def _running(kind: ScanRunKind) -> ScanRun:
    return ScanRun.start(
        kind=kind,
        trigger=ScanRunTrigger.MANUAL,
        library_id="lib_test12345678" if kind is ScanRunKind.SCAN else None,
    )


@pytest.mark.unit
class TestScanRunSucceed:
    def test_scan_counters_serialize_into_summary(self) -> None:
        run = _running(ScanRunKind.SCAN).succeed(
            ScanCounters(movies_created=2, episodes_updated=3), []
        )
        assert run.status is ScanRunStatus.SUCCEEDED
        assert run.finished_at is not None
        assert run.summary == {
            "movies_created": 2,
            "movies_updated": 0,
            "episodes_created": 0,
            "episodes_updated": 3,
        }

    def test_enrich_counters_serialize_into_summary(self) -> None:
        run = _running(ScanRunKind.ENRICH).succeed(
            EnrichCounters(movies_enriched=4, series_enriched=2, skipped=1), []
        )
        assert run.summary == {
            "movies_enriched": 4,
            "series_enriched": 2,
            "skipped": 1,
        }

    def test_rejects_counters_that_do_not_match_kind(self) -> None:
        with pytest.raises(ValueError, match="cannot summarize"):
            _running(ScanRunKind.SCAN).succeed(EnrichCounters(), [])
        with pytest.raises(ValueError, match="cannot summarize"):
            _running(ScanRunKind.ENRICH).succeed(ScanCounters(), [])


@pytest.mark.unit
class TestScanRunFail:
    def test_fail_without_counters_keeps_existing_summary(self) -> None:
        run = _running(ScanRunKind.SCAN).fail("boom")
        assert run.status is ScanRunStatus.FAILED
        assert run.summary == {}
        assert run.errors == ["boom"]

    def test_fail_with_partial_counters_records_them(self) -> None:
        run = _running(ScanRunKind.SCAN).fail("boom", ScanCounters(movies_created=1))
        assert run.summary["movies_created"] == 1

    def test_fail_rejects_mismatched_counters(self) -> None:
        with pytest.raises(ValueError, match="cannot summarize"):
            _running(ScanRunKind.SCAN).fail("boom", EnrichCounters())

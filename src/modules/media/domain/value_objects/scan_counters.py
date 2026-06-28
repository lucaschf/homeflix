"""Typed counters for a scan / bulk-enrich run.

These replace the magic-key ``dict[str, Any]`` that the runner used to
build by hand. The field names ARE the persisted summary keys, so the
JSON shape stored on ``scan_runs.summary`` is unchanged — ``to_summary``
is the single source of that contract.
"""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class ScanCounters(CompoundValueObject):
    """Per-kind counters produced by a catalog scan.

    Attributes:
        movies_created: Movies inserted during the scan.
        movies_updated: Existing movies whose files were refreshed.
        episodes_created: Episodes inserted during the scan.
        episodes_updated: Existing episodes whose files were refreshed.
    """

    movies_created: int = Field(default=0, ge=0)
    movies_updated: int = Field(default=0, ge=0)
    episodes_created: int = Field(default=0, ge=0)
    episodes_updated: int = Field(default=0, ge=0)

    def to_summary(self) -> dict[str, int]:
        """Serialize to the persisted summary shape (key = field name)."""
        return self.model_dump()


class EnrichCounters(CompoundValueObject):
    """Per-kind counters produced by a bulk metadata enrich.

    Attributes:
        movies_enriched: Movies whose metadata was filled/refreshed.
        series_enriched: Series whose metadata was filled/refreshed.
        skipped: Items left untouched (already complete, or no match).
    """

    movies_enriched: int = Field(default=0, ge=0)
    series_enriched: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)

    def to_summary(self) -> dict[str, int]:
        """Serialize to the persisted summary shape (key = field name)."""
        return self.model_dump()


__all__ = ["EnrichCounters", "ScanCounters"]

"""Thumbnail backfill tunables — cadence and output directory."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class ThumbnailBackfillConfig(CompoundValueObject):
    """Operational knobs for the scrub-preview backfill job.

    Attributes:
        enabled: Toggle for the periodic job that fills in scrub-preview
            sprites for movies and episodes that don't have one yet
            (e.g. items added by a scan but never streamed).
        batch_size: Maximum number of media items processed per tick.
            Lower values reduce CPU spikes; higher values catch up
            faster on a large catalog.
        interval_minutes: How often the backfill job runs.
        subdir: Subdirectory (relative to each media file's parent
            folder) where the generated sprite + VTT pair is written,
            nested under a per-stem leaf so episodes that share a
            season folder do not overwrite each other.

    Example:
        >>> cfg = ThumbnailBackfillConfig()
        >>> faster = cfg.with_updates(batch_size=20, interval_minutes=10)
    """

    enabled: bool = Field(default=True)
    batch_size: int = Field(default=10, ge=1)
    interval_minutes: int = Field(default=20, ge=1)
    subdir: str = Field(default=".homeflix/thumbnails", min_length=1)


__all__ = ["ThumbnailBackfillConfig"]

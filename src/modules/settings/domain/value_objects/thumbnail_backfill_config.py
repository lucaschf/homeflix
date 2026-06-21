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
        eager_concurrency: Maximum number of sprite generations the
            eager (on-play) trigger runs in parallel. Each generation
            decodes a whole file (NVDEC), so an unbounded burst — e.g.
            HLS remounts re-firing for the same session, or several
            preview-less titles played back-to-back — would peg the GPU.
            Excess eager requests queue until a slot frees. The periodic
            backfill is always sequential and ignores this cap.

    Example:
        >>> cfg = ThumbnailBackfillConfig()
        >>> faster = cfg.with_updates(batch_size=20, interval_minutes=10)
    """

    enabled: bool = Field(default=True)
    batch_size: int = Field(default=10, ge=1)
    interval_minutes: int = Field(default=20, ge=1)
    subdir: str = Field(default=".homeflix/thumbnails", min_length=1)
    eager_concurrency: int = Field(default=2, ge=1, le=4)


__all__ = ["ThumbnailBackfillConfig"]

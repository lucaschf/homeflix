"""Artwork mirror tunables — cadence, batch size, size ceiling (ADR-029)."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class ArtworkMirrorConfig(CompoundValueObject):
    """Operational knobs for the periodic artwork-mirror job.

    Attributes:
        enabled: Toggle for the periodic job that downloads still-remote
            poster/backdrop/logo images (TMDB URLs) and mirrors them into
            local storage, replacing the stored field with the local
            reference so the catalog stops depending on the provider CDN.
        batch_size: Maximum media items (movies + series) processed per
            tick. Bounds network + disk work per run on a large catalog.
        interval_minutes: How often the mirror job runs.
        max_bytes: Hard ceiling on a single downloaded image. Larger
            responses are skipped (kept as remote URLs) so a hostile or
            mis-sized URL cannot exhaust memory during the download.

    Example:
        >>> cfg = ArtworkMirrorConfig()
        >>> faster = cfg.with_updates(batch_size=50, interval_minutes=15)
    """

    enabled: bool = Field(default=True)
    batch_size: int = Field(default=20, ge=1)
    interval_minutes: int = Field(default=30, ge=1)
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)


__all__ = ["ArtworkMirrorConfig"]

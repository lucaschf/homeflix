"""Streaming tunables — ffmpeg parallelism and HLS cache cap."""

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class StreamingConfig(CompoundValueObject):
    """Operational knobs for HLS transcoding and segment caching.

    Attributes:
        ffmpeg_threads: Maximum worker threads ffmpeg may use per
            invocation (applied as ``-threads N`` on every ffmpeg
            call). ``None`` leaves ffmpeg in "auto" mode, which uses
            every logical core. Set this to roughly ``cpu_count // 2``
            to cap transcoding to ~50% of the host. Caps parallelism,
            not absolute CPU — use cgroups or equivalent for a hard
            limit. Applies to HLS transcoding, subtitle extraction,
            and scrub-preview sprite generation.
        hls_cache_max_size_mb: Maximum HLS cache size in megabytes.
            When the directory exceeds this size, the least-recently-
            accessed buckets are deleted until the cache fits. Bump
            on large catalogs to avoid re-transcoding popular titles
            on every visit.

    Example:
        >>> cfg = StreamingConfig(ffmpeg_threads=4, hls_cache_max_size_mb=10240)
    """

    ffmpeg_threads: int | None = Field(default=None, ge=1)
    hls_cache_max_size_mb: int = Field(default=5120, ge=1)


__all__ = ["StreamingConfig"]

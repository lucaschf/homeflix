"""Streaming tunables — ffmpeg parallelism, HLS cache cap, and hardware accel."""

from enum import StrEnum

from pydantic import Field

from src.building_blocks.domain.value_objects import CompoundValueObject


class HardwareAccel(StrEnum):
    """Video encoder selection for the HLS transcode path.

    Members:
        AUTO: Probe the host for a working NVENC encoder at runtime and
            use it when present; fall back to software ``libx264``
            otherwise. The safe default — a machine without an NVIDIA
            GPU silently stays on software.
        NVENC: Force NVIDIA NVENC (``h264_nvenc`` + CUDA decode). Use
            on a known-good GPU host to skip the probe. A broken or
            absent encoder surfaces as a transcode failure rather than
            falling back.
        OFF: Force software ``libx264``, ignoring any available GPU.
            Useful for CI, containers without ``--gpus``, or to A/B the
            two paths.
    """

    AUTO = "auto"
    NVENC = "nvenc"
    OFF = "off"


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
            on every visit. Set to ``0`` to disable LRU eviction
            entirely (the cache will grow without bound).
        hw_accel: Which video encoder the HLS transcode path uses.
            ``AUTO`` (default) prefers NVENC when a functional GPU
            encoder is detected and falls back to software libx264 —
            decisive for 4K/HEVC sources where software encoding
            bottlenecks the CPU. Has no effect on the H.264 ``copy``
            fast path, which never re-encodes.

    Example:
        >>> cfg = StreamingConfig(ffmpeg_threads=4, hls_cache_max_size_mb=10240)
        >>> cfg.hw_accel
        <HardwareAccel.AUTO: 'auto'>
    """

    ffmpeg_threads: int | None = Field(default=None, ge=1)
    hls_cache_max_size_mb: int = Field(default=5120, ge=0)
    hw_accel: HardwareAccel = Field(default=HardwareAccel.AUTO)


__all__ = ["HardwareAccel", "StreamingConfig"]

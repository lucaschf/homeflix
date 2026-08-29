"""Shared media-probe contract.

The probe port and its :class:`ProbeResult` DTO live in the shared kernel
because both the Media catalog scan and the Streaming context need to
inspect a media file's audio/subtitle/resolution metadata. The concrete
ffprobe-backed implementation lives in the Streaming infrastructure and is
wired into both contexts at the composition root.
"""

from src.shared_kernel.media_probe.media_probe_port import (
    MediaProbePort,
    ProbeResult,
)

__all__ = ["MediaProbePort", "ProbeResult"]

"""Hardware-acceleration (NVENC/CUDA) capability probing for HLS transcodes.

Extracted from ``HlsService`` (pure, no locks/threads): decides whether a
transcode should run on the GPU. Wraps the persisted ``hw_accel`` knob and
memoises the one-time functional NVENC probe so the first AUTO-mode
transcode pays the cold CUDA init once and every later call reads a cached
boolean.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

from src.modules.streaming.infrastructure.streaming._subprocess import (
    HW_ACCEL_NVENC,
    HW_ACCEL_OFF,
    SUBPROCESS_TEXT_KWARGS,
)

if TYPE_CHECKING:
    from src.modules.streaming.application.ports.runtime_config_ports import HlsRuntimeConfigPort

_logger = logging.getLogger(__name__)

# Wall-clock cap for the one-time NVENC functional probe. Deliberately
# generous: the probe is the process's first CUDA call, so it absorbs the
# cold driver / context init, which was measured at ~20s on a cold but
# perfectly working GPU. Cutting this to a few seconds would time out
# that cold init and make AUTO mode fall back to software on a host that
# actually has a usable encoder — the exact false negative this feature
# exists to avoid. The cost (a longer first play once per process on a
# hung driver) fits inside the 120s first-segment budget.
_NVENC_PROBE_TIMEOUT = 30


class HardwareAccelerationProbe:
    """Resolve whether a transcode should use NVENC, honouring ``hw_accel``.

    Args:
        runtime_settings: Snapshot facade for :class:`StreamingConfig`.
            ``hw_accel`` is read fresh per decision via the sync snapshot.
    """

    def __init__(self, runtime_settings: HlsRuntimeConfigPort) -> None:
        self._runtime_settings = runtime_settings
        # Memoised result of the one-time NVENC functional probe (None
        # until first transcode in AUTO mode forces the check).
        self._nvenc_probe: bool | None = None

    @staticmethod
    def probe_video_codec(file_path: str) -> str | None:
        """Detect video codec using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                **SUBPROCESS_TEXT_KWARGS,
                check=False,
                timeout=10,
            )
            codec = result.stdout.strip().lower()
            return codec if codec else None
        except Exception:
            return None

    @staticmethod
    def detect_nvenc() -> bool:
        """Functionally probe whether ``h264_nvenc`` can actually encode.

        The encoder being *listed* by ffmpeg is not enough — a host can
        ship an ffmpeg with NVENC compiled in while lacking the GPU,
        driver, or a free encode session. We run a sub-second throwaway
        encode of a synthetic source through CUDA so AUTO mode only
        commits to NVENC when the full decode→encode path works.

        Returns ``True`` only on a clean (exit 0) probe encode.
        """
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=256x256:r=10",
                    "-t",
                    "0.2",
                    "-c:v",
                    "h264_nvenc",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=_NVENC_PROBE_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def nvenc_available(self) -> bool:
        """Return the memoised NVENC functional-probe result.

        Probed at most once per instance — the first transcode in AUTO
        mode pays the ~1s cold-start CUDA init, every later call reads
        the cached boolean.
        """
        if self._nvenc_probe is None:
            self._nvenc_probe = self.detect_nvenc()
            _logger.info("NVENC functional probe result: %s", self._nvenc_probe)
        return self._nvenc_probe

    def use_nvenc(self) -> bool:
        """Decide whether this transcode should use NVENC.

        Honours the persisted ``hw_accel`` knob: ``off`` forces
        software, ``nvenc`` forces hardware (a broken encoder then
        surfaces as a transcode failure rather than silently falling
        back), and ``auto`` defers to the cached functional probe.
        """
        mode = self._runtime_settings.streaming_snapshot_sync().hw_accel
        if mode == HW_ACCEL_OFF:
            return False
        if mode == HW_ACCEL_NVENC:
            return True
        return self.nvenc_available()


__all__ = ["HardwareAccelerationProbe"]

"""Video analysis primitives — ffmpeg frame sampling + perceptual hashing.

The frame hasher gracefully degrades to ``None`` when ffmpeg is missing
on PATH, so the frame-hash intro detector can stay opt-in without
crashing the host on minimal images.
"""

from src.modules.media.infrastructure.video.frame_hash_correlator import (
    FrameHashCorrelator,
    FrameHashTuning,
)
from src.modules.media.infrastructure.video.frame_hash_intro_detector import (
    FrameHashIntroDetector,
)
from src.modules.media.infrastructure.video.frame_hasher import FrameHasher

__all__ = [
    "FrameHashCorrelator",
    "FrameHashIntroDetector",
    "FrameHashTuning",
    "FrameHasher",
]

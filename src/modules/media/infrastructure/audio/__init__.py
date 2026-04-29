"""Audio analysis primitives — ffmpeg extraction + Chromaprint fingerprints.

Both wrappers gracefully degrade to ``None`` when their backing system
binary (``ffmpeg`` / ``fpcalc``) is missing on PATH, so feature flags
that depend on intro detection can stay opt-in without crashing the
host on minimal Docker images.
"""

from src.modules.media.infrastructure.audio.audio_extractor import AudioExtractor
from src.modules.media.infrastructure.audio.chromaprint_service import (
    ChromaprintFingerprint,
    ChromaprintService,
)

__all__ = ["AudioExtractor", "ChromaprintFingerprint", "ChromaprintService"]

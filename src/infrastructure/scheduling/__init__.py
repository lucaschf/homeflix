"""Background scheduling infrastructure.

The scheduler coordinates recurring work (library scans, scrub-preview
thumbnail backfill, intro detection, scan-dedup sweep) without coupling
the domain or application layers to any specific scheduling backend.
"""

from src.infrastructure.scheduling.intro_detection_job import IntroDetectionJob
from src.infrastructure.scheduling.scan_dedup_sweep_job import ScanDedupSweepJob
from src.infrastructure.scheduling.scheduler_service import LibraryScanScheduler
from src.infrastructure.scheduling.thumbnail_backfill_job import ThumbnailBackfillJob

__all__ = [
    "IntroDetectionJob",
    "LibraryScanScheduler",
    "ScanDedupSweepJob",
    "ThumbnailBackfillJob",
]

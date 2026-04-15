"""Background scheduling infrastructure.

The scheduler coordinates recurring work (library scans today;
trickplay generation and periodic enrichment later) without
coupling the domain or application layers to any specific
scheduling backend.
"""

from src.infrastructure.scheduling.scheduler_service import LibraryScanScheduler

__all__ = ["LibraryScanScheduler"]

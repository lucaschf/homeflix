"""Consumer-defined read port for HLS cache occupancy (admin overview).

The admin Overview aggregator (Media BC) shows an HLS occupancy card, but
the HLS cache now lives in the Streaming BC. This port is the slice the
aggregator needs; its adapter lives in ``media.infrastructure.acl`` and
delegates to Streaming's ``GetHlsCacheStatsUseCase`` (ADR-009), so the
use case never imports Streaming directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HlsCacheStatsView:
    """Media-side projection of the streaming HLS cache snapshot.

    Attributes:
        size_bytes: Bytes currently used on disk under the cache root.
        max_bytes: Configured ceiling.
        last_cleared_at: Wallclock time of the last global clear, or
            ``None``.
    """

    size_bytes: int
    max_bytes: int
    last_cleared_at: datetime | None


class HlsCacheStatsReadPort(ABC):
    """Read the current HLS cache occupancy without the Streaming BC."""

    @abstractmethod
    def get_stats(self) -> HlsCacheStatsView:
        """Return the current cache occupancy snapshot."""
        ...


__all__ = ["HlsCacheStatsReadPort", "HlsCacheStatsView"]

"""Port for querying media counts from the Media bounded context.

The Library BC exposes per-library movie/series counts in its output
DTO but does not own the media catalog. This port describes the
minimal read contract Library requires from Media. The adapter lives
in ``library.infrastructure.acl`` and translates from Media's
``MovieRepository`` / ``SeriesRepository``.

See ADR-009 for the cross-BC read port pattern.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class MediaCountQueryPort(ABC):
    """Read-only query of media counts under a set of directory paths.

    This is the only surface through which the Library BC reaches into
    the Media catalog. Keep it narrow — anything richer than counts
    should trigger a conversation about whether the responsibility
    belongs in Library at all.
    """

    @abstractmethod
    async def count_movies_under_paths(self, paths: Sequence[str]) -> int:
        """Count movies whose primary file sits under any of ``paths``.

        Args:
            paths: Absolute directory paths. Empty sequence returns ``0``.

        Returns:
            Non-negative count of distinct movies.
        """
        ...

    @abstractmethod
    async def count_series_under_paths(self, paths: Sequence[str]) -> int:
        """Count series with at least one episode file under ``paths``.

        Args:
            paths: Absolute directory paths. Empty sequence returns ``0``.

        Returns:
            Non-negative count of distinct series.
        """
        ...


__all__ = ["MediaCountQueryPort"]

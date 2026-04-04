"""Series repository interface."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from src.modules.media.domain.entities.series import Series
from src.modules.media.domain.value_objects import EpisodeId, FilePath, SeriesId, Title


class SeriesRepository(ABC):
    """Repository interface for Series aggregate.

    This is a port in the hexagonal architecture pattern.
    Implementations (adapters) will be in the infrastructure layer.
    """

    @abstractmethod
    async def find_by_id(self, series_id: SeriesId) -> Series | None:
        """Find a series by its ID (includes seasons and episodes).

        Args:
            series_id: The series' external ID.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def save(self, series: Series) -> Series:
        """Persist a series with all its seasons and episodes.

        Args:
            series: The series to save.

        Returns:
            The saved series (with generated IDs if new).
        """
        ...

    @abstractmethod
    async def delete(self, series_id: SeriesId) -> bool:
        """Delete a series and all its seasons/episodes.

        Args:
            series_id: The series' external ID.

        Returns:
            True if deleted, False if not found.
        """
        ...

    @abstractmethod
    async def list_all(self) -> Sequence[Series]:
        """List all series (may return shallow objects without episodes).

        Returns:
            Sequence of all series.
        """
        ...

    @abstractmethod
    async def find_by_episode_id(self, episode_id: EpisodeId) -> Series | None:
        """Find a series containing an episode with this ID.

        Args:
            episode_id: The episode's external ID.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_title(self, title: Title) -> Series | None:
        """Find a series by its title (case-insensitive).

        Args:
            title: The series title to search for.

        Returns:
            The Series if found, None otherwise.
        """
        ...

    @abstractmethod
    async def find_by_file_path(self, file_path: FilePath) -> Series | None:
        """Find a series containing an episode with this file path.

        Args:
            file_path: The absolute file path.

        Returns:
            The Series if found, None otherwise.
        """
        ...


__all__ = ["SeriesRepository"]

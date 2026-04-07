"""ClearProgressUseCase - Clear watch progress for a media item."""

from dataclasses import dataclass

from src.modules.watch_progress.domain.repositories import WatchProgressRepository


@dataclass(frozen=True)
class ClearProgressInput:
    """Input for ClearProgressUseCase.

    Attributes:
        media_id: External ID of the media.
    """

    media_id: str


class ClearProgressUseCase:
    """Clear (soft-delete) watch progress for a media item.

    Example:
        >>> use_case = ClearProgressUseCase(progress_repository)
        >>> await use_case.execute(ClearProgressInput("mov_abc123def456"))
    """

    def __init__(self, progress_repository: WatchProgressRepository) -> None:
        """Initialize the use case.

        Args:
            progress_repository: Repository for watch progress persistence.
        """
        self._repo = progress_repository

    async def execute(self, input_dto: ClearProgressInput) -> bool:
        """Execute the use case.

        Args:
            input_dto: Contains the media_id to clear.

        Returns:
            True if progress was found and deleted, False otherwise.
        """
        return await self._repo.delete(input_dto.media_id)


__all__ = ["ClearProgressUseCase"]

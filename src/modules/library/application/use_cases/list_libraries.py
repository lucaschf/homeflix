"""ListLibrariesUseCase."""

from src.modules.library.application.dtos.library_dtos import LibraryOutput
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.repositories.library_repository import LibraryRepository
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository


class ListLibrariesUseCase:
    """Return every non-deleted library."""

    def __init__(
        self,
        library_repository: LibraryRepository,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        self._repo = library_repository
        self._movie_repo = movie_repository
        self._series_repo = series_repository

    async def execute(self) -> list[LibraryOutput]:
        """List all libraries.

        Returns:
            List of ``LibraryOutput`` ordered by name.
        """
        entities = await self._repo.find_all()
        return [await library_to_output(e, self._movie_repo, self._series_repo) for e in entities]


__all__ = ["ListLibrariesUseCase"]

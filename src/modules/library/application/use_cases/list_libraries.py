"""ListLibrariesUseCase."""

from src.modules.library.application.dtos.library_dtos import LibraryOutput
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.repositories.library_repository import LibraryRepository


class ListLibrariesUseCase:
    """Return every non-deleted library."""

    def __init__(self, library_repository: LibraryRepository) -> None:
        self._repo = library_repository

    async def execute(self) -> list[LibraryOutput]:
        """List all libraries.

        Returns:
            List of ``LibraryOutput`` ordered by name.
        """
        entities = await self._repo.find_all()
        return [library_to_output(e) for e in entities]


__all__ = ["ListLibrariesUseCase"]

"""ListLibrariesUseCase."""

from src.modules.library.application.dtos.library_dtos import LibraryOutput
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.repositories.library_repository import LibraryRepository


class ListLibrariesUseCase:
    """Return every non-deleted library."""

    def __init__(
        self,
        library_repository: LibraryRepository,
        media_count_query: MediaCountQueryPort,
    ) -> None:
        self._repo = library_repository
        self._media_count_query = media_count_query

    async def execute(self) -> list[LibraryOutput]:
        """List all libraries.

        The count queries fan out serially on purpose: every repo on
        this request shares the same ``AsyncSession`` (see
        ``session_manager.py``), and SQLAlchemy sessions forbid
        concurrent ``execute`` calls on the same transaction — a
        ``gather`` here raises ``InvalidRequestError`` the moment two
        libraries exist. For tens of libraries the serial cost is
        negligible; batching would require a dedicated short-lived
        session per library and isn't worth the complexity today.

        Returns:
            List of ``LibraryOutput`` ordered by name.
        """
        entities = await self._repo.find_all()
        return [await library_to_output(e, self._media_count_query) for e in entities]


__all__ = ["ListLibrariesUseCase"]

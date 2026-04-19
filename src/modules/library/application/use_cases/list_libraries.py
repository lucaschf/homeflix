"""ListLibrariesUseCase."""

from src.modules.library.application.dtos.library_dtos import LibraryOutput
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.library.application.use_cases._counts import resolve_counts
from src.modules.library.application.use_cases._to_output import library_to_output


class ListLibrariesUseCase:
    """Return every non-deleted library."""

    def __init__(
        self,
        uow_factory: LibraryUnitOfWorkFactory,
        media_count_query: MediaCountQueryPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._media_count_query = media_count_query

    async def execute(self) -> list[LibraryOutput]:
        """List all libraries.

        The count queries fan out serially: each
        ``MediaCountQueryPort`` call opens its own short-lived
        ``AsyncSession`` internally, so a ``gather`` would only buy
        concurrency at the cost of spawning 2N connections for N
        libraries. For tens of libraries the serial cost is
        negligible.

        Returns:
            List of ``LibraryOutput`` ordered by name.
        """
        async with self._uow_factory() as uow:
            entities = await uow.libraries.find_all()
        outputs: list[LibraryOutput] = []
        for entity in entities:
            movie_count, series_count = await resolve_counts(entity, self._media_count_query)
            outputs.append(
                library_to_output(entity, movie_count=movie_count, series_count=series_count)
            )
        return outputs


__all__ = ["ListLibrariesUseCase"]

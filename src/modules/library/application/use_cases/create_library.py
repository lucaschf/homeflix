"""CreateLibraryUseCase."""

from src.modules.library.application.dtos.library_dtos import (
    CreateLibraryInput,
    LibraryOutput,
)
from src.modules.library.application.ports import MediaCountQueryPort
from src.modules.library.application.unit_of_work import LibraryUnitOfWorkFactory
from src.modules.library.application.use_cases._counts import resolve_counts
from src.modules.library.application.use_cases._to_output import library_to_output
from src.modules.library.domain.entities.library import Library
from src.modules.library.domain.value_objects.library_type import LibraryType


class CreateLibraryUseCase:
    """Create a new library and persist it."""

    def __init__(
        self,
        uow_factory: LibraryUnitOfWorkFactory,
        media_count_query: MediaCountQueryPort,
    ) -> None:
        self._uow_factory = uow_factory
        self._media_count_query = media_count_query

    async def execute(self, input_dto: CreateLibraryInput) -> LibraryOutput:
        """Create and persist a new Library.

        Args:
            input_dto: Library creation parameters.

        Returns:
            The persisted library as a ``LibraryOutput``.
        """
        library = Library.create(
            name=input_dto.name,
            library_type=LibraryType(input_dto.library_type),
            paths=input_dto.paths,
            language=input_dto.language,
            metadata_providers=input_dto.metadata_providers,
            settings=input_dto.settings,
        )
        if input_dto.scan_schedule:
            library = library.with_updates(scan_schedule=input_dto.scan_schedule)

        async with self._uow_factory() as uow:
            saved = await uow.libraries.save(library)
        movie_count, series_count = await resolve_counts(saved, self._media_count_query)
        return library_to_output(saved, movie_count=movie_count, series_count=series_count)


__all__ = ["CreateLibraryUseCase"]

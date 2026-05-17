"""DeleteSeriesUseCase - Soft-delete a series by ID."""

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.media.application.dtos.series_dtos import DeleteSeriesInput
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.value_objects import SeriesId


class DeleteSeriesUseCase:
    """Soft-delete a series by its external ID.

    Marks the series as deleted in the database. The record (and the
    cascaded seasons / episodes / media_files children) stays on disk
    so the soft-delete can be undone later via DB intervention.
    Mirrors ``DeleteMovieUseCase``.

    Example:
        >>> use_case = DeleteSeriesUseCase(uow_factory)
        >>> await use_case.execute(DeleteSeriesInput("ser_abc123"))
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, input_dto: DeleteSeriesInput) -> None:
        """Soft-delete the series.

        Args:
            input_dto: Contains the ``series_id`` to delete.

        Raises:
            ResourceNotFoundException: When no series matches the id.
        """
        series_id = SeriesId(input_dto.series_id)
        async with self._uow_factory() as uow:
            deleted = await uow.series.delete(series_id)

        if not deleted:
            raise ResourceNotFoundException.for_resource("Series", input_dto.series_id)


__all__ = ["DeleteSeriesUseCase"]

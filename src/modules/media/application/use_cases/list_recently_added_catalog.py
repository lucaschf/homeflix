"""ListRecentlyAddedCatalogUseCase - mixed (movies + series) recents."""

import asyncio
from collections.abc import Sequence
from typing import cast

from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListRecentlyAddedCatalogInput,
    ListRecentlyAddedCatalogOutput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series
from src.shared_kernel.value_objects.library_id import LibraryId


class ListRecentlyAddedCatalogUseCase:
    """Mixed top-N most recently added titles across movies + series.

    Each repo is asked for its top ``limit`` newest entries (ordered
    by ``id DESC`` — see ``MovieRepository.list_recently_added``);
    the two streams are merged in Python by ``created_at`` descending
    and the merge is trimmed to ``limit``. Each repo's own internal
    auto-increment id is monotonic with insertion within its own
    table, but ids aren't comparable across the two tables so a real
    timestamp is required for the cross-stream sort —
    ``DomainEntity.created_at`` is populated on insert and is
    suitable.

    Worst case the use case over-fetches by ``limit`` rows from one
    side (when one stream is empty), which is fine: ``list_recently_added``
    is a single ``LIMIT N`` query per repo.

    Example:
        >>> use_case = ListRecentlyAddedCatalogUseCase(uow_factory)
        >>> result = await use_case.execute(
        ...     ListRecentlyAddedCatalogInput(limit=20)
        ... )
        >>> len(result.items)
        20
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_library_access: ProfileLibraryAccessPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            profile_library_access: Port that resolves the caller's
                allowed library_ids.
        """
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access

    async def execute(
        self, input_dto: ListRecentlyAddedCatalogInput
    ) -> ListRecentlyAddedCatalogOutput:
        """Execute the use case.

        Args:
            input_dto: ``profile_id``, ``limit`` (max items in the
                merged result) and ``lang``.

        Returns:
            ``ListRecentlyAddedCatalogOutput`` with the merged page,
            newest first. Empty when the caller's profile has no
            ``allowed_library_ids`` — short-circuits the UoW.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return ListRecentlyAddedCatalogOutput(items=[])

        # Each branch opens its own UoW because SQLAlchemy AsyncSession
        # forbids concurrent execution on the same session — same
        # pattern as ``ListByGenreUseCase``.
        movies, series_list = await asyncio.gather(
            self._fetch_recent_movies(input_dto.limit, allowed),
            self._fetch_recent_series(input_dto.limit, allowed),
        )

        merged: list[Movie | Series] = sorted(
            cast("list[Movie | Series]", [*movies, *series_list]),
            key=lambda item: item.created_at,
            reverse=True,
        )[: input_dto.limit]

        return ListRecentlyAddedCatalogOutput(
            items=[self._to_output(item, input_dto.lang) for item in merged],
        )

    async def _fetch_recent_movies(
        self, limit: int, allowed_library_ids: Sequence[LibraryId]
    ) -> list[Movie]:
        async with self._uow_factory() as uow:
            return list(
                await uow.movies.list_recently_added(
                    limit,
                    allowed_library_ids=allowed_library_ids,
                )
            )

    async def _fetch_recent_series(
        self, limit: int, allowed_library_ids: Sequence[LibraryId]
    ) -> list[Series]:
        async with self._uow_factory() as uow:
            return list(
                await uow.series.list_recently_added(
                    limit,
                    allowed_library_ids=allowed_library_ids,
                )
            )

    @staticmethod
    def _to_output(item: Movie | Series, lang: str) -> CatalogItemOutput:
        """Convert a movie/series entity into the catalog row DTO.

        Same projection used by ``ListByGenreUseCase._to_output`` —
        kept as a private static method here instead of imported to
        avoid a cross use-case dependency. The DTO is small and
        mirrored in two places at most.
        """
        if isinstance(item, Movie):
            return CatalogItemOutput(
                id=str(item.id),
                type="movie",
                title=item.get_title(lang),
                year=item.year.value,
                synopsis=item.get_synopsis(lang),
                poster_path=item.get_poster_path(lang),
                backdrop_path=item.get_backdrop_path(lang),
                genres=item.get_genres(lang),
            )
        return CatalogItemOutput(
            id=str(item.id),
            type="series",
            title=item.get_title(lang),
            year=item.start_year.value,
            synopsis=item.get_synopsis(lang),
            poster_path=item.get_poster_path(lang),
            backdrop_path=item.get_backdrop_path(lang),
            genres=item.get_genres(lang),
        )


__all__ = ["ListRecentlyAddedCatalogUseCase"]

"""GetFeaturedMediaUseCase - Random media for hero banner."""

import random

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series


class GetFeaturedMediaUseCase:
    """Return random movies and/or series for the hero banner.

    Fetches items with backdrop images from the database using
    random ordering, then maps to a flat output list.

    Per ADR-010, the random pool is restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = GetFeaturedMediaUseCase(uow_factory, profile_library_access)
        >>> items = await use_case.execute(
        ...     GetFeaturedInput(profile_id="prf_abc", media_type="all", limit=6)
        ... )
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

    async def execute(self, input_dto: GetFeaturedInput) -> list[FeaturedItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains profile_id, media_type, limit, and lang.

        Returns:
            List of FeaturedItemOutput for the hero banner.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return []

        results: list[FeaturedItemOutput] = []
        lang = input_dto.lang

        async with self._uow_factory() as uow:
            if input_dto.media_type in ("all", "movie"):
                movies = await uow.movies.find_random(
                    input_dto.limit,
                    with_backdrop=True,
                    allowed_library_ids=allowed,
                )
                results.extend(self._movie_to_output(m, lang) for m in movies)

            if input_dto.media_type in ("all", "series"):
                series_list = await uow.series.find_random(
                    input_dto.limit,
                    with_backdrop=True,
                    allowed_library_ids=allowed,
                )
                results.extend(self._series_to_output(s, lang) for s in series_list)

        if input_dto.media_type == "all":
            random.shuffle(results)

        return results[: input_dto.limit]

    @staticmethod
    def _movie_to_output(movie: Movie, lang: str) -> FeaturedItemOutput:
        """Convert Movie entity to featured output."""
        return FeaturedItemOutput(
            id=str(movie.id),
            type="movie",
            title=movie.get_title(lang),
            synopsis=movie.get_synopsis(lang),
            year=movie.year.value,
            duration_formatted=movie.duration.format_hms(),
            genres=movie.get_genres(lang),
            backdrop_path=movie.get_backdrop_path(lang),
            logo_path=movie.get_logo_path(lang),
            content_rating=movie.content_rating.value if movie.content_rating else None,
            trailer_url=movie.trailer_url,
        )

    @staticmethod
    def _series_to_output(series: Series, lang: str) -> FeaturedItemOutput:
        """Convert Series entity to featured output."""
        return FeaturedItemOutput(
            id=str(series.id),
            type="series",
            title=series.get_title(lang),
            synopsis=series.get_synopsis(lang),
            year=series.start_year.value,
            duration_formatted=None,
            genres=series.get_genres(lang),
            backdrop_path=series.get_backdrop_path(lang),
            logo_path=series.get_logo_path(lang),
            content_rating=series.content_rating.value if series.content_rating else None,
            trailer_url=series.trailer_url,
        )


__all__ = ["GetFeaturedMediaUseCase"]

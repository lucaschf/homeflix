"""GetFeaturedMediaUseCase - Random media for hero banner."""

import random

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.unit_of_work import MediaUnitOfWorkFactory
from src.modules.media.domain.entities import Movie, Series


class GetFeaturedMediaUseCase:
    """Return random movies and/or series for the hero banner.

    Fetches items with backdrop images from the database using
    random ordering, then maps to a flat output list.

    Example:
        >>> use_case = GetFeaturedMediaUseCase(uow_factory)
        >>> items = await use_case.execute(GetFeaturedInput(media_type="all", limit=6))
    """

    def __init__(self, uow_factory: MediaUnitOfWorkFactory) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
        """
        self._uow_factory = uow_factory

    async def execute(self, input_dto: GetFeaturedInput) -> list[FeaturedItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains media_type, limit, and lang.

        Returns:
            List of FeaturedItemOutput for the hero banner.
        """
        results: list[FeaturedItemOutput] = []
        lang = input_dto.lang

        async with self._uow_factory() as uow:
            if input_dto.media_type in ("all", "movie"):
                movies = await uow.movies.find_random(input_dto.limit, with_backdrop=True)
                results.extend(self._movie_to_output(m, lang) for m in movies)

            if input_dto.media_type in ("all", "series"):
                series_list = await uow.series.find_random(input_dto.limit, with_backdrop=True)
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
            backdrop_path=movie.backdrop_path.value if movie.backdrop_path else None,
            logo_path=movie.logo_path.value if movie.logo_path else None,
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
            backdrop_path=series.backdrop_path.value if series.backdrop_path else None,
            logo_path=series.logo_path.value if series.logo_path else None,
            content_rating=series.content_rating.value if series.content_rating else None,
            trailer_url=series.trailer_url,
        )


__all__ = ["GetFeaturedMediaUseCase"]

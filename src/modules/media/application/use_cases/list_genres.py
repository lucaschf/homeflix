"""ListGenresUseCase - aggregate genres across movies and series."""

from src.modules.media.application.dtos.catalog_dtos import (
    GenreOutput,
    ListGenresInput,
    ListGenresOutput,
)
from src.modules.media.domain.repositories import MovieRepository, SeriesRepository
from src.modules.media.domain.repositories.movie_repository import GenreRow


class ListGenresUseCase:
    """Cross-cutting use case that aggregates genres across both media types.

    Reads the lightweight ``GenreRow`` projection from each repository
    (which only fetches the ``genres`` and ``localized`` columns), then
    folds the canonical genre names into a count + the first localized
    label seen for each.

    The "first localized label" strategy is intentional: in a healthy
    catalog every row tagged with canonical "Action" should resolve to
    the same translation (e.g. "Ação"), so picking the first one is
    deterministic enough. If two rows ever disagree on a translation,
    the first one wins — fixing the inconsistency is a metadata
    cleanup task, not a use-case responsibility.

    Sort order: by count descending, then alphabetically by display
    name. This puts the most-populated carousels at the top of the
    Home page where they're most useful.

    Example:
        >>> use_case = ListGenresUseCase(movie_repo, series_repo)
        >>> result = await use_case.execute(ListGenresInput(lang="pt-BR"))
        >>> result.genres[0]
        GenreOutput(id="Action", name="Ação", count=42)
    """

    def __init__(
        self,
        movie_repository: MovieRepository,
        series_repository: SeriesRepository,
    ) -> None:
        """Initialize the use case.

        Args:
            movie_repository: Movie repo, used for ``list_genre_rows``.
            series_repository: Series repo, used for ``list_genre_rows``.
        """
        self._movie_repository = movie_repository
        self._series_repository = series_repository

    async def execute(self, input_dto: ListGenresInput) -> ListGenresOutput:
        """Execute the use case.

        Args:
            input_dto: Carries the requested ``lang``.

        Returns:
            ``ListGenresOutput`` with one ``GenreOutput`` per unique
            canonical genre present in the library.
        """
        movie_rows = await self._movie_repository.list_genre_rows(input_dto.lang)
        series_rows = await self._series_repository.list_genre_rows(input_dto.lang)

        counts: dict[str, int] = {}
        localized_label: dict[str, str] = {}

        # Two explicit loops instead of `for row in (*movie_rows, *series_rows):`
        # — the spread builds a brand-new tuple containing every row
        # from both repositories, temporarily doubling memory for
        # large catalogs. Iterating each sequence in turn does the
        # exact same fold without the copy.
        for row in movie_rows:
            self._fold_row(row, counts, localized_label)
        for row in series_rows:
            self._fold_row(row, counts, localized_label)

        genres = [
            GenreOutput(
                id=canonical,
                name=localized_label.get(canonical, canonical),
                count=count,
            )
            for canonical, count in counts.items()
        ]
        # Sort by count descending, then alphabetical (case-insensitive)
        # so the most-populated carousels surface first and ties stay
        # deterministic across renders.
        genres.sort(key=lambda g: (-g.count, g.name.lower()))

        return ListGenresOutput(genres=genres)

    @staticmethod
    def _fold_row(
        row: GenreRow,
        counts: dict[str, int],
        localized_label: dict[str, str],
    ) -> None:
        """Fold one ``GenreRow`` into the running count + label maps.

        Iterates the canonical genres positionally and pairs each one
        with the corresponding localized name (when present). The
        first non-empty localized label seen for a canonical genre is
        the one that survives — see the class docstring for the
        rationale.
        """
        for index, canonical in enumerate(row.canonical_genres):
            counts[canonical] = counts.get(canonical, 0) + 1
            if canonical not in localized_label and index < len(row.localized_genres):
                label = row.localized_genres[index]
                if label:
                    localized_label[canonical] = label


__all__ = ["ListGenresUseCase"]

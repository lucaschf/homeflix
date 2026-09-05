"""GetFeaturedMediaUseCase - Recommended media for the hero banner."""

import random
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from src.modules.media.application.dtos.featured_dtos import (
    FeaturedItemOutput,
    GetFeaturedInput,
)
from src.modules.media.application.ports.profile_library_access_port import (
    ProfileLibraryAccessPort,
)
from src.modules.media.application.ports.watch_history_port import (
    WatchedTitle,
    WatchHistoryPort,
)
from src.modules.media.application.unit_of_work import (
    MediaUnitOfWork,
    MediaUnitOfWorkFactory,
)
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import Genre, MovieId, SeriesId
from src.shared_kernel.value_objects.library_id import LibraryId

# How many recently watched titles feed the taste profile. Wide enough
# that a couple of odd picks don't dominate, narrow enough that the
# profile tracks what the viewer is into *lately*.
_HISTORY_WINDOW = 50

# How many of the viewer's top genres the recommendation pool is
# restricted to. Backfill (see ``_pick``) relaxes the filter when the
# catalog doesn't have enough unseen titles in those genres.
_TOP_GENRES = 3

# A title watched to the end says more about taste than one abandoned
# halfway through.
_COMPLETED_WEIGHT = 2.0
_IN_PROGRESS_WEIGHT = 1.0

# Recency decay: a title's weight halves every ``_RECENCY_HALF_LIFE_DAYS``
# since it was last watched, so what the viewer is into *now* outranks a
# phase from months ago without ever dropping to zero.
_RECENCY_HALF_LIFE_DAYS = 30.0


class GetFeaturedMediaUseCase:
    """Return movies and/or series for the hero banner, tailored to the viewer.

    Reads the profile's recent watch history through ``WatchHistoryPort``
    (ADR-009) and:

    1. **Never repeats a watched title** — every movie or series the
       profile has progress on (in progress or completed) is excluded
       from the pool.
    2. **Prefers the viewer's favourite genres** — the genres of the
       watched titles are tallied (completed titles weigh more, recently
       watched titles weigh more) and the pool is first drawn from titles
       tagged with the top genres. Each recommended item reports which of
       its genres matched (``matched_genres``) so the UI can say why.
    3. **Backfills randomly** — when the genre pool can't fill ``limit``
       (small catalog, exotic taste) the remaining slots are drawn from
       any unseen title, so the hero is never empty just because the
       viewer already saw everything in their favourite genres.

    A profile with no history falls back to the original behaviour:
    random titles with a backdrop.

    Per ADR-010, the pool is restricted to the caller's
    ``Profile.allowed_library_ids`` via ``ProfileLibraryAccessPort``. A
    deny-all profile short-circuits to an empty list without opening
    the UoW.

    Example:
        >>> use_case = GetFeaturedMediaUseCase(
        ...     uow_factory, profile_library_access, watch_history
        ... )
        >>> items = await use_case.execute(
        ...     GetFeaturedInput(profile_id="prf_abc", media_type="all", limit=6)
        ... )
    """

    def __init__(
        self,
        uow_factory: MediaUnitOfWorkFactory,
        profile_library_access: ProfileLibraryAccessPort,
        watch_history: WatchHistoryPort,
    ) -> None:
        """Initialize the use case.

        Args:
            uow_factory: Factory that opens a fresh media Unit of Work.
            profile_library_access: Port that resolves the caller's
                allowed library_ids.
            watch_history: Port that resolves the caller's recently
                watched titles (movies and series).
        """
        self._uow_factory = uow_factory
        self._profile_library_access = profile_library_access
        self._watch_history = watch_history

    async def execute(self, input_dto: GetFeaturedInput) -> list[FeaturedItemOutput]:
        """Execute the use case.

        Args:
            input_dto: Contains profile_id, media_type, limit, and lang.

        Returns:
            List of FeaturedItemOutput for the hero banner. Genre-matched
            recommendations come first, random backfill last; each group
            is shuffled so the hero rotates between visits.
        """
        allowed = await self._profile_library_access.find_for_profile(input_dto.profile_id)
        if not allowed:
            return []

        history = await self._watch_history.list_recently_watched(
            input_dto.profile_id, limit=_HISTORY_WINDOW
        )
        watched_movie_ids = [MovieId(t.media_id) for t in history if t.media_type == "movie"]
        watched_series_ids = [SeriesId(t.media_id) for t in history if t.media_type == "series"]

        lang = input_dto.lang
        limit = input_dto.limit
        want_movies = input_dto.media_type in ("all", "movie")
        want_series = input_dto.media_type in ("all", "series")

        recommended: list[FeaturedItemOutput] = []
        backfill: list[FeaturedItemOutput] = []

        async with self._uow_factory() as uow:
            top_genres = await self._top_genres(uow, history, watched_movie_ids, watched_series_ids)

            if want_movies:
                matched_movies, extra_movies = await self._pick_movies(
                    uow, limit, allowed, top_genres, watched_movie_ids
                )
                recommended.extend(
                    self._movie_to_output(m, lang, top_genres) for m in matched_movies
                )
                backfill.extend(self._movie_to_output(m, lang) for m in extra_movies)

            if want_series:
                matched_series, extra_series = await self._pick_series(
                    uow, limit, allowed, top_genres, watched_series_ids
                )
                recommended.extend(
                    self._series_to_output(s, lang, top_genres) for s in matched_series
                )
                backfill.extend(self._series_to_output(s, lang) for s in extra_series)

        random.shuffle(recommended)
        random.shuffle(backfill)
        return (recommended + backfill)[:limit]

    @staticmethod
    async def _top_genres(
        uow: MediaUnitOfWork,
        history: Sequence[WatchedTitle],
        watched_movie_ids: Sequence[MovieId],
        watched_series_ids: Sequence[SeriesId],
    ) -> list[Genre]:
        """Tally the genres of the watched titles and keep the top few."""
        if not history:
            return []

        watched_movies = await uow.movies.find_by_ids(watched_movie_ids)
        watched_series = await uow.series.find_by_ids(watched_series_ids)

        genres_by_id: dict[str, Sequence[Genre]] = {
            **{mid: movie.genres for mid, movie in watched_movies.items()},
            **{sid: series.genres for sid, series in watched_series.items()},
        }
        now = datetime.now(UTC)
        weighted = (
            (genres_by_id.get(title.media_id, ()), _weight_for(title, now)) for title in history
        )
        return rank_genres(weighted, top_n=_TOP_GENRES)

    @staticmethod
    async def _pick_movies(
        uow: MediaUnitOfWork,
        limit: int,
        allowed: Sequence[LibraryId],
        genres: Sequence[Genre],
        exclude_ids: Sequence[MovieId],
    ) -> tuple[list[Movie], list[Movie]]:
        """Draw ``limit`` unseen movies: genre matches first, then any.

        Returns ``(matched, backfill)``. When there is no taste profile
        (``genres`` empty) everything lands in ``matched`` — there is
        nothing to prefer, so a random unseen draw *is* the recommendation.
        """
        matched = list(
            await uow.movies.find_random(
                limit,
                with_backdrop=True,
                allowed_library_ids=allowed,
                genres=list(genres),
                exclude_ids=list(exclude_ids),
            )
        )
        missing = limit - len(matched)
        if not genres or missing <= 0:
            return matched, []

        already = [*exclude_ids, *(m.id for m in matched if m.id is not None)]
        backfill = list(
            await uow.movies.find_random(
                missing,
                with_backdrop=True,
                allowed_library_ids=allowed,
                genres=[],
                exclude_ids=already,
            )
        )
        return matched, backfill

    @staticmethod
    async def _pick_series(
        uow: MediaUnitOfWork,
        limit: int,
        allowed: Sequence[LibraryId],
        genres: Sequence[Genre],
        exclude_ids: Sequence[SeriesId],
    ) -> tuple[list[Series], list[Series]]:
        """Series twin of ``_pick_movies`` — same two-step draw."""
        matched = list(
            await uow.series.find_random(
                limit,
                with_backdrop=True,
                allowed_library_ids=allowed,
                genres=list(genres),
                exclude_ids=list(exclude_ids),
            )
        )
        missing = limit - len(matched)
        if not genres or missing <= 0:
            return matched, []

        already = [*exclude_ids, *(s.id for s in matched if s.id is not None)]
        backfill = list(
            await uow.series.find_random(
                missing,
                with_backdrop=True,
                allowed_library_ids=allowed,
                genres=[],
                exclude_ids=already,
            )
        )
        return matched, backfill

    @staticmethod
    def _movie_to_output(
        movie: Movie, lang: str, taste: Sequence[Genre] = ()
    ) -> FeaturedItemOutput:
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
            matched_genres=matched_genres(movie.genres, movie.get_genres(lang), taste),
        )

    @staticmethod
    def _series_to_output(
        series: Series, lang: str, taste: Sequence[Genre] = ()
    ) -> FeaturedItemOutput:
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
            matched_genres=matched_genres(series.genres, series.get_genres(lang), taste),
        )


def _weight_for(title: WatchedTitle, now: datetime) -> float:
    base = _COMPLETED_WEIGHT if title.status == "completed" else _IN_PROGRESS_WEIGHT
    return base * recency_factor(title.last_watched_at, now)


def recency_factor(
    last_watched_at: datetime,
    now: datetime,
    *,
    half_life_days: float = _RECENCY_HALF_LIFE_DAYS,
) -> float:
    """Exponential decay in ``(0, 1]``: ``1.0`` now, ``0.5`` one half-life ago.

    A naive (tz-less) ``last_watched_at`` is treated as UTC. Timestamps
    in the future clamp to ``1.0`` rather than inflating the weight.

    Example:
        >>> from datetime import UTC, datetime, timedelta
        >>> now = datetime(2026, 1, 31, tzinfo=UTC)
        >>> recency_factor(now - timedelta(days=30), now)
        0.5
    """
    if last_watched_at.tzinfo is None:
        last_watched_at = last_watched_at.replace(tzinfo=UTC)
    age_days = max((now - last_watched_at).total_seconds(), 0.0) / 86_400
    return float(0.5 ** (age_days / half_life_days))


def rank_genres(
    weighted_genres: Iterable[tuple[Sequence[Genre], float]],
    *,
    top_n: int,
) -> list[Genre]:
    """Rank genres by weighted frequency and keep the ``top_n`` most common.

    Each input pair is ``(genres of one watched title, weight)``. A
    genre's score is the sum of the weights of the titles carrying it.
    Ties keep first-seen order, so with history sorted most-recent-first
    the more recently watched genre wins.

    Example:
        >>> rank_genres(
        ...     [([Genre("Action"), Genre("Sci-Fi")], 2), ([Genre("Action")], 1)],
        ...     top_n=1,
        ... )
        [Genre(value='Action')]
    """
    scores: dict[Genre, float] = {}
    for genres, weight in weighted_genres:
        for genre in genres:
            scores[genre] = scores.get(genre, 0.0) + weight
    # ``sorted`` is stable, so equal scores keep insertion (first-seen) order.
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [genre for genre, _ in ranked[:top_n]]


def matched_genres(
    canonical: Sequence[Genre],
    localized: Sequence[str],
    taste: Sequence[Genre],
) -> list[str]:
    """Localized names of the title's genres that are in the viewer's taste.

    ``localized`` is what ``Entity.get_genres(lang)`` returns — parallel
    to ``canonical`` when a translation exists (ADR-023), or the canonical
    names themselves when it doesn't. Falls back to the canonical name
    whenever the lists don't line up.
    """
    if not taste:
        return []
    wanted = set(taste)
    return [
        localized[i] if i < len(localized) else genre.value
        for i, genre in enumerate(canonical)
        if genre in wanted
    ]


__all__ = ["GetFeaturedMediaUseCase", "matched_genres", "rank_genres", "recency_factor"]

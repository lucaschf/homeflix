"""Every catalog read that accepts a ``policy`` must actually apply it (ADR-035 §7).

``test_visibility_projection.py`` holds ``visibility_conditions`` to
``ViewingPolicy.permits()``, and the architecture test forbids a
visibility predicate written outside that helper. Neither notices a
repository method that takes ``policy`` and never splats the helper into
its query: the signature type-checks, the unit tests mock the
repository, and the method quietly serves every library. This module
closes that gap by running each gated read against real rows in two
libraries under three policies:

- ``None`` — the internal, ungated path (scanner, jobs, ``save`` reload)
  sees both libraries;
- an empty ACL — deny-all, so nothing comes back (fail-closed);
- an ACL naming one library — only that library's titles come back.

Each method returns a different shape (an entity, a page, a dict keyed
by id or TMDB id, genre rows with no id at all), so every entry in
``_GATED_READS`` carries a small reader that normalizes its result to a
set of external ids.

The catalog is seeded over ``fts_session_factory`` so ``search``, which
reads the ``movies_fts`` / ``series_fts`` virtual tables that
``Base.metadata.create_all`` does not build, sits in ``_GATED_READS``
beside every other gated read.
"""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.repositories import GenreRow
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    MediaFile,
    MovieId,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    TmdbId,
    Year,
)
from src.modules.media.domain.value_objects.cast_member import CastMember
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.shared_kernel.content_policy import ViewingPolicy

_LIBRARY_A = "lib_gatealpha001"
_LIBRARY_B = "lib_gatebravo001"
_LIBRARIES = (_LIBRARY_A, _LIBRARY_B)

#: Titles seeded per media kind per library.
_TITLES_PER_LIBRARY = 2

#: Larger than anything seeded, so no page or random draw truncates.
_WIDE_LIMIT = 50

#: Every seeded title carries this genre and this cast member, so the
#: genre and actor listings reach all of them.
_SHARED_GENRE = Genre("Drama")
_SHARED_ACTOR = "Gate Keeper"

#: Every seeded title starts with this word, so ``search`` reaches all of them.
_SHARED_TITLE_WORD = "Gate"

_MARKER_PREFIX = "marker-"


def _marker_genre(external_id: str) -> Genre:
    """Name a title through a genre, for reads that project no id.

    ``GenreRow`` carries only genre lists, so each seeded title is also
    tagged with a genre spelling its own external id.
    """
    return Genre(f"{_MARKER_PREFIX}{external_id}")


@dataclass(frozen=True)
class _Seeded:
    """What the fixture wrote, grouped by library.

    Attributes:
        movies: Seeded movies keyed by ``library_id``.
        series: Seeded series keyed by ``library_id``.
    """

    movies: dict[str, list[Movie]]
    series: dict[str, list[Series]]

    def all_movies(self) -> list[Movie]:
        """Every seeded movie, across both libraries."""
        return [movie for library in _LIBRARIES for movie in self.movies[library]]

    def all_series(self) -> list[Series]:
        """Every seeded series, across both libraries."""
        return [series for library in _LIBRARIES for series in self.series[library]]


def _movie(library_id: str, index: int, tmdb_id: int) -> Movie:
    movie_id = MovieId.generate()
    return Movie(
        library_id=library_id,
        id=movie_id,
        title=Title(f"Gate Movie {library_id} {index}"),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{library_id}/movies/{index}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        genres=[_SHARED_GENRE, _marker_genre(str(movie_id))],
        cast=[CastMember(name=_SHARED_ACTOR)],
        tmdb_id=TmdbId(tmdb_id),
    )


def _series(library_id: str, index: int, tmdb_id: int) -> Series:
    series_id = SeriesId.generate()
    episode = Episode(
        id=EpisodeId.generate(),
        series_id=series_id,
        season_number=1,
        episode_number=1,
        title=Title("Pilot"),
        duration=Duration(2700),
        files=[
            MediaFile(
                file_path=FilePath(f"/{library_id}/series/{index}/s01e01.mkv"),
                file_size=500_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
    )
    season = Season(
        id=SeasonId.generate(),
        series_id=series_id,
        season_number=1,
        title=Title("Season 1"),
        episodes=[episode],
    )
    return Series(
        library_id=library_id,
        id=series_id,
        title=Title(f"Gate Series {library_id} {index}"),
        start_year=Year(2020),
        seasons=[season],
        genres=[_SHARED_GENRE, _marker_genre(str(series_id))],
        cast=[CastMember(name=_SHARED_ACTOR)],
        tmdb_id=TmdbId(tmdb_id),
    )


@pytest.fixture
async def seeded(fts_session_factory: async_sessionmaker[AsyncSession]) -> _Seeded:
    """Write the same catalog shape into two libraries and commit it."""
    movies: dict[str, list[Movie]] = {library: [] for library in _LIBRARIES}
    series: dict[str, list[Series]] = {library: [] for library in _LIBRARIES}
    tmdb_id = 1000

    async with fts_session_factory() as session:
        movie_repo = SQLAlchemyMovieRepository(session)
        series_repo = SQLAlchemySeriesRepository(session)
        for library in _LIBRARIES:
            for index in range(_TITLES_PER_LIBRARY):
                tmdb_id += 1
                movies[library].append(await movie_repo.save(_movie(library, index, tmdb_id)))
                tmdb_id += 1
                series[library].append(await series_repo.save(_series(library, index, tmdb_id)))
        await session.commit()

    return _Seeded(movies=movies, series=series)


# ── Readers: one per gated method, each normalizing to external ids ──

type _Reader = Callable[[AsyncSession, _Seeded, ViewingPolicy | None], Awaitable[set[str]]]


def _ids_from_genre_rows(rows: Sequence[GenreRow]) -> set[str]:
    """Recover the external ids from the marker genres of ``GenreRow``s."""
    return {
        genre.removeprefix(_MARKER_PREFIX)
        for row in rows
        for genre in row.canonical_genres
        if genre.startswith(_MARKER_PREFIX)
    }


async def _movies_find_by_id(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    # Single-result lookup: one call cannot return both libraries, so
    # it is asked once per seeded title and the hits are collected.
    repo = SQLAlchemyMovieRepository(session)
    found: set[str] = set()
    for movie in seeded.all_movies():
        assert movie.id is not None
        hit = await repo.find_by_id(movie.id, policy=policy)
        if hit is not None:
            found.add(str(hit.id))
    return found


async def _movies_list_paginated(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    page = await repo.list_paginated(cursor=None, limit=_WIDE_LIMIT, policy=policy)
    return {str(movie.id) for movie in page.items}


async def _movies_list_recently_added(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    return {str(m.id) for m in await repo.list_recently_added(_WIDE_LIMIT, policy=policy)}


async def _movies_list_genre_rows(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    return _ids_from_genre_rows(await repo.list_genre_rows("en", policy=policy))


async def _movies_list_paginated_by_genre(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    page = await repo.list_paginated_by_genre(
        _SHARED_GENRE, cursor=None, limit=_WIDE_LIMIT, policy=policy
    )
    return {str(movie.id) for movie in page.items}


async def _movies_list_paginated_by_cast_member(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    page = await repo.list_paginated_by_cast_member(
        _SHARED_ACTOR, cursor=None, limit=_WIDE_LIMIT, policy=policy
    )
    return {str(movie.id) for movie in page.items}


async def _movies_find_random(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    return {str(m.id) for m in await repo.find_random(_WIDE_LIMIT, policy=policy)}


async def _movies_find_by_ids(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    ids = [movie.id for movie in seeded.all_movies() if movie.id is not None]
    return set(await repo.find_by_ids(ids, policy=policy))


async def _movies_find_by_tmdb_ids(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    tmdb_ids = [m.tmdb_id.value for m in seeded.all_movies() if m.tmdb_id is not None]
    found = await repo.find_by_tmdb_ids(tmdb_ids, policy=policy)
    return {str(movie.id) for movie in found.values()}


async def _movies_search(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemyMovieRepository(session)
    hits = await repo.search(_SHARED_TITLE_WORD, limit=_WIDE_LIMIT, policy=policy)
    return {str(movie.id) for movie, _rank in hits}


async def _series_find_by_id(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    # Single-result lookup — asked once per seeded title, as for movies.
    repo = SQLAlchemySeriesRepository(session)
    found: set[str] = set()
    for series in seeded.all_series():
        assert series.id is not None
        hit = await repo.find_by_id(series.id, policy=policy)
        if hit is not None:
            found.add(str(hit.id))
    return found


async def _series_list_paginated(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    page = await repo.list_paginated(cursor=None, limit=_WIDE_LIMIT, policy=policy)
    return {str(series.id) for series in page.items}


async def _series_list_recently_added(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    return {str(s.id) for s in await repo.list_recently_added(_WIDE_LIMIT, policy=policy)}


async def _series_list_genre_rows(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    return _ids_from_genre_rows(await repo.list_genre_rows("en", policy=policy))


async def _series_list_paginated_by_genre(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    page = await repo.list_paginated_by_genre(
        _SHARED_GENRE, cursor=None, limit=_WIDE_LIMIT, policy=policy
    )
    return {str(series.id) for series in page.items}


async def _series_find_random(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    return {str(s.id) for s in await repo.find_random(_WIDE_LIMIT, policy=policy)}


async def _series_find_by_title(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    # Single-result lookup — every seeded title is distinct, so each
    # call can match at most one row.
    repo = SQLAlchemySeriesRepository(session)
    found: set[str] = set()
    for series in seeded.all_series():
        hit = await repo.find_by_title(series.title, policy=policy)
        if hit is not None:
            found.add(str(hit.id))
    return found


async def _series_find_by_ids(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    ids = [series.id for series in seeded.all_series() if series.id is not None]
    return set(await repo.find_by_ids(ids, policy=policy))


async def _series_find_by_tmdb_ids(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    tmdb_ids = [s.tmdb_id.value for s in seeded.all_series() if s.tmdb_id is not None]
    found = await repo.find_by_tmdb_ids(tmdb_ids, policy=policy)
    return {str(series.id) for series in found.values()}


async def _series_find_by_episode_id(
    session: AsyncSession, seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    # Single-result lookup keyed by an episode — asked once per seeded
    # series through its only episode.
    repo = SQLAlchemySeriesRepository(session)
    found: set[str] = set()
    for series in seeded.all_series():
        episode_id = series.seasons[0].episodes[0].id
        assert episode_id is not None
        hit = await repo.find_by_episode_id(episode_id, policy=policy)
        if hit is not None:
            found.add(str(hit.id))
    return found


async def _series_search(
    session: AsyncSession, _seeded: _Seeded, policy: ViewingPolicy | None
) -> set[str]:
    repo = SQLAlchemySeriesRepository(session)
    hits = await repo.search(_SHARED_TITLE_WORD, limit=_WIDE_LIMIT, policy=policy)
    return {str(series.id) for series, _rank in hits}


@dataclass(frozen=True)
class _GatedRead:
    """One repository method that accepts a ``policy``.

    Attributes:
        name: ``<repository>.<method>``, used as the test id and in
            failure messages.
        media: Which seeded titles the method can return.
        read: Calls the method and normalizes its result to external ids.
    """

    name: str
    media: Literal["movie", "series"]
    read: _Reader


_GATED_READS: list[_GatedRead] = [
    _GatedRead("movies.find_by_id", "movie", _movies_find_by_id),
    _GatedRead("movies.list_paginated", "movie", _movies_list_paginated),
    _GatedRead("movies.list_recently_added", "movie", _movies_list_recently_added),
    _GatedRead("movies.list_genre_rows", "movie", _movies_list_genre_rows),
    _GatedRead("movies.list_paginated_by_genre", "movie", _movies_list_paginated_by_genre),
    _GatedRead(
        "movies.list_paginated_by_cast_member", "movie", _movies_list_paginated_by_cast_member
    ),
    _GatedRead("movies.find_random", "movie", _movies_find_random),
    _GatedRead("movies.find_by_ids", "movie", _movies_find_by_ids),
    _GatedRead("movies.find_by_tmdb_ids", "movie", _movies_find_by_tmdb_ids),
    _GatedRead("movies.search", "movie", _movies_search),
    _GatedRead("series.find_by_id", "series", _series_find_by_id),
    _GatedRead("series.list_paginated", "series", _series_list_paginated),
    _GatedRead("series.list_recently_added", "series", _series_list_recently_added),
    _GatedRead("series.list_genre_rows", "series", _series_list_genre_rows),
    _GatedRead("series.list_paginated_by_genre", "series", _series_list_paginated_by_genre),
    _GatedRead("series.find_random", "series", _series_find_random),
    _GatedRead("series.find_by_title", "series", _series_find_by_title),
    _GatedRead("series.find_by_ids", "series", _series_find_by_ids),
    _GatedRead("series.find_by_tmdb_ids", "series", _series_find_by_tmdb_ids),
    _GatedRead("series.find_by_episode_id", "series", _series_find_by_episode_id),
    _GatedRead("series.search", "series", _series_search),
]

#: ``(case, policy, libraries whose titles must come back)``.
_CASES: list[tuple[str, ViewingPolicy | None, tuple[str, ...]]] = [
    ("ungated", None, _LIBRARIES),
    ("deny_all", ViewingPolicy(allowed_library_ids=[]), ()),
    ("library_a_only", ViewingPolicy(allowed_library_ids=[_LIBRARY_A]), (_LIBRARY_A,)),
]


def _expected_ids(seeded: _Seeded, media: str, libraries: tuple[str, ...]) -> set[str]:
    """External ids of the seeded ``media`` titles that live in ``libraries``."""
    if media == "movie":
        return {str(movie.id) for library in libraries for movie in seeded.movies[library]}
    return {str(series.id) for library in libraries for series in seeded.series[library]}


@pytest.mark.integration
class TestEveryGatedReadAppliesThePolicy:
    """Fail-closed on an empty ACL, fail-open only when ungated."""

    @pytest.mark.parametrize(
        ("case", "policy", "visible_libraries"), _CASES, ids=[case[0] for case in _CASES]
    )
    @pytest.mark.parametrize("gated_read", _GATED_READS, ids=[read.name for read in _GATED_READS])
    async def test_returns_exactly_the_titles_the_policy_reaches(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        seeded: _Seeded,
        gated_read: _GatedRead,
        case: str,
        policy: ViewingPolicy | None,
        visible_libraries: tuple[str, ...],
    ) -> None:
        expected = _expected_ids(seeded, gated_read.media, visible_libraries)
        # Guard the fixture itself: an empty expectation in the ungated
        # case would let a method that returns nothing pass everywhere.
        if policy is None:
            assert len(expected) == _TITLES_PER_LIBRARY * len(_LIBRARIES)

        async with fts_session_factory() as session:
            returned = await gated_read.read(session, seeded, policy)

        assert returned == expected, (
            f"{gated_read.name} [{case}] returned the wrong titles: "
            f"leaked {sorted(returned - expected)}, missing {sorted(expected - returned)}"
        )

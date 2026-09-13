"""``search`` on both catalog repositories, over real FTS5.

``search`` is one query: the FTS5 match (with its coalesced ``bm25()``
score) joined to the catalog table, with the genre and year filters, the
soft-delete exclusion and the viewing policy in the ``WHERE`` clause,
ordered by rank, title and id, and cut by ``LIMIT`` only after all of
them. The tests here pin:

- relevance order, and the tiebreak on stored title by code point, then
  insertion order — equal ranks are common, not a corner case: in the
  application database ``bm25()`` comes back NULL for any query matching
  more documents than the index's drifted counter admits, and every hit
  is coalesced to ``0.0``, so the tiebreak alone picks the page;
- the genre and year filters, soft-delete exclusion and localized titles;
- shallow entities: no file variants, no seasons, one row per series;
- the maturity limit, which hides titles above it and every unclassified
  title.

``TestSearchFillsThePageAfterEveryCut`` guards against the regression of
cutting a ranked top-N before filtering: whether the policy's library
ACL, the genre or the year range hides the best-ranked hits, the page
still fills with the visible titles, in rank order. Per-policy reach
(ungated, deny-all, one library) lives with the other gated reads in
``test_repository_visibility_gates.py``.

Rows are written through the repositories, so the migration's triggers
index them exactly as they index the application database.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import cycle
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.domain.entities import Episode, Movie, Season, Series
from src.modules.media.domain.value_objects import (
    Duration,
    EpisodeId,
    FilePath,
    Genre,
    LocalizedMetadata,
    MediaFile,
    Resolution,
    SeasonId,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import AgeRating, Certification, ContentRating, RatingSystem

_LIBRARY_A = "lib_searchalph01"
_LIBRARY_B = "lib_searchbrav01"

type _CatalogEntity = Movie | Series
type _Hits = list[tuple[Any, float]]


def _build_movie(
    title: str,
    *,
    library_id: str = _LIBRARY_A,
    year: int = 2000,
    genres: Sequence[str] = (),
    localized: dict[str, dict[str, Any]] | None = None,
    certification: Certification | None = None,
) -> Movie:
    return Movie(
        library_id=library_id,
        title=Title(title),
        year=Year(year),
        duration=Duration(7200),
        genres=[Genre(genre) for genre in genres],
        localized=LocalizedMetadata.from_serializable(localized),
        certification=certification,
    )


def _build_series(
    title: str,
    *,
    library_id: str = _LIBRARY_A,
    year: int = 2000,
    genres: Sequence[str] = (),
    localized: dict[str, dict[str, Any]] | None = None,
    certification: Certification | None = None,
) -> Series:
    return Series(
        library_id=library_id,
        title=Title(title),
        start_year=Year(year),
        genres=[Genre(genre) for genre in genres],
        localized=LocalizedMetadata.from_serializable(localized),
        certification=certification,
    )


@dataclass(frozen=True)
class _Catalog:
    """One searchable catalog and how to write titles into it.

    Attributes:
        name: Test id.
        table: Base table name; its FTS5 index is ``<table>_fts``.
        repository: Builds the repository over a session.
        build: Builds an unsaved entity from a title and optional fields.
    """

    name: str
    table: str
    repository: Callable[[AsyncSession], Any]
    build: Callable[..., _CatalogEntity]


_MOVIES = _Catalog("movies", "movies", SQLAlchemyMovieRepository, _build_movie)
_SERIES = _Catalog("series", "series", SQLAlchemySeriesRepository, _build_series)


@pytest.fixture(params=[_MOVIES, _SERIES], ids=lambda catalog: catalog.name)
def catalog(request: pytest.FixtureRequest) -> _Catalog:
    """Run each characterization against both repositories."""
    return request.param


async def _save_all(
    factory: async_sessionmaker[AsyncSession],
    catalog: _Catalog,
    entities: Sequence[_CatalogEntity],
) -> list[Any]:
    """Save ``entities`` in order and commit; return them with their ids."""
    async with factory() as session:
        repository = catalog.repository(session)
        saved = [await repository.save(entity) for entity in entities]
        await session.commit()
    return saved


async def _search(
    factory: async_sessionmaker[AsyncSession],
    catalog: _Catalog,
    query: str,
    **kwargs: Any,
) -> _Hits:
    async with factory() as session:
        return await catalog.repository(session).search(query, **kwargs)


def _titles(hits: _Hits) -> list[str]:
    return [entity.title.value for entity, _rank in hits]


async def _row_id(session: AsyncSession, catalog: _Catalog, external_id: object) -> int:
    """Return the integer primary key, which is also the row's FTS5 rowid."""
    result = await session.execute(
        text(f"SELECT id FROM {catalog.table} WHERE external_id = :external_id"),
        {"external_id": str(external_id)},
    )
    return int(result.scalar_one())


@pytest.mark.integration
class TestSearchOrdering:
    """Most relevant first; equal ranks ordered by title, then insertion."""

    async def test_orders_hits_from_most_to_least_relevant(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        # Seeded in neither relevance nor title order. The fillers keep
        # the term in under half the documents, so ``bm25()`` scores it
        # with a real IDF instead of the clamped minimum.
        await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("Maltese Falcon Story Of"),
                catalog.build("Zulu Falcon"),
                catalog.build("Falcon"),
                catalog.build("Falcon Rising Again"),
                catalog.build("The Falcon Falcon"),
                *(catalog.build(f"Unrelated {name}") for name in ("A", "B", "C", "D", "E", "F")),
            ],
        )

        hits = await _search(fts_session_factory, catalog, "falcon")

        ranks = [rank for _entity, rank in hits]
        assert len(set(ranks)) == len(ranks), "fixture must give every hit a distinct rank"
        assert ranks == sorted(ranks)
        assert _titles(hits) == [
            "Falcon",
            "The Falcon Falcon",
            "Zulu Falcon",
            "Falcon Rising Again",
            "Maltese Falcon Story Of",
        ]

    async def test_breaks_rank_ties_by_title_code_point_then_insertion_order(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        """No case folding, no accent folding: ``"A" < "a" < "Á"``.

        The tokenizer (``unicode61 remove_diacritics 2``) folds all four
        titles to the same tokens, so they tie on rank. The tiebreak is
        on the stored title as-is, which is what SQLite's default
        ``BINARY`` collation also compares — a rewrite that sorts with
        ``NOCASE`` or ``lower()`` reorders this page. The two identical
        titles keep insertion order.
        """
        accented, first_upper, lower, second_upper = await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("Álpha Tie"),
                catalog.build("Alpha Tie"),
                catalog.build("alpha Tie"),
                catalog.build("Alpha Tie"),
            ],
        )

        hits = await _search(fts_session_factory, catalog, "tie")

        assert len({rank for _entity, rank in hits}) == 1, "fixture must tie every hit"
        assert [str(entity.id) for entity, _rank in hits] == [
            str(first_upper.id),
            str(second_upper.id),
            str(lower.id),
            str(accented.id),
        ]

    async def test_scores_unrankable_hits_as_zero_and_orders_them_by_title(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        """Reproduces the NULL ``bm25()`` seen in the application database.

        There, every hit of a broad prefix (``a*``: 644 of 644 movies)
        scores NULL. The cause is the index's document counter drifting
        below the real count: any UPDATE to a row that is already
        soft-deleted makes the sync trigger issue a second ``'delete'``
        for it (the copy measured holds ``nDoc = 639`` for 644 indexed
        movies). A query that matches more documents than the counter
        admits gets a NaN IDF, which SQLite returns as NULL. Here the
        drift of one document comes from an explicit FTS5 ``'delete'``
        command for a row the soft-delete already removed, so the test
        does not depend on the trigger defect surviving.
        """
        *_nimbus, decoy = await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("Nimbus Two"),
                catalog.build("Nimbus One"),
                catalog.build("Nimbus Three"),
                catalog.build("Decoy"),
            ],
        )
        fts_table = f"{catalog.table}_fts"
        async with fts_session_factory() as session:
            await catalog.repository(session).delete(decoy.id)
            await session.execute(
                text(
                    f"INSERT INTO {fts_table}({fts_table}, rowid, title) "
                    "VALUES ('delete', :rowid, 'Decoy')"
                ),
                {"rowid": await _row_id(session, catalog, decoy.id)},
            )
            await session.commit()
            raw_scores = (
                await session.execute(
                    text(f"SELECT bm25({fts_table}) FROM {fts_table} WHERE {fts_table} MATCH :q"),
                    {"q": "nimbus*"},
                )
            ).scalars()
            assert list(raw_scores) == [None, None, None], "fixture must make bm25() NULL"

        hits = await _search(fts_session_factory, catalog, "nimbus")

        assert [(entity.title.value, rank) for entity, rank in hits] == [
            ("Nimbus One", 0.0),
            ("Nimbus Three", 0.0),
            ("Nimbus Two", 0.0),
        ]

    async def test_returns_the_first_limit_hits_of_the_ordering(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        # Seven tied hits — more than ``limit * 2`` — and the title that
        # sorts first is inserted last, so it is the one a rank-only cut
        # to a top-N before the title tiebreak would drop.
        await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build(f"Echo {name}")
                for name in ("Kilo", "Bravo", "Lima", "Juliet", "Delta", "Golf", "Alpha")
            ],
        )

        hits = await _search(fts_session_factory, catalog, "echo", limit=3)

        assert len({rank for _entity, rank in hits}) == 1, "fixture must tie every hit"
        assert _titles(hits) == ["Echo Alpha", "Echo Bravo", "Echo Delta"]


@pytest.mark.integration
class TestSearchFilters:
    """What narrows the hits besides the text match."""

    async def test_genre_matches_one_whole_entry_of_the_genre_list(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("Harbor Lights", genres=["Drama", "Horror"]),
                catalog.build("Harbor Nights", genres=["Comedy"]),
                catalog.build("Harbor Fights", genres=["Horror Comedy"]),
            ],
        )

        hits = await _search(fts_session_factory, catalog, "harbor", genre="Horror")

        assert _titles(hits) == ["Harbor Lights"]

    @pytest.mark.parametrize(
        ("year_min", "year_max", "expected"),
        [
            (2000, None, {"Orbit 2000", "Orbit 2010", "Orbit 2011"}),
            (None, 2010, {"Orbit 1999", "Orbit 2000", "Orbit 2010"}),
            (2000, 2010, {"Orbit 2000", "Orbit 2010"}),
        ],
        ids=["min_only", "max_only", "both_inclusive"],
    )
    async def test_year_bounds_are_inclusive(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        catalog: _Catalog,
        year_min: int | None,
        year_max: int | None,
        expected: set[str],
    ) -> None:
        await _save_all(
            fts_session_factory,
            catalog,
            [catalog.build(f"Orbit {year}", year=year) for year in (1999, 2000, 2010, 2011)],
        )

        hits = await _search(
            fts_session_factory, catalog, "orbit", year_min=year_min, year_max=year_max
        )

        assert set(_titles(hits)) == expected

    async def test_excludes_soft_deleted_titles(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        """Excluded by the query itself, not only by the index trigger.

        The soft-delete trigger already drops the row from the index, so
        the deleted row is written back into it by hand: only the
        ``deleted_at`` filter in ``search`` can keep it out of the page.
        """
        _visible, deleted = await _save_all(
            fts_session_factory,
            catalog,
            [catalog.build("Ghost Visible"), catalog.build("Ghost Deleted")],
        )
        fts_table = f"{catalog.table}_fts"
        async with fts_session_factory() as session:
            assert await catalog.repository(session).delete(deleted.id)
            deleted_row_id = await _row_id(session, catalog, deleted.id)
            await session.execute(
                text(f"INSERT INTO {fts_table}(rowid, title) VALUES (:rowid, 'Ghost Deleted')"),
                {"rowid": deleted_row_id},
            )
            await session.commit()
            matched = (
                await session.execute(
                    text(f"SELECT rowid FROM {fts_table} WHERE {fts_table} MATCH :q"),
                    {"q": "ghost*"},
                )
            ).scalars()
            assert deleted_row_id in set(matched), "fixture must leave the deleted row indexed"

        hits = await _search(fts_session_factory, catalog, "ghost")

        assert _titles(hits) == ["Ghost Visible"]

    @pytest.mark.parametrize("query", ["espião", "espiao"])
    async def test_matches_a_localized_title_with_or_without_accents(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        catalog: _Catalog,
        query: str,
    ) -> None:
        await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("The Spy", localized={"pt-BR": {"title": "O Espião"}}),
                catalog.build("The Spider"),
            ],
        )

        hits = await _search(fts_session_factory, catalog, query)

        assert _titles(hits) == ["The Spy"]

    @pytest.mark.parametrize(
        "query", ["   ", '"-+', "zzzz"], ids=["blank", "operators", "no_match"]
    )
    async def test_returns_nothing_without_a_usable_match(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        catalog: _Catalog,
        query: str,
    ) -> None:
        await _save_all(fts_session_factory, catalog, [catalog.build("Anything")])

        assert await _search(fts_session_factory, catalog, query) == []


@pytest.mark.integration
class TestSearchReturnsShallowEntities:
    """Hits carry root columns only; children are never mapped."""

    async def test_movie_hits_carry_no_file_variants(
        self, fts_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        movie = _build_movie("Reel Deep").with_updates(
            files=[
                MediaFile(
                    file_path=FilePath("/movies/reel-deep.mkv"),
                    file_size=1_000_000_000,
                    resolution=Resolution("1080p"),
                    is_primary=True,
                )
            ]
        )
        (saved,) = await _save_all(fts_session_factory, _MOVIES, [movie])
        assert len(saved.files) == 1, "fixture must persist a file variant"

        hits = await _search(fts_session_factory, _MOVIES, "reel")

        assert [(str(entity.id), entity.files) for entity, _rank in hits] == [(str(saved.id), [])]

    async def test_series_hits_are_unique_and_carry_no_seasons(
        self, fts_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        series_id = SeriesId.generate()
        seasons = [
            Season(
                id=SeasonId.generate(),
                series_id=series_id,
                season_number=season_number,
                title=Title(f"Season {season_number}"),
                episodes=[
                    Episode(
                        id=EpisodeId.generate(),
                        series_id=series_id,
                        season_number=season_number,
                        episode_number=episode_number,
                        title=Title(f"Episode {episode_number}"),
                        duration=Duration(2700),
                    )
                    for episode_number in (1, 2)
                ],
            )
            for season_number in (1, 2)
        ]
        series = _build_series("Longrunner").with_updates(id=series_id, seasons=seasons)
        (saved,) = await _save_all(fts_session_factory, _SERIES, [series])
        assert len(saved.seasons) == 2, "fixture must persist the seasons"

        hits = await _search(fts_session_factory, _SERIES, "longrunner")

        assert [(str(entity.id), entity.seasons) for entity, _rank in hits] == [(str(saved.id), [])]


# ── The maturity axis ────────────────────────────────────────────────


def _dejus(label: str, age: int) -> Certification:
    return Certification(
        system=RatingSystem.BR_DEJUS, label=ContentRating(label), minimum_age=AgeRating(age)
    )


@pytest.mark.integration
class TestSearchUnderAMaturityLimit:
    """A limited profile finds only titles classified at or below its limit."""

    async def test_returns_only_titles_classified_at_or_below_the_limit(
        self, fts_session_factory: async_sessionmaker[AsyncSession], catalog: _Catalog
    ) -> None:
        """Below the adult rung, a title without a determinable age never shows.

        Every title ties on rank and the default limit holds all of them,
        so only the policy narrows the page, which comes back in title
        order. The one title in another library checks that the maturity
        axis adds to the library ACL instead of replacing it.
        """
        await _save_all(
            fts_session_factory,
            catalog,
            [
                catalog.build("Rated Eighteen", certification=_dejus("18", 18)),
                catalog.build("Rated Twelve", certification=_dejus("12", 12)),
                catalog.build("Rated Fourteen", certification=_dejus("14", 14)),
                catalog.build("Rated Free", certification=_dejus("L", 0)),
                catalog.build(
                    "Rated Unknown",
                    certification=Certification.undetermined(ContentRating("NR")),
                ),
                catalog.build("Rated Missing"),
                catalog.build("Rated Ten", certification=_dejus("10", 10)),
                catalog.build(
                    "Rated Elsewhere", library_id=_LIBRARY_B, certification=_dejus("10", 10)
                ),
            ],
        )

        hits = await _search(
            fts_session_factory,
            catalog,
            "rated",
            policy=ViewingPolicy(allowed_library_ids=[_LIBRARY_A], maturity_limit=AgeRating(12)),
        )

        assert _titles(hits) == ["Rated Free", "Rated Ten", "Rated Twelve"]


# ── Pages are cut after filtering ────────────────────────────────────

_PAGE_LIMIT = 3


@dataclass(frozen=True)
class _Cut:
    """One way the search can hide the best-ranked hits.

    Attributes:
        name: Test id.
        visible: Build fields of a title the search keeps.
        hidden: Build fields of the titles the search drops, used in turn.
        search: The ``search`` arguments that apply the cut.
    """

    name: str
    visible: dict[str, Any]
    hidden: tuple[dict[str, Any], ...]
    search: dict[str, Any]


_ALLOWED_LIBRARY = _LIBRARY_B
_DENIED_LIBRARY = _LIBRARY_A

_CUTS = [
    _Cut(
        "library_acl",
        visible={"library_id": _ALLOWED_LIBRARY},
        hidden=({"library_id": _DENIED_LIBRARY},),
        search={"policy": ViewingPolicy(allowed_library_ids=[_ALLOWED_LIBRARY])},
    ),
    # One-token genres on both sides, so the genre column adds the same
    # length to every document and leaves the title-driven ranks as they are.
    _Cut(
        "genre",
        visible={"genres": ["Western"]},
        hidden=({"genres": ["Musical"]},),
        search={"genre": "Western"},
    ),
    _Cut(
        "year",
        visible={"year": 2005},
        hidden=({"year": 1999}, {"year": 2011}),
        search={"year_min": 2000, "year_max": 2010},
    ),
]


@pytest.fixture(params=_CUTS, ids=lambda cut: cut.name)
def cut(request: pytest.FixtureRequest) -> _Cut:
    """Run each page test once per filter that can hide hits."""
    return request.param


def _crowded_catalog(catalog: _Catalog, cut: _Cut) -> list[_CatalogEntity]:
    """Many hits, with the visible titles mostly ranked below the hidden ones.

    Every title matches ``comet`` once, so shorter titles rank higher:

    - ``Comet`` (visible, one token) is the single best hit;
    - five hidden titles of two tokens come next, tied;
    - three visible titles of three tokens come last, tied.

    Among the ``_PAGE_LIMIT * 2`` most relevant hits only ``Comet`` is
    visible, yet four visible titles match — more than a page.
    """
    hidden = cycle(cut.hidden)
    return [
        catalog.build("Comet Oscar Papa", **cut.visible),
        *(
            catalog.build(f"Comet {name}", **next(hidden))
            for name in ("Alpha", "Bravo", "Charlie", "Delta", "Echo")
        ),
        catalog.build("Comet", **cut.visible),
        catalog.build("Comet Kilo Lima", **cut.visible),
        catalog.build("Comet Mike November", **cut.visible),
    ]


_VISIBLE_TITLES = {"Comet", "Comet Kilo Lima", "Comet Mike November", "Comet Oscar Papa"}


@pytest.mark.integration
class TestSearchFillsThePageAfterEveryCut:
    """Filters and the policy narrow the hits before ``LIMIT``, not after."""

    async def test_scenario_leaves_the_visible_titles_a_minority_of_the_ranked_pool(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        catalog: _Catalog,
        cut: _Cut,
    ) -> None:
        """Holds the premise of the page test below.

        A search that cut the ``_PAGE_LIMIT * 2`` best hits before
        filtering would keep a single visible title and serve a short page.
        """
        await _save_all(fts_session_factory, catalog, _crowded_catalog(catalog, cut))
        table, fts_table = catalog.table, f"{catalog.table}_fts"

        async with fts_session_factory() as session:
            pool = (
                await session.execute(
                    text(
                        f"SELECT {table}.title FROM {fts_table} "
                        f"JOIN {table} ON {table}.id = {fts_table}.rowid "
                        f"WHERE {fts_table} MATCH :q "
                        f"ORDER BY bm25({fts_table}) LIMIT :pool"
                    ),
                    {"q": "comet*", "pool": _PAGE_LIMIT * 2},
                )
            ).scalars()

            assert [title in _VISIBLE_TITLES for title in pool] == [True] + [False] * 5

    async def test_fills_the_page_with_visible_titles_in_rank_order(
        self,
        fts_session_factory: async_sessionmaker[AsyncSession],
        catalog: _Catalog,
        cut: _Cut,
    ) -> None:
        await _save_all(fts_session_factory, catalog, _crowded_catalog(catalog, cut))

        hits = await _search(fts_session_factory, catalog, "comet", limit=_PAGE_LIMIT, **cut.search)

        titles = _titles(hits)
        assert len(hits) == _PAGE_LIMIT, f"short page: {titles}"
        assert titles == ["Comet", "Comet Kilo Lima", "Comet Mike November"]

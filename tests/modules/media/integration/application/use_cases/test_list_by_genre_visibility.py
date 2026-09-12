"""Genre browse under a restricted policy, walked page by page (ADR-035 §7).

``ListByGenreUseCase`` merges the movie and series streams in Python and
advances each stream through the repository's positional
``item_cursors``: the cursor at index ``i`` resumes after the ``i``-th
row of that page. That only holds when the visibility filter runs inside
the SQL, before ``LIMIT`` and before the cursors are built. Filtering the
rows afterwards shifts the indexes and re-serves titles on the next page;
filtering after the merge skips them for good. Neither raises, and
neither shows up on page one — so this walks every page with a small
limit, through the real repositories, and checks the whole walk.
"""

import math

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.modules.media.application.dtos.catalog_dtos import ListByGenreInput
from src.modules.media.application.ports.profile_viewing_policy_port import (
    ProfileViewingPolicyPort,
)
from src.modules.media.application.use_cases.list_by_genre import ListByGenreUseCase
from src.modules.media.domain.entities import Movie, Series
from src.modules.media.domain.value_objects import (
    Duration,
    FilePath,
    Genre,
    MediaFile,
    MovieId,
    Resolution,
    SeriesId,
    Title,
    Year,
)
from src.modules.media.infrastructure.persistence.repositories import (
    SQLAlchemyMovieRepository,
    SQLAlchemySeriesRepository,
)
from src.modules.media.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyMediaUnitOfWorkFactory,
)
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

_VISIBLE_LIBRARY = "lib_visible00001"
_HIDDEN_LIBRARY = "lib_hidden000001"
_PROFILE_ID = "prf_test12345678"
_GENRE = "Drama"
_PAGE_SIZE = 2

#: ``(title, library, kind)``, in title order. Hidden titles sit between
#: visible ones in both streams, so a filter that ran after ``LIMIT``
#: would change what each page holds rather than only trim its tail.
_CATALOG: list[tuple[str, str, MediaType]] = [
    ("Alpha", _VISIBLE_LIBRARY, MediaType.MOVIE),
    ("Bravo", _HIDDEN_LIBRARY, MediaType.MOVIE),
    ("Charlie", _VISIBLE_LIBRARY, MediaType.SERIES),
    ("Delta", _HIDDEN_LIBRARY, MediaType.SERIES),
    ("Echo", _VISIBLE_LIBRARY, MediaType.MOVIE),
    ("Foxtrot", _HIDDEN_LIBRARY, MediaType.MOVIE),
    ("Golf", _VISIBLE_LIBRARY, MediaType.SERIES),
    ("Hotel", _HIDDEN_LIBRARY, MediaType.SERIES),
    ("India", _VISIBLE_LIBRARY, MediaType.MOVIE),
    ("Juliet", _HIDDEN_LIBRARY, MediaType.SERIES),
    ("Kilo", _VISIBLE_LIBRARY, MediaType.SERIES),
    ("Lima", _HIDDEN_LIBRARY, MediaType.MOVIE),
    ("Mike", _VISIBLE_LIBRARY, MediaType.MOVIE),
    ("November", _HIDDEN_LIBRARY, MediaType.SERIES),
    ("Oscar", _VISIBLE_LIBRARY, MediaType.SERIES),
    ("Papa", _VISIBLE_LIBRARY, MediaType.MOVIE),
]


class _FixedViewingPolicy(ProfileViewingPolicyPort):
    """Answer every profile with one policy — the Identity adapter is not under test."""

    def __init__(self, policy: ViewingPolicy) -> None:
        self._policy = policy

    async def find_for_profile(self, profile_id: ProfileId) -> ViewingPolicy:
        return self._policy


def _movie(title: str, library_id: str) -> Movie:
    return Movie(
        library_id=library_id,
        id=MovieId.generate(),
        title=Title(title),
        year=Year(2024),
        duration=Duration(7200),
        files=[
            MediaFile(
                file_path=FilePath(f"/{library_id}/{title}.mkv"),
                file_size=1_000_000_000,
                resolution=Resolution("1080p"),
                is_primary=True,
            )
        ],
        genres=[Genre(_GENRE)],
    )


def _series(title: str, library_id: str) -> Series:
    return Series(
        library_id=library_id,
        id=SeriesId.generate(),
        title=Title(title),
        start_year=Year(2020),
        genres=[Genre(_GENRE)],
    )


async def _seed(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, str]:
    """Persist ``_CATALOG`` and return each title's external id by library."""
    library_of: dict[str, str] = {}
    async with session_factory() as session:
        movies = SQLAlchemyMovieRepository(session)
        series = SQLAlchemySeriesRepository(session)
        for title, library_id, kind in _CATALOG:
            if kind is MediaType.MOVIE:
                saved_movie = await movies.save(_movie(title, library_id))
                library_of[str(saved_movie.id)] = library_id
            else:
                saved_series = await series.save(_series(title, library_id))
                library_of[str(saved_series.id)] = library_id
        await session.commit()
    return library_of


@pytest.mark.integration
class TestListByGenreUnderARestrictedPolicy:
    """Every page, not just the first, respects the policy."""

    async def test_walking_every_page_serves_each_eligible_title_exactly_once(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        library_of = await _seed(session_factory)
        eligible = {eid for eid, library in library_of.items() if library == _VISIBLE_LIBRARY}
        hidden = set(library_of) - eligible
        use_case = ListByGenreUseCase(
            uow_factory=SqlAlchemyMediaUnitOfWorkFactory(session_factory),
            profile_viewing_policy=_FixedViewingPolicy(
                ViewingPolicy(allowed_library_ids=[_VISIBLE_LIBRARY])
            ),
        )

        pages: list[list[str]] = []
        cursor: str | None = None
        while True:
            output = await use_case.execute(
                ListByGenreInput(
                    profile_id=_PROFILE_ID,
                    genre=_GENRE,
                    cursor=cursor,
                    limit=_PAGE_SIZE,
                )
            )
            pages.append([item.id for item in output.items])
            if not output.has_more:
                break
            # Bound the walk, so a cursor that stops advancing fails
            # the test instead of hanging it.
            assert len(pages) <= len(_CATALOG), f"pagination did not terminate: {pages}"
            cursor = output.next_cursor

        served = [external_id for page in pages for external_id in page]
        expected_pages = math.ceil(len(eligible) / _PAGE_SIZE)
        assert not hidden & set(served), f"titles outside the policy were served: {pages}"
        assert len(served) == len(set(served)), f"titles were served more than once: {pages}"
        assert set(served) == eligible, f"eligible titles never served: {eligible - set(served)}"
        assert len(pages) == expected_pages, f"expected {expected_pages} pages, got {pages}"

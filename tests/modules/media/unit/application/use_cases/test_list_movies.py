"""Tests for ListMoviesUseCase."""

import pytest

from src.building_blocks.application.pagination import PaginatedResult, Pagination
from src.modules.media.application.dtos import ListMoviesInput, ListMoviesOutput, MovieSummaryOutput
from src.modules.media.application.use_cases import ListMoviesUseCase
from src.modules.media.domain.entities import Movie
from tests.modules.media.unit.conftest import (
    FakeProfileLibraryAccessPort,
    make_media_uow_mock,
    make_profile_library_access,
)

_LIBRARY_ID = "lib_test12345678"
_LIBRARY_ID_OTHER = "lib_otherlibrary"
_PROFILE_ID = "prf_test12345678"


def _make_movie(
    title: str = "Test Movie",
    year: int = 2020,
    *,
    library_id: str = _LIBRARY_ID,
) -> Movie:
    return Movie.create(
        library_id=library_id,
        title=title,
        year=year,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    )


def _page(
    movies: list[Movie],
    *,
    next_cursor: str | None = None,
    has_more: bool = False,
    total_count: int | None = None,
) -> PaginatedResult[Movie]:
    return PaginatedResult(
        items=movies,
        pagination=Pagination(next_cursor=next_cursor, has_more=has_more),
        total_count=total_count,
    )


class TestListMoviesUseCase:
    """Tests for ListMoviesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_first_page(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page(
            [_make_movie("Movie 1"), _make_movie("Movie 2")],
            has_more=False,
        )
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        assert isinstance(result, ListMoviesOutput)
        assert len(result.movies) == 2
        assert result.has_more is False
        assert result.next_cursor is None
        # include_total defaults to False → repo gets include_total=False → total_count is None
        assert result.total_count is None
        mocks.movies.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=False,
            allowed_library_ids=[_LIBRARY_ID],
            library_id=None,
            has_tmdb_id=None,
            needs_enrichment_review=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_convert_movies_to_summaries(self) -> None:
        mocks = make_media_uow_mock()
        movie = _make_movie("Test Movie", 2020).with_genre("Action")
        mocks.movies.list_paginated.return_value = _page([movie])
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        summary = result.movies[0]
        assert isinstance(summary, MovieSummaryOutput)
        assert summary.title == "Test Movie"
        assert summary.year == 2020
        assert summary.duration_formatted == "02:00:00"
        assert summary.resolution == "1080p"
        assert summary.genres == ["Action"]

    @pytest.mark.asyncio
    async def test_should_pass_cursor_and_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page([])
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID, cursor="abc123", limit=15))

        mocks.movies.list_paginated.assert_awaited_once_with(
            cursor="abc123",
            limit=15,
            include_total=False,
            allowed_library_ids=[_LIBRARY_ID],
            library_id=None,
            has_tmdb_id=None,
            needs_enrichment_review=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_propagate_next_cursor_and_has_more(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page(
            [_make_movie("Movie 1")],
            next_cursor="next-token",
            has_more=True,
        )
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        assert result.next_cursor == "next-token"
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_should_return_empty_page_when_no_movies(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page([])
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        assert result.movies == []
        assert result.has_more is False
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_should_request_total_when_include_total_is_true(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page(
            [_make_movie("Movie 1")],
            total_count=42,
        )
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID, include_total=True))

        assert result.total_count == 42
        mocks.movies.list_paginated.assert_awaited_once_with(
            cursor=None,
            limit=20,
            include_total=True,
            allowed_library_ids=[_LIBRARY_ID],
            library_id=None,
            has_tmdb_id=None,
            needs_enrichment_review=None,
            q=None,
        )

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        # Deny-all profile (empty allowed list) → empty result + no UoW.
        # Load-bearing security assertion: an unauthorized profile must
        # NEVER reach the catalog repository.
        mocks = make_media_uow_mock()
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        assert result.movies == []
        assert result.has_more is False
        assert result.next_cursor is None
        # The UoW factory must not be called.
        mocks.factory.assert_not_called()
        mocks.movies.list_paginated.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_zero_total_count_for_deny_all_when_requested(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID, include_total=True))

        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        # Two libraries' worth of items exist on the repo side; the
        # fake port restricts the profile to library A, so only the
        # library-A items must come back. We assert the kwarg the
        # use case passes — the repo is mocked, so the actual filter
        # is exercised in the integration tests; here we pin the
        # contract between use case and repo.
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page(
            [_make_movie("Visible", library_id=_LIBRARY_ID)]
        )
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(ListMoviesInput(profile_id=_PROFILE_ID))

        assert [m.title for m in result.movies] == ["Visible"]
        passed = mocks.movies.list_paginated.await_args.kwargs["allowed_library_ids"]
        assert list(passed) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(passed)

    @pytest.mark.asyncio
    async def test_should_forward_admin_filters_to_repository(self) -> None:
        """``library_id`` / ``has_tmdb_id`` / ``needs_enrichment_review``
        are pass-through filters used by the admin Catalog page. The
        use case mustn't drop them on the floor."""
        mocks = make_media_uow_mock()
        mocks.movies.list_paginated.return_value = _page([])
        use_case = ListMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(
            ListMoviesInput(
                profile_id=_PROFILE_ID,
                library_id="lib_specific00000",
                has_tmdb_id=False,
                needs_enrichment_review=True,
            ),
        )

        kwargs = mocks.movies.list_paginated.await_args.kwargs
        assert kwargs["library_id"] == "lib_specific00000"
        assert kwargs["has_tmdb_id"] is False
        assert kwargs["needs_enrichment_review"] is True

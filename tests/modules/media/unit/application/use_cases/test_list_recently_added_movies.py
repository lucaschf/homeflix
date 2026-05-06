"""Tests for ListRecentlyAddedMoviesUseCase."""

import pytest

from src.modules.media.application.dtos import (
    ListRecentlyAddedMoviesInput,
    ListRecentlyAddedMoviesOutput,
    MovieSummaryOutput,
)
from src.modules.media.application.use_cases import ListRecentlyAddedMoviesUseCase
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


class TestListRecentlyAddedMoviesUseCase:
    """Tests for ListRecentlyAddedMoviesUseCase."""

    @pytest.mark.asyncio
    async def test_should_return_summaries_in_repository_order(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [
            _make_movie("Newest"),
            _make_movie("Older"),
        ]
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID, limit=10)
        )

        assert isinstance(result, ListRecentlyAddedMoviesOutput)
        assert [m.title for m in result.movies] == ["Newest", "Older"]
        assert all(isinstance(m, MovieSummaryOutput) for m in result.movies)

    @pytest.mark.asyncio
    async def test_should_pass_limit_to_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID, limit=15))

        mocks.movies.list_recently_added.assert_awaited_once_with(
            15, allowed_library_ids=[_LIBRARY_ID]
        )

    @pytest.mark.asyncio
    async def test_should_default_limit_to_twenty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        await use_case.execute(ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID))

        mocks.movies.list_recently_added.assert_awaited_once_with(
            20, allowed_library_ids=[_LIBRARY_ID]
        )

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_repository_empty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID))

        assert result.movies == []

    @pytest.mark.asyncio
    async def test_should_localize_summaries_with_input_lang(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [_make_movie("A Movie", 2024)]
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=make_profile_library_access(),
        )

        result = await use_case.execute(
            ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID, lang="pt-BR")
        )

        assert len(result.movies) == 1
        assert result.movies[0].title == "A Movie"

    @pytest.mark.asyncio
    async def test_should_short_circuit_for_deny_all_profile(self) -> None:
        mocks = make_media_uow_mock()
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: []}),
        )

        result = await use_case.execute(ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID))

        assert result.movies == []
        mocks.factory.assert_not_called()
        mocks.movies.list_recently_added.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_forward_only_allowed_libraries_for_inclusion_path(
        self,
    ) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [
            _make_movie("Visible", library_id=_LIBRARY_ID)
        ]
        use_case = ListRecentlyAddedMoviesUseCase(
            uow_factory=mocks.factory,
            profile_library_access=FakeProfileLibraryAccessPort({_PROFILE_ID: [_LIBRARY_ID]}),
        )

        result = await use_case.execute(ListRecentlyAddedMoviesInput(profile_id=_PROFILE_ID))

        assert [m.title for m in result.movies] == ["Visible"]
        passed = mocks.movies.list_recently_added.await_args.kwargs["allowed_library_ids"]
        assert list(passed) == [_LIBRARY_ID]
        assert _LIBRARY_ID_OTHER not in list(passed)

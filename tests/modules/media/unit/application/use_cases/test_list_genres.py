"""Tests for ListGenresUseCase."""


import pytest

from src.modules.media.application.dtos.catalog_dtos import (
    GenreOutput,
    ListGenresInput,
    ListGenresOutput,
)
from src.modules.media.application.use_cases.list_genres import ListGenresUseCase
from src.modules.media.domain.repositories.movie_repository import GenreRow
from tests.modules.media.unit.conftest import make_media_uow_mock


def _row(canonical: list[str], localized: list[str] | None = None) -> GenreRow:
    return GenreRow(canonical_genres=canonical, localized_genres=localized or [])


@pytest.mark.unit
class TestListGenresUseCase:
    """Cross-aggregation behavior of ListGenresUseCase."""

    @pytest.mark.asyncio
    async def test_should_count_unique_genres_across_movies_and_series(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [
            _row(["Action", "Comedy"]),
            _row(["Action"]),
        ]
        mocks.series.list_genre_rows.return_value = [
            _row(["Comedy"]),
            _row(["Drama"]),
        ]
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput())

        assert isinstance(result, ListGenresOutput)
        counts = {g.id: g.count for g in result.genres}
        assert counts == {"Action": 2, "Comedy": 2, "Drama": 1}

    @pytest.mark.asyncio
    async def test_should_sort_by_count_desc_then_alphabetical(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [
            _row(["Drama"]),
            _row(["Drama"]),
            _row(["Drama"]),
            _row(["Comedy"]),
            _row(["Comedy"]),
            _row(["Action"]),
            _row(["Action"]),
        ]
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput())

        # Drama (3) → Action, Comedy (tied at 2, alphabetical)
        assert [g.id for g in result.genres] == ["Drama", "Action", "Comedy"]

    @pytest.mark.asyncio
    async def test_should_use_first_seen_localized_label(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [
            _row(["Action"], ["Ação"]),
            _row(["Action"], ["A Wrong Translation"]),  # ignored — first wins
        ]
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput(lang="pt-BR"))

        assert result.genres[0] == GenreOutput(id="Action", name="Ação", count=2)

    @pytest.mark.asyncio
    async def test_should_fall_back_to_canonical_when_no_localized_label(self) -> None:
        mocks = make_media_uow_mock()
        # No localized genres available — repo returns empty list for that field
        mocks.movies.list_genre_rows.return_value = [_row(["Action"])]
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput(lang="pt-BR"))

        # Falls back to the canonical English name
        assert result.genres[0].name == "Action"

    @pytest.mark.asyncio
    async def test_should_skip_empty_localized_label(self) -> None:
        # An empty string in the localized list shouldn't beat a later
        # non-empty translation. The "first non-empty" rule.
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [
            _row(["Action"], [""]),
            _row(["Action"], ["Ação"]),
        ]
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput(lang="pt-BR"))

        assert result.genres[0].name == "Ação"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_rows(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = []
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput())

        assert result.genres == []

    @pytest.mark.asyncio
    async def test_should_pass_lang_through_to_repos(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = []
        mocks.series.list_genre_rows.return_value = []
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListGenresInput(lang="pt-BR"))

        mocks.movies.list_genre_rows.assert_awaited_once_with("pt-BR")
        mocks.series.list_genre_rows.assert_awaited_once_with("pt-BR")

    @pytest.mark.asyncio
    async def test_should_skip_series_repo_when_filtered_to_movies(self) -> None:
        # media_type="movie" restricts the aggregation to the movie
        # repo — the series repo must not be called at all so the
        # counts reflect movies only (and the Movies tab on the
        # frontend doesn't surface series-only genres).
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [_row(["Action"]), _row(["Comedy"])]
        mocks.series.list_genre_rows.return_value = [_row(["Drama"])]
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput(media_type="movie"))

        mocks.movies.list_genre_rows.assert_awaited_once()
        mocks.series.list_genre_rows.assert_not_awaited()
        assert {g.id for g in result.genres} == {"Action", "Comedy"}

    @pytest.mark.asyncio
    async def test_should_skip_movie_repo_when_filtered_to_series(self) -> None:
        # Mirror of the previous test — Series tab should only hit
        # the series repo.
        mocks = make_media_uow_mock()
        mocks.movies.list_genre_rows.return_value = [_row(["Action"])]
        mocks.series.list_genre_rows.return_value = [_row(["Drama"]), _row(["Thriller"])]
        use_case = ListGenresUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListGenresInput(media_type="series"))

        mocks.series.list_genre_rows.assert_awaited_once()
        mocks.movies.list_genre_rows.assert_not_awaited()
        assert {g.id for g in result.genres} == {"Drama", "Thriller"}

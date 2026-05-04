"""Tests for ListRecentlyAddedCatalogUseCase."""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.media.application.dtos.catalog_dtos import (
    CatalogItemOutput,
    ListRecentlyAddedCatalogInput,
    ListRecentlyAddedCatalogOutput,
)
from src.modules.media.application.use_cases import ListRecentlyAddedCatalogUseCase
from src.modules.media.domain.entities import Movie, Series
from tests.modules.media.unit.conftest import make_media_uow_mock

_LIBRARY_ID = "lib_test12345678"


def _movie_at(title: str, when: datetime) -> Movie:
    """Build a movie pinned to a specific ``created_at`` for the merge test."""
    return Movie.create(
        library_id=_LIBRARY_ID,
        title=title,
        year=2020,
        duration=7200,
        file_path=f"/movies/{title.lower().replace(' ', '_')}.mkv",
        file_size=1_000_000_000,
        resolution="1080p",
    ).with_updates(created_at=when)


def _series_at(title: str, when: datetime) -> Series:
    """Build a series pinned to a specific ``created_at`` for the merge test."""
    return Series.create(library_id=_LIBRARY_ID, title=title, start_year=2020).with_updates(
        created_at=when
    )


class TestListRecentlyAddedCatalogUseCase:
    """Tests for ListRecentlyAddedCatalogUseCase."""

    @pytest.mark.asyncio
    async def test_should_merge_streams_by_created_at_desc(self) -> None:
        base = datetime(2026, 5, 1, tzinfo=UTC)
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [
            _movie_at("Movie newest", base),
            _movie_at("Movie older", base - timedelta(hours=4)),
        ]
        mocks.series.list_recently_added.return_value = [
            _series_at("Series mid", base - timedelta(hours=2)),
        ]
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedCatalogInput(limit=10))

        assert isinstance(result, ListRecentlyAddedCatalogOutput)
        assert [(it.type, it.title) for it in result.items] == [
            ("movie", "Movie newest"),
            ("series", "Series mid"),
            ("movie", "Movie older"),
        ]

    @pytest.mark.asyncio
    async def test_should_clamp_merge_to_limit(self) -> None:
        base = datetime(2026, 5, 1, tzinfo=UTC)
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [
            _movie_at("M1", base),
            _movie_at("M2", base - timedelta(hours=2)),
        ]
        mocks.series.list_recently_added.return_value = [
            _series_at("S1", base - timedelta(hours=1)),
            _series_at("S2", base - timedelta(hours=3)),
        ]
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedCatalogInput(limit=2))

        # The two newest across both streams; the third and fourth
        # are dropped by the limit clamp regardless of their type.
        assert [(it.type, it.title) for it in result.items] == [
            ("movie", "M1"),
            ("series", "S1"),
        ]

    @pytest.mark.asyncio
    async def test_should_request_limit_from_each_repository(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        await use_case.execute(ListRecentlyAddedCatalogInput(limit=15))

        mocks.movies.list_recently_added.assert_awaited_once_with(15)
        mocks.series.list_recently_added.assert_awaited_once_with(15)

    @pytest.mark.asyncio
    async def test_should_return_only_movies_when_no_series(self) -> None:
        base = datetime(2026, 5, 1, tzinfo=UTC)
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [_movie_at("Solo", base)]
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedCatalogInput())

        assert len(result.items) == 1
        assert result.items[0].type == "movie"
        assert result.items[0].title == "Solo"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_both_streams_empty(self) -> None:
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = []
        mocks.series.list_recently_added.return_value = []
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedCatalogInput())

        assert result.items == []

    @pytest.mark.asyncio
    async def test_should_emit_catalog_item_outputs(self) -> None:
        base = datetime(2026, 5, 1, tzinfo=UTC)
        mocks = make_media_uow_mock()
        mocks.movies.list_recently_added.return_value = [_movie_at("Movie", base)]
        mocks.series.list_recently_added.return_value = [
            _series_at("Series", base - timedelta(hours=1))
        ]
        use_case = ListRecentlyAddedCatalogUseCase(uow_factory=mocks.factory)

        result = await use_case.execute(ListRecentlyAddedCatalogInput())

        assert all(isinstance(item, CatalogItemOutput) for item in result.items)
        assert {it.type for it in result.items} == {"movie", "series"}

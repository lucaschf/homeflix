"""Tests for GetWatchlistUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import (
    GetWatchlistInput,
    WatchlistItemOutput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.use_cases import GetWatchlistUseCase
from src.modules.collections.domain.entities import WatchlistItem
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.media_id import MovieId
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestGetWatchlistUseCase:
    """Tests for getting watchlist items with metadata."""

    @pytest.mark.asyncio
    async def test_should_return_items_with_metadata(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
        )

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
            progress_lookup=make_progress_lookup_mock(),
        )

        result = await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 1
        assert isinstance(result[0], WatchlistItemOutput)
        assert result[0].title == "Inception"

    @pytest.mark.asyncio
    async def test_should_carry_enrichment_fields_from_summary(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items
        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
            progress_lookup=make_progress_lookup_mock(),
        )

        out = (await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value)))[0]

        assert out.year == 2010
        assert out.runtime_seconds == 8880
        assert out.genres == ("Action", "Sci-Fi")
        assert out.resolution == "4K"
        assert out.hdr is True

    @pytest.mark.asyncio
    async def test_should_attach_progress_for_movies(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(movie_summary("mov_abc123def456")),
            progress_lookup=make_progress_lookup_mock({"mov_abc123def456": 0.42}),
        )

        out = (await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value)))[0]

        assert out.progress == 0.42

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_items(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = []
        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
            progress_lookup=make_progress_lookup_mock(),
        )

        result = await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_missing00000",
                media_type=MediaType.MOVIE,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(),  # no summaries
            progress_lookup=make_progress_lookup_mock(),
        )

        result = await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_mixed_media_types(
        self,
        movie_summary: MediaSummaryFactory,
        series_summary: MediaSummaryFactory,
    ) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            ),
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="ser_xyz789abc123",
                media_type=MediaType.SERIES,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
            series_summary("ser_xyz789abc123", "Breaking Bad"),
        )

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
            progress_lookup=make_progress_lookup_mock(),
        )

        result = await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        assert result[0].title == "Inception"
        assert result[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_respect_limit(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = []
        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
            progress_lookup=make_progress_lookup_mock(),
        )

        await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value, limit=25))

        mocks.watchlist.list_all.assert_called_once_with(_PROFILE_ID, limit=25)

    @pytest.mark.asyncio
    async def test_should_pass_language_to_media_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        items = [
            WatchlistItem.create(
                profile_id=_PROFILE_ID,
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.watchlist.list_all.return_value = items

        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        use_case = GetWatchlistUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
            progress_lookup=make_progress_lookup_mock(),
        )

        await use_case.execute(GetWatchlistInput(profile_id=_PROFILE_ID.value, lang="pt-BR"))

        media_lookup.get_many.assert_awaited_once_with(
            [MovieId("mov_abc123def456")],
            [],
            "pt-BR",
        )

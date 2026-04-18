"""Tests for GetCustomListItemsUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
)

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.use_cases import GetCustomListItemsUseCase
from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.repositories import CustomListRepository
from src.shared_kernel.value_objects import CollectionMediaType


@pytest.mark.unit
class TestGetCustomListItemsUseCase:
    """Tests for getting custom list items with metadata."""

    @pytest.mark.asyncio
    async def test_should_return_items_with_metadata(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(name="Test")
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]

        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = custom_list
        mock_list_repo.list_items.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
        )

        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=media_lookup,
        )

        result = await use_case.execute(GetCustomListItemsInput(list_id=str(custom_list.id)))

        assert len(result) == 1
        assert isinstance(result[0], CustomListItemOutput)
        assert result[0].title == "Inception"
        assert result[0].media_id == "mov_abc123def456"

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = None
        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=AsyncMock(spec=MediaLookupPort),
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(GetCustomListItemsInput(list_id="lst_nonexistent00"))

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_items(self) -> None:
        custom_list = CustomList.create(name="Empty List")
        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = custom_list
        mock_list_repo.list_items.return_value = []
        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=AsyncMock(spec=MediaLookupPort),
        )

        result = await use_case.execute(GetCustomListItemsInput(list_id=str(custom_list.id)))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        custom_list = CustomList.create(name="Test")
        items = [
            CustomListItem.create(
                media_id="mov_missing00000",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]
        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = custom_list
        mock_list_repo.list_items.return_value = items

        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=make_media_lookup_mock(),
        )

        result = await use_case.execute(GetCustomListItemsInput(list_id=str(custom_list.id)))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_mixed_media_types(
        self,
        movie_summary: MediaSummaryFactory,
        series_summary: MediaSummaryFactory,
    ) -> None:
        custom_list = CustomList.create(name="Mixed")
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
            CustomListItem.create(
                media_id="ser_xyz789abc123",
                media_type=CollectionMediaType.SERIES,
                position=1,
            ),
        ]

        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = custom_list
        mock_list_repo.list_items.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
            series_summary("ser_xyz789abc123", "Breaking Bad"),
        )

        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=media_lookup,
        )

        result = await use_case.execute(GetCustomListItemsInput(list_id=str(custom_list.id)))

        assert len(result) == 2
        assert result[0].title == "Inception"
        assert result[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_pass_language_to_media_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(name="Test")
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]

        mock_list_repo = AsyncMock(spec=CustomListRepository)
        mock_list_repo.find_by_id.return_value = custom_list
        mock_list_repo.list_items.return_value = items

        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        use_case = GetCustomListItemsUseCase(
            custom_list_repository=mock_list_repo,
            media_lookup=media_lookup,
        )

        await use_case.execute(GetCustomListItemsInput(list_id=str(custom_list.id), lang="pt-BR"))

        media_lookup.get_many.assert_awaited_once_with(
            ["mov_abc123def456"],
            [],
            "pt-BR",
        )

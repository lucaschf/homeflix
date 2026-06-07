"""Tests for GetCustomListItemsUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import (
    CustomListItemOutput,
    GetCustomListItemsInput,
)
from src.modules.collections.application.ports import MediaLookupPort
from src.modules.collections.application.use_cases import GetCustomListItemsUseCase
from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.media_id import MovieId
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_PROFILE_ID = ProfileId("prf_test12345678")


@pytest.mark.unit
class TestGetCustomListItemsUseCase:
    """Tests for getting custom list items with metadata."""

    @pytest.mark.asyncio
    async def test_should_return_items_with_metadata(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
        )

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert len(result) == 1
        assert isinstance(result[0], CustomListItemOutput)
        assert result[0].title == "Inception"
        assert result[0].media_id == "mov_abc123def456"

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
        )

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                GetCustomListItemsInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_no_items(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Empty List", existing_count=0)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = []
        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_missing00000",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_should_handle_mixed_media_types(
        self,
        movie_summary: MediaSummaryFactory,
        series_summary: MediaSummaryFactory,
    ) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Mixed", existing_count=0)
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
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        media_lookup = make_media_lookup_mock(
            movie_summary("mov_abc123def456", "Inception"),
            series_summary("ser_xyz789abc123", "Breaking Bad"),
        )

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert len(result) == 2
        assert result[0].title == "Inception"
        assert result[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_pass_language_to_media_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=CollectionMediaType.MOVIE,
                position=0,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        media_lookup = make_media_lookup_mock(movie_summary("mov_abc123def456"))

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=media_lookup,
        )

        await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                lang="pt-BR",
            )
        )

        media_lookup.get_many.assert_awaited_once_with(
            [MovieId("mov_abc123def456")],
            [],
            "pt-BR",
        )

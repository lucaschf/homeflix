"""Tests for GetCustomListItemsUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
    make_profile_library_access_mock,
    make_progress_lookup_mock,
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
from src.shared_kernel.value_objects import MediaType
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
                media_type=MediaType.MOVIE,
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
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert len(result.items) == 1
        assert isinstance(result.items[0], CustomListItemOutput)
        assert result.items[0].title == "Inception"
        assert result.items[0].media_id == "mov_abc123def456"
        assert result.items[0].position == 0
        # Enrichment fields flow through from the media summary.
        assert result.items[0].year == 2010
        assert result.items[0].runtime_seconds == 8880
        assert result.items[0].genres == ("Action", "Sci-Fi")
        assert result.items[0].resolution == "4K"
        assert result.items[0].hdr is True

    @pytest.mark.asyncio
    async def test_should_attach_progress_for_movie_items(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
                position=0,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(movie_summary("mov_abc123def456")),
            progress_lookup=make_progress_lookup_mock({"mov_abc123def456": 0.5}),
            profile_library_access=make_profile_library_access_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(profile_id=_PROFILE_ID.value, list_id=str(custom_list.id))
        )

        assert result.items[0].progress == 0.5

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        # Neither owned by the caller nor resolvable as a shared list.
        mocks.custom_lists.find_by_id.return_value = None
        mocks.custom_lists.find_by_id_unscoped.return_value = None
        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
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
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert result.items == ()

    @pytest.mark.asyncio
    async def test_should_skip_missing_media(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_missing00000",
                media_type=MediaType.MOVIE,
                position=0,
            ),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.list_items.return_value = items

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(),
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert result.items == ()

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
                media_type=MediaType.MOVIE,
                position=0,
            ),
            CustomListItem.create(
                media_id="ser_xyz789abc123",
                media_type=MediaType.SERIES,
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
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
            )
        )

        assert len(result.items) == 2
        assert result.items[0].title == "Inception"
        assert result.items[1].title == "Breaking Bad"

    @pytest.mark.asyncio
    async def test_should_pass_language_to_media_lookup(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Test", existing_count=0)
        items = [
            CustomListItem.create(
                media_id="mov_abc123def456",
                media_type=MediaType.MOVIE,
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
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock(),
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


_OWNER_ID = ProfileId("prf_owner0000001")
_FOLLOWER_ID = ProfileId("prf_follower0001")


@pytest.mark.unit
class TestGetCustomListItemsFollowerPath:
    """A follower reading a shared list gets access-filtered items."""

    @pytest.mark.asyncio
    async def test_follower_sees_filtered_items_with_hidden_count(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        from src.modules.collections.domain.entities import ListFollow
        from src.modules.collections.domain.value_objects import ListId

        shared = CustomList.create(
            profile_id=_OWNER_ID, name="Owner list", existing_count=0
        ).shared()
        items = [
            CustomListItem.create(media_id="mov_allowed00001", media_type=MediaType.MOVIE),
            CustomListItem.create(media_id="mov_restrict0001", media_type=MediaType.MOVIE),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None  # not the owner
        mocks.custom_lists.find_by_id_unscoped.return_value = shared
        mocks.list_follows.find.return_value = ListFollow.create(
            follower_profile_id=_FOLLOWER_ID, list_id=ListId(str(shared.id))
        )
        mocks.custom_lists.list_items.return_value = items

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=make_media_lookup_mock(
                movie_summary("mov_allowed00001", library_id="lib_movies000001"),
                movie_summary("mov_restrict0001", library_id="lib_locked000001"),
            ),
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock("lib_movies000001"),
        )

        result = await use_case.execute(
            GetCustomListItemsInput(profile_id=_FOLLOWER_ID.value, list_id=str(shared.id))
        )

        assert len(result.items) == 1
        assert result.items[0].media_id == "mov_allowed00001"
        assert result.hidden_count == 1

    @pytest.mark.asyncio
    async def test_non_follower_gets_not_found(self) -> None:
        shared = CustomList.create(
            profile_id=_OWNER_ID, name="Owner list", existing_count=0
        ).shared()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = None
        mocks.custom_lists.find_by_id_unscoped.return_value = shared
        mocks.list_follows.find.return_value = None  # caller doesn't follow it

        use_case = GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=AsyncMock(spec=MediaLookupPort),
            progress_lookup=make_progress_lookup_mock(),
            profile_library_access=make_profile_library_access_mock("lib_movies000001"),
        )

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetCustomListItemsInput(profile_id=_FOLLOWER_ID.value, list_id=str(shared.id))
            )

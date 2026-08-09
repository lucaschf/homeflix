"""Tests for GetSharedListPreviewUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
    make_profile_library_access_mock,
    make_profile_lookup_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import GetSharedListPreviewInput
from src.modules.collections.application.use_cases import GetSharedListPreviewUseCase
from src.modules.collections.domain.entities import CustomList, CustomListItem, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_OWNER = ProfileId("prf_owner0000001")
_FOLLOWER = ProfileId("prf_follower0001")


def _shared_list() -> CustomList:
    return CustomList.create(profile_id=_OWNER, name="Owner list", existing_count=0).shared()


def _item(media_id: str) -> CustomListItem:
    return CustomListItem.create(media_id=media_id, media_type=MediaType.MOVIE)


def _make_use_case(
    mocks, *, allowed_libraries: tuple[str, ...], summaries, follow=None, owner_name="Lucas"
) -> GetSharedListPreviewUseCase:
    mocks.list_follows.find.return_value = follow
    return GetSharedListPreviewUseCase(
        uow_factory=mocks.factory,
        media_lookup=make_media_lookup_mock(*summaries),
        progress_lookup=make_progress_lookup_mock(),
        profile_library_access=make_profile_library_access_mock(*allowed_libraries),
        profile_lookup=make_profile_lookup_mock({_OWNER.value: owner_name}),
    )


@pytest.mark.unit
class TestGetSharedListPreviewUseCase:
    """Read-only, access-filtered preview by token."""

    @pytest.mark.asyncio
    async def test_returns_meta_items_and_owner_name(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [_item("mov_aaa111bbb222")]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_movies000001",),
            summaries=[movie_summary("mov_aaa111bbb222", library_id="lib_movies000001")],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert result.list.name == "Owner list"
        assert result.list.owner_name == "Lucas"
        assert len(result.items) == 1
        assert result.hidden_count == 0
        assert result.is_following is False

    @pytest.mark.asyncio
    async def test_kids_profile_never_sees_restricted_items(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [
            _item("mov_allowed00001"),
            _item("mov_restrict0001"),
        ]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_kids00000001",),
            summaries=[
                movie_summary("mov_allowed00001", library_id="lib_kids00000001"),
                movie_summary("mov_restrict0001", library_id="lib_adults000001"),
            ],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        # The restricted title is filtered out and counted, never leaked.
        assert len(result.items) == 1
        assert result.items[0].media_id == "mov_allowed00001"
        assert result.hidden_count == 1

    @pytest.mark.asyncio
    async def test_fully_restricted_list_previews_empty_with_notice(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [_item("mov_restrict0001")]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=(),  # deny-all
            summaries=[movie_summary("mov_restrict0001", library_id="lib_adults000001")],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert result.items == ()
        assert result.hidden_count == 1

    @pytest.mark.asyncio
    async def test_is_following_true_when_follow_exists(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list()
        follow = ListFollow.create(follower_profile_id=_FOLLOWER, list_id=ListId(str(shared.id)))
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = []
        use_case = _make_use_case(
            mocks, allowed_libraries=("lib_movies000001",), summaries=[], follow=follow
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert result.is_following is True

    @pytest.mark.asyncio
    async def test_unknown_token_raises_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = None
        use_case = _make_use_case(mocks, allowed_libraries=("lib_movies000001",), summaries=[])

        with pytest.raises(ResourceNotFoundException):
            await use_case.execute(
                GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token="x" * 24)
            )

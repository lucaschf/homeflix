"""Tests for GetSharedListPreviewUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    make_media_lookup_mock,
    make_profile_lookup_mock,
    make_profile_viewing_policy_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.building_blocks.application.errors import ResourceNotFoundException
from src.modules.collections.application.dtos import GetSharedListPreviewInput
from src.modules.collections.application.use_cases import GetSharedListPreviewUseCase
from src.modules.collections.domain.entities import CustomList, CustomListItem, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
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
    mocks,
    *,
    allowed_libraries: tuple[str, ...],
    summaries,
    follow=None,
    owner_name="Lucas",
    maturity_limit: AgeRating | None = None,
) -> GetSharedListPreviewUseCase:
    mocks.list_follows.find.return_value = follow
    return GetSharedListPreviewUseCase(
        uow_factory=mocks.factory,
        media_lookup=make_media_lookup_mock(*summaries),
        progress_lookup=make_progress_lookup_mock(),
        profile_viewing_policy=make_profile_viewing_policy_mock(
            *allowed_libraries, maturity_limit=maturity_limit
        ),
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
    @pytest.mark.parametrize("library_id", [None, "lib_short", "", " lib_movies000001 "])
    async def test_item_with_unknown_or_malformed_library_is_hidden(
        self, movie_summary: MediaSummaryFactory, library_id: str | None
    ) -> None:
        # No policy can grant a library it cannot name: the item is
        # withheld and counted, and the preview itself still succeeds.
        shared = _shared_list()
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [_item("mov_restrict0001")]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_movies000001",),
            summaries=[movie_summary("mov_restrict0001", library_id=library_id)],
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


@pytest.mark.unit
class TestGetSharedListPreviewMaturityLimit:
    """Titles above the caller's maturity limit leave no trace in the preview."""

    @pytest.mark.asyncio
    async def test_withheld_titles_are_left_out_of_items_count_and_positions(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list().with_updates(item_count=5)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [
            CustomListItem.create(media_id=media_id, media_type=MediaType.MOVIE, position=position)
            for position, media_id in enumerate(
                [
                    "mov_sixteen00001",
                    "mov_tenyears0001",
                    "mov_restrict0001",
                    "mov_unrated00001",
                    "mov_tenyears0002",
                ]
            )
        ]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_movies000001",),
            maturity_limit=AgeRating(12),
            summaries=[
                movie_summary("mov_sixteen00001", minimum_age=AgeRating(16)),
                movie_summary("mov_tenyears0001", minimum_age=AgeRating(10)),
                movie_summary(
                    "mov_restrict0001", library_id="lib_adults000001", minimum_age=AgeRating(10)
                ),
                movie_summary("mov_unrated00001", minimum_age=None),
                movie_summary("mov_tenyears0002", minimum_age=AgeRating(10)),
            ],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert [item.media_id for item in result.items] == [
            "mov_tenyears0001",
            "mov_tenyears0002",
        ]
        assert [item.position for item in result.items] == [0, 1]
        assert result.hidden_count == 1
        # Stored 5, minus the 2 withheld by age; the hidden one stays counted.
        assert result.list.item_count == 3

    @pytest.mark.asyncio
    async def test_removed_title_stays_in_the_count_under_a_limit(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list().with_updates(item_count=6)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        media_ids = [
            "mov_removed00001",
            "mov_sixteen00001",
            "mov_tenyears0001",
            "mov_tenyears0002",
            "mov_tenyears0003",
            "mov_tenyears0004",
        ]
        mocks.custom_lists.list_items.return_value = [
            CustomListItem.create(media_id=media_id, media_type=MediaType.MOVIE, position=position)
            for position, media_id in enumerate(media_ids)
        ]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_movies000001",),
            maturity_limit=AgeRating(12),
            # No summary for the removed title: it is gone from the catalog.
            summaries=[
                movie_summary("mov_sixteen00001", minimum_age=AgeRating(16)),
                *(movie_summary(media_id, minimum_age=AgeRating(10)) for media_id in media_ids[2:]),
            ],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert [item.media_id for item in result.items] == media_ids[2:]
        assert result.hidden_count == 0
        # Stored 6, minus only the 1 withheld by age: the removed title is
        # not emitted but still counted, as without a limit.
        assert result.list.item_count == 5

    @pytest.mark.asyncio
    async def test_stored_count_and_positions_are_kept_without_a_limit(
        self, movie_summary: MediaSummaryFactory
    ) -> None:
        shared = _shared_list().with_updates(item_count=4)
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_share_token.return_value = shared
        mocks.custom_lists.list_items.return_value = [
            CustomListItem.create(
                media_id="mov_sixteen00001", media_type=MediaType.MOVIE, position=0
            ),
            CustomListItem.create(
                media_id="mov_restrict0001", media_type=MediaType.MOVIE, position=1
            ),
            CustomListItem.create(
                media_id="mov_unrated00001", media_type=MediaType.MOVIE, position=5
            ),
        ]
        use_case = _make_use_case(
            mocks,
            allowed_libraries=("lib_movies000001",),
            summaries=[
                movie_summary("mov_sixteen00001", minimum_age=AgeRating(16)),
                movie_summary(
                    "mov_restrict0001", library_id="lib_adults000001", minimum_age=AgeRating(10)
                ),
                movie_summary("mov_unrated00001", minimum_age=None),
            ],
        )

        result = await use_case.execute(
            GetSharedListPreviewInput(profile_id=_FOLLOWER.value, token=shared.share_token.value)
        )

        assert [item.media_id for item in result.items] == [
            "mov_sixteen00001",
            "mov_unrated00001",
        ]
        assert [item.position for item in result.items] == [0, 5]
        assert result.hidden_count == 1
        assert result.list.item_count == 4

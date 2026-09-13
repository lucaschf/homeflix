"""Tests for ListCustomListsUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, call

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    MOVIES_LIBRARY_ID,
    make_catalog_lookup_mock,
    make_profile_lookup_mock,
    make_profile_viewing_policy_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import make_collections_uow_mock

from src.modules.collections.application.dtos import (
    CustomListOutput,
    GetCustomListItemsInput,
    GetSharedListPreviewInput,
)
from src.modules.collections.application.ports import ProfileViewingPolicyPort
from src.modules.collections.application.use_cases import (
    GetCustomListItemsUseCase,
    GetSharedListPreviewUseCase,
    ListCustomListsUseCase,
)
from src.modules.collections.application.use_cases.list_custom_lists import (
    ListCustomListsInput,
)
from src.modules.collections.domain.entities import CustomList, CustomListItem, ListFollow
from src.modules.collections.domain.value_objects import ListId
from src.shared_kernel.content_policy import ViewingPolicy
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_PROFILE_ID = ProfileId("prf_test12345678")
_OWNER_ID = ProfileId("prf_owner0000001")


@pytest.mark.unit
class TestListCustomListsUseCase:
    """Tests for listing owned + followed custom lists."""

    @pytest.mark.asyncio
    async def test_should_return_all_owned_lists(self) -> None:
        lists = [
            CustomList.create(profile_id=_PROFILE_ID, name="Action", existing_count=0),
            CustomList.create(profile_id=_PROFILE_ID, name="Comedy", existing_count=0),
        ]
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = lists
        mocks.list_follows.list_for_follower.return_value = []
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
            media_lookup=make_catalog_lookup_mock(),
            profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        assert all(isinstance(item, CustomListOutput) for item in result)
        assert result[0].name == "Action"
        assert result[1].name == "Comedy"
        assert all(not item.is_followed for item in result)
        mocks.custom_lists.list_all.assert_called_once_with(_PROFILE_ID)

    @pytest.mark.asyncio
    async def test_should_return_empty_list_when_none_exist(self) -> None:
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = []
        mocks.list_follows.list_for_follower.return_value = []
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
            media_lookup=make_catalog_lookup_mock(),
            profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert result == []

    @pytest.mark.asyncio
    async def test_should_append_followed_lists_flagged_with_owner_name(self) -> None:
        owned = CustomList.create(profile_id=_PROFILE_ID, name="Mine", existing_count=0)
        followed = CustomList.create(
            profile_id=_OWNER_ID, name="Lucas' picks", existing_count=0
        ).shared()
        follow = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId(str(followed.id)),
        )
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = [owned]
        mocks.list_follows.list_for_follower.return_value = [follow]
        mocks.custom_lists.find_by_id_unscoped.return_value = followed
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock({_OWNER_ID.value: "Lucas"}),
            media_lookup=make_catalog_lookup_mock(),
            profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert len(result) == 2
        # Owned row first, followed row second.
        assert result[0].is_followed is False
        assert result[1].is_followed is True
        assert result[1].owner_name == "Lucas"
        assert result[1].name == "Lucas' picks"

    @pytest.mark.asyncio
    async def test_should_drop_followed_list_that_is_gone_or_unshared(self) -> None:
        follow_gone = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId("lst_gone00000001"),
        )
        follow_unshared = ListFollow.create(
            follower_profile_id=_PROFILE_ID,
            list_id=ListId("lst_unshared0001"),
        )
        unshared_list = CustomList.create(
            profile_id=_OWNER_ID, name="No longer shared", existing_count=0
        )
        mocks = make_collections_uow_mock()
        mocks.custom_lists.list_all.return_value = []
        mocks.list_follows.list_for_follower.return_value = [follow_gone, follow_unshared]
        mocks.custom_lists.find_by_id_unscoped.side_effect = [None, unshared_list]
        use_case = ListCustomListsUseCase(
            uow_factory=mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
            media_lookup=make_catalog_lookup_mock(),
            profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
        )

        result = await use_case.execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert result == []


_LIMIT = AgeRating(12)
_OTHER_LIBRARY_ID = "lib_other0000001"

_VISIBLE = "mov_visible00001"
_WITHHELD = "mov_withheld0001"
_UNRATED = "ser_unrated00001"
_OTHER_SHELF = "mov_othershelf01"
_OTHER_SHELF_ADULT = "ser_othershelf18"
_REMOVED = "mov_removed00001"


def _items(*media_ids: str) -> list[CustomListItem]:
    return [
        CustomListItem.create(
            media_id=media_id,
            media_type=MediaType.MOVIE if media_id.startswith("mov_") else MediaType.SERIES,
            position=position,
        )
        for position, media_id in enumerate(media_ids)
    ]


def _catalog(movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory) -> AsyncMock:
    """One title per outcome under a limit of 12 on ``MOVIES_LIBRARY_ID``.

    ``_REMOVED`` is left out: it is in the lists but gone from the catalog.
    """
    return make_catalog_lookup_mock(
        movie_summary(_VISIBLE, library_id=MOVIES_LIBRARY_ID, minimum_age=AgeRating(10)),
        movie_summary(_WITHHELD, library_id=MOVIES_LIBRARY_ID, minimum_age=AgeRating(16)),
        series_summary(_UNRATED, library_id=MOVIES_LIBRARY_ID, minimum_age=None),
        movie_summary(_OTHER_SHELF, library_id=_OTHER_LIBRARY_ID, minimum_age=AgeRating(10)),
        series_summary(_OTHER_SHELF_ADULT, library_id=_OTHER_LIBRARY_ID, minimum_age=AgeRating(18)),
    )


def _policy_per_profile(policies: dict[ProfileId, ViewingPolicy]) -> AsyncMock:
    """A ``ProfileViewingPolicyPort`` answering each profile with its own policy."""
    port = AsyncMock(spec=ProfileViewingPolicyPort)
    port.find_for_profile.side_effect = policies.__getitem__
    return port


class _Store:
    """One owned and one followed list, served alike to every use case."""

    def __init__(self) -> None:
        self.owned_items = _items(
            _WITHHELD, _VISIBLE, _OTHER_SHELF, _UNRATED, _REMOVED, _OTHER_SHELF_ADULT
        )
        self.followed_items = _items(_VISIBLE, _WITHHELD, _REMOVED, _OTHER_SHELF)
        self.owned = CustomList.create(
            profile_id=_PROFILE_ID, name="Mine", existing_count=0
        ).with_updates(item_count=len(self.owned_items))
        self.followed = (
            CustomList.create(profile_id=_OWNER_ID, name="Theirs", existing_count=0)
            .shared()
            .with_updates(item_count=len(self.followed_items))
        )
        follow = ListFollow.create(
            follower_profile_id=_PROFILE_ID, list_id=ListId(str(self.followed.id))
        )
        self.mocks = make_collections_uow_mock()
        repo = self.mocks.custom_lists
        repo.list_all.return_value = [self.owned]
        repo.find_by_id.side_effect = lambda list_id, _profile_id: (
            self.owned if list_id == str(self.owned.id) else None
        )
        repo.find_by_id_unscoped.return_value = self.followed
        repo.find_by_share_token.return_value = self.followed
        repo.list_items.side_effect = lambda list_id, _profile_id: (
            self.owned_items if list_id == str(self.owned.id) else self.followed_items
        )
        self.mocks.list_follows.list_for_follower.return_value = [follow]
        self.mocks.list_follows.find.return_value = follow

    def use_case(self, media_lookup: AsyncMock, policy: AsyncMock) -> ListCustomListsUseCase:
        return ListCustomListsUseCase(
            uow_factory=self.mocks.factory,
            profile_lookup=make_profile_lookup_mock(),
            media_lookup=media_lookup,
            profile_viewing_policy=policy,
        )


@pytest.mark.unit
class TestListCustomListsItemCount:
    """``item_count`` leaves out only the titles withheld from the caller by age."""

    @pytest.mark.asyncio
    async def test_should_show_stored_count_without_media_or_item_reads_when_unlimited(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        catalog = _catalog(movie_summary, series_summary)

        result = await store.use_case(
            catalog, make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID)
        ).execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert [row.item_count for row in result] == [6, 4]
        catalog.find_visible_titles.assert_not_awaited()
        catalog.get_many.assert_not_awaited()
        store.mocks.custom_lists.list_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_subtract_only_titles_withheld_by_age_on_owned_and_followed(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()

        result = await store.use_case(
            _catalog(movie_summary, series_summary),
            make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT),
        ).execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        # Owned: 6 stored, the 16 and the unrated title withheld. Followed:
        # 4 stored, the 16 withheld. Removed and other-shelf titles stay in.
        assert [(row.id, row.item_count) for row in result] == [
            (str(store.owned.id), 4),
            (str(store.followed.id), 3),
        ]
        store.mocks.custom_lists.list_items.assert_has_awaits(
            [call(str(store.owned.id), _PROFILE_ID), call(str(store.followed.id), _OWNER_ID)]
        )

    @pytest.mark.asyncio
    async def test_should_agree_with_items_read_and_preview_for_owner_and_follower(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        catalog = _catalog(movie_summary, series_summary)
        policy = make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT)
        items_read = GetCustomListItemsUseCase(
            uow_factory=store.mocks.factory,
            media_lookup=catalog,
            progress_lookup=make_progress_lookup_mock(),
            profile_viewing_policy=policy,
        )
        preview_read = GetSharedListPreviewUseCase(
            uow_factory=store.mocks.factory,
            media_lookup=catalog,
            progress_lookup=make_progress_lookup_mock(),
            profile_viewing_policy=policy,
            profile_lookup=make_profile_lookup_mock(),
        )

        rows = await store.use_case(catalog, policy).execute(
            ListCustomListsInput(profile_id=_PROFILE_ID.value)
        )
        preview = await preview_read.execute(
            GetSharedListPreviewInput(profile_id=_PROFILE_ID.value, token="t" * 32)
        )

        for row in rows:
            read = await items_read.execute(
                GetCustomListItemsInput(profile_id=_PROFILE_ID.value, list_id=row.id)
            )
            removed = 1  # ``_REMOVED`` sits in both lists.
            assert row.item_count - len(read.items) - read.hidden_count == removed
        assert rows[1].item_count == preview.list.item_count

    @pytest.mark.asyncio
    async def test_should_ask_the_catalog_twice_for_every_list_after_the_transaction(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        second_owned = CustomList.create(
            profile_id=_PROFILE_ID, name="Two", existing_count=0
        ).with_updates(item_count=2)
        store.mocks.custom_lists.list_all.return_value = [store.owned, second_owned]
        second_items = _items(_UNRATED, _VISIBLE)
        list_items = store.mocks.custom_lists.list_items.side_effect
        store.mocks.custom_lists.list_items.side_effect = lambda list_id, profile_id: (
            second_items if list_id == str(second_owned.id) else list_items(list_id, profile_id)
        )
        catalog = _catalog(movie_summary, series_summary)
        answer = catalog.find_visible_titles.side_effect

        async def after_the_transaction(**kwargs: object) -> frozenset[str]:
            store.mocks.uow.__aexit__.assert_awaited_once()  # type: ignore[attr-defined]
            return await answer(**kwargs)

        catalog.find_visible_titles.side_effect = after_the_transaction

        result = await store.use_case(
            catalog, make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT)
        ).execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert [row.item_count for row in result] == [4, 1, 3]
        assert catalog.find_visible_titles.await_count == 2
        every_title = {
            item.media_id.value
            for item in [*store.owned_items, *second_items, *store.followed_items]
        }
        policies = []
        for awaited in catalog.find_visible_titles.await_args_list:
            requested = [m.value for m in awaited.kwargs["movie_ids"]] + [
                s.value for s in awaited.kwargs["series_ids"]
            ]
            assert sorted(requested) == sorted(every_title)
            policies.append(awaited.kwargs["policy"])
        assert set(policies) == {
            ViewingPolicy.unrestricted([MOVIES_LIBRARY_ID]),
            ViewingPolicy(allowed_library_ids=[MOVIES_LIBRARY_ID], maturity_limit=_LIMIT),
        }

    @pytest.mark.asyncio
    async def test_should_show_stored_count_without_media_calls_under_deny_all(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        catalog = _catalog(movie_summary, series_summary)

        result = await store.use_case(
            catalog, make_profile_viewing_policy_mock(maturity_limit=_LIMIT)
        ).execute(ListCustomListsInput(profile_id=_PROFILE_ID.value))

        assert [row.item_count for row in result] == [6, 4]
        catalog.find_visible_titles.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_derive_followed_count_by_limited_callers_policy_not_owners(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        policy = _policy_per_profile(
            {
                _PROFILE_ID: ViewingPolicy(
                    allowed_library_ids=[MOVIES_LIBRARY_ID], maturity_limit=_LIMIT
                ),
                _OWNER_ID: ViewingPolicy.unrestricted([MOVIES_LIBRARY_ID]),
            }
        )

        result = await store.use_case(_catalog(movie_summary, series_summary), policy).execute(
            ListCustomListsInput(profile_id=_PROFILE_ID.value)
        )

        # The follower's limit withholds the 16 the unlimited owner sees.
        assert [(row.id, row.item_count) for row in result] == [
            (str(store.owned.id), 4),
            (str(store.followed.id), 3),
        ]

    @pytest.mark.asyncio
    async def test_should_show_followed_stored_count_when_only_the_owner_is_limited(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        catalog = _catalog(movie_summary, series_summary)
        policy = _policy_per_profile(
            {
                _PROFILE_ID: ViewingPolicy.unrestricted([MOVIES_LIBRARY_ID]),
                _OWNER_ID: ViewingPolicy(
                    allowed_library_ids=[MOVIES_LIBRARY_ID], maturity_limit=_LIMIT
                ),
            }
        )

        result = await store.use_case(catalog, policy).execute(
            ListCustomListsInput(profile_id=_PROFILE_ID.value)
        )

        assert [(row.id, row.item_count) for row in result] == [
            (str(store.owned.id), 6),
            (str(store.followed.id), 4),
        ]
        catalog.find_visible_titles.assert_not_awaited()
        store.mocks.custom_lists.list_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_read_the_policy_before_opening_the_transaction(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        store = _Store()
        policy = make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT)
        manager = Mock()
        manager.attach_mock(policy.find_for_profile, "find_for_profile")
        manager.attach_mock(store.mocks.factory, "uow_factory")

        await store.use_case(_catalog(movie_summary, series_summary), policy).execute(
            ListCustomListsInput(profile_id=_PROFILE_ID.value)
        )

        assert manager.mock_calls[0] == call.find_for_profile(_PROFILE_ID)
        assert call.uow_factory() in manager.mock_calls[1:]

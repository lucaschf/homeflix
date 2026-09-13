"""Tests for RenameCustomListUseCase."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock, call

import pytest
from tests.modules.collections.unit.application.use_cases.conftest import (
    MOVIES_LIBRARY_ID,
    make_catalog_lookup_mock,
    make_profile_viewing_policy_mock,
    make_progress_lookup_mock,
)
from tests.modules.collections.unit.conftest import (
    CollectionsUoWMocks,
    make_collections_uow_mock,
)

from src.building_blocks.application.errors import ResourceNotFoundException
from src.building_blocks.domain import BusinessRuleViolationException
from src.modules.collections.application.dtos import (
    CustomListOutput,
    GetCustomListItemsInput,
    RenameCustomListInput,
)
from src.modules.collections.application.use_cases import (
    GetCustomListItemsUseCase,
    RenameCustomListUseCase,
)
from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.shared_kernel.value_objects import MediaType
from src.shared_kernel.value_objects.age_rating import AgeRating
from src.shared_kernel.value_objects.profile_id import ProfileId

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from tests.modules.collections.unit.application.use_cases.conftest import (
        MediaSummaryFactory,
    )

_PROFILE_ID = ProfileId("prf_test12345678")


def _make_use_case(mocks: CollectionsUoWMocks) -> RenameCustomListUseCase:
    """Build the use case for a caller without a maturity limit."""
    return RenameCustomListUseCase(
        uow_factory=mocks.factory,
        media_lookup=make_catalog_lookup_mock(),
        profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
    )


@pytest.mark.unit
class TestRenameCustomListUseCase:
    """Tests for renaming custom lists."""

    @pytest.mark.asyncio
    async def test_should_rename_successfully(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Old Name", existing_count=0)
        renamed = custom_list.rename("New Name")
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = None
        mock_repo.update.return_value = renamed
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                name="New Name",
            )
        )

        assert isinstance(result, CustomListOutput)
        assert result.name == "New Name"
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_update_name_and_description(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Old Name", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = None
        mock_repo.update.side_effect = lambda entity: entity  # echo what was built
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                name="New Name",
                description="  A weekend of scares  ",
            )
        )

        assert result.name == "New Name"
        assert result.description == "A weekend of scares"

    @pytest.mark.asyncio
    async def test_should_raise_when_list_not_found(self) -> None:
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = None
        use_case = _make_use_case(mocks)

        with pytest.raises(ResourceNotFoundException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id="lst_nonexistent00",
                    name="New Name",
                )
            )

        assert exc_info.value.resource_type == "CustomList"

    @pytest.mark.asyncio
    async def test_should_raise_when_name_taken_by_other_list(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="My List", existing_count=0)
        other_list = CustomList.create(profile_id=_PROFILE_ID, name="Taken Name", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = other_list
        use_case = _make_use_case(mocks)

        with pytest.raises(BusinessRuleViolationException) as exc_info:
            await use_case.execute(
                RenameCustomListInput(
                    profile_id=_PROFILE_ID.value,
                    list_id=str(custom_list.id),
                    name="Taken Name",
                )
            )

        assert exc_info.value.message_code == "CUSTOM_LIST_NAME_DUPLICATE"

    @pytest.mark.asyncio
    async def test_should_allow_renaming_to_same_name(self) -> None:
        custom_list = CustomList.create(profile_id=_PROFILE_ID, name="Same Name", existing_count=0)
        mocks = make_collections_uow_mock()
        mock_repo = mocks.custom_lists
        mock_repo.find_by_id.return_value = custom_list
        mock_repo.find_by_name.return_value = custom_list
        mock_repo.update.return_value = custom_list
        use_case = _make_use_case(mocks)

        result = await use_case.execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value,
                list_id=str(custom_list.id),
                name="Same Name",
            )
        )

        assert result.name == "Same Name"
        mock_repo.update.assert_called_once()


_LIMIT = AgeRating(12)
_OTHER_LIBRARY_ID = "lib_other0000001"
_VISIBLE = "mov_visible00001"
_WITHHELD = "mov_withheld0001"
_UNRATED = "ser_unrated00001"
_OTHER_SHELF = "mov_othershelf01"
_REMOVED = "mov_removed00001"


@pytest.mark.unit
class TestRenameCustomListItemCount:
    """The renamed list's ``item_count`` leaves out only titles withheld by age."""

    @staticmethod
    def _seed() -> tuple[CollectionsUoWMocks, CustomList, list[CustomListItem]]:
        items = [
            CustomListItem.create(
                media_id=media_id,
                media_type=MediaType.MOVIE if media_id.startswith("mov_") else MediaType.SERIES,
                position=position,
            )
            for position, media_id in enumerate(
                [_WITHHELD, _VISIBLE, _REMOVED, _OTHER_SHELF, _UNRATED]
            )
        ]
        custom_list = CustomList.create(
            profile_id=_PROFILE_ID, name="Old Name", existing_count=0
        ).with_updates(item_count=len(items))
        mocks = make_collections_uow_mock()
        mocks.custom_lists.find_by_id.return_value = custom_list
        mocks.custom_lists.find_by_name.return_value = None
        mocks.custom_lists.update.side_effect = lambda entity: entity
        mocks.custom_lists.list_items.return_value = items
        return mocks, custom_list, items

    @staticmethod
    def _catalog(
        movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> AsyncMock:
        return make_catalog_lookup_mock(
            movie_summary(_VISIBLE, library_id=MOVIES_LIBRARY_ID, minimum_age=AgeRating(10)),
            movie_summary(_WITHHELD, library_id=MOVIES_LIBRARY_ID, minimum_age=AgeRating(16)),
            series_summary(_UNRATED, library_id=MOVIES_LIBRARY_ID, minimum_age=None),
            movie_summary(_OTHER_SHELF, library_id=_OTHER_LIBRARY_ID, minimum_age=AgeRating(16)),
        )

    @pytest.mark.asyncio
    async def test_should_show_stored_count_without_media_or_item_reads_when_unlimited(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        mocks, custom_list, _ = self._seed()
        catalog = self._catalog(movie_summary, series_summary)

        result = await RenameCustomListUseCase(
            uow_factory=mocks.factory,
            media_lookup=catalog,
            profile_viewing_policy=make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID),
        ).execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value, list_id=str(custom_list.id), name="New Name"
            )
        )

        assert result.item_count == 5
        catalog.find_visible_titles.assert_not_awaited()
        catalog.get_many.assert_not_awaited()
        mocks.custom_lists.list_items.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_should_subtract_titles_withheld_by_age_and_agree_with_items_read(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        mocks, custom_list, _ = self._seed()
        catalog = self._catalog(movie_summary, series_summary)
        policy = make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT)

        result = await RenameCustomListUseCase(
            uow_factory=mocks.factory, media_lookup=catalog, profile_viewing_policy=policy
        ).execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value, list_id=str(custom_list.id), name="New Name"
            )
        )
        read = await GetCustomListItemsUseCase(
            uow_factory=mocks.factory,
            media_lookup=catalog,
            progress_lookup=make_progress_lookup_mock(),
            profile_viewing_policy=policy,
        ).execute(
            GetCustomListItemsInput(profile_id=_PROFILE_ID.value, list_id=str(custom_list.id))
        )

        # 5 stored; the 16 and the unrated title in reach are withheld; the
        # 16 on another shelf is hidden by library, the removed one is gone.
        assert result.name == "New Name"
        assert result.item_count == 3
        assert result.item_count - len(read.items) - read.hidden_count == 1
        mocks.custom_lists.list_items.assert_any_await(str(custom_list.id), _PROFILE_ID)
        assert catalog.find_visible_titles.await_count == 2

    @pytest.mark.asyncio
    async def test_should_read_the_policy_before_and_the_catalog_after_the_transaction(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        mocks, custom_list, _ = self._seed()
        policy = make_profile_viewing_policy_mock(MOVIES_LIBRARY_ID, maturity_limit=_LIMIT)
        manager = Mock()
        manager.attach_mock(policy.find_for_profile, "find_for_profile")
        manager.attach_mock(mocks.factory, "uow_factory")
        catalog = self._catalog(movie_summary, series_summary)
        answer = catalog.find_visible_titles.side_effect

        async def after_the_transaction(**kwargs: object) -> frozenset[str]:
            mocks.uow.__aexit__.assert_awaited_once()  # type: ignore[attr-defined]
            return await answer(**kwargs)

        catalog.find_visible_titles.side_effect = after_the_transaction

        result = await RenameCustomListUseCase(
            uow_factory=mocks.factory, media_lookup=catalog, profile_viewing_policy=policy
        ).execute(
            RenameCustomListInput(
                profile_id=_PROFILE_ID.value, list_id=str(custom_list.id), name="New Name"
            )
        )

        assert result.item_count == 3
        assert catalog.find_visible_titles.await_count == 2
        assert manager.mock_calls[0] == call.find_for_profile(_PROFILE_ID)
        assert call.uow_factory() in manager.mock_calls[1:]

    @pytest.mark.asyncio
    async def test_should_not_reach_the_catalog_when_the_list_is_not_found(
        self, movie_summary: MediaSummaryFactory, series_summary: MediaSummaryFactory
    ) -> None:
        mocks, _, _ = self._seed()
        mocks.custom_lists.find_by_id.return_value = None
        catalog = self._catalog(movie_summary, series_summary)

        with pytest.raises(ResourceNotFoundException):
            await RenameCustomListUseCase(
                uow_factory=mocks.factory,
                media_lookup=catalog,
                profile_viewing_policy=make_profile_viewing_policy_mock(
                    MOVIES_LIBRARY_ID, maturity_limit=_LIMIT
                ),
            ).execute(
                RenameCustomListInput(
                    profile_id=_PROFILE_ID.value, list_id="lst_nonexistent00", name="New"
                )
            )

        catalog.find_visible_titles.assert_not_awaited()
        mocks.custom_lists.update.assert_not_awaited()

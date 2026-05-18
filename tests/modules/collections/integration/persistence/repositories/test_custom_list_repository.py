"""Integration tests for SQLAlchemyCustomListRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyCustomListRepository,
)
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId

SAMPLE_MOVIE_ID = "mov_abc123def456"
MISSING_LIST_ID = "lst_nonexistent00"
MISSING_ITEM_ID = "mov_notinlist0000"
_PROFILE_ID = ProfileId("prf_test12345678")
_OTHER_PROFILE_ID = ProfileId("prf_otherprofile")


def _create_list(
    name: str = "Test List",
    profile_id: ProfileId = _PROFILE_ID,
) -> CustomList:
    return CustomList.create(profile_id=profile_id, name=name)


def _create_item(
    media_id: str = SAMPLE_MOVIE_ID,
    media_type: CollectionMediaType = CollectionMediaType.MOVIE,
    position: int = 0,
) -> CustomListItem:
    return CustomListItem.create(
        media_id=media_id,
        media_type=media_type,
        position=position,
    )


@pytest.mark.integration
class TestSQLAlchemyCustomListRepositoryCRUD:
    """Tests for custom list CRUD operations."""

    async def test_add_should_persist_new_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="Action Movies")

        saved = await repo.add(custom_list)

        assert saved.id == custom_list.id
        assert saved.name.value == "Action Movies"
        assert saved.item_count == 0
        assert saved.profile_id == _PROFILE_ID

    async def test_find_by_id_should_return_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="Comedy")
        await repo.add(custom_list)

        found = await repo.find_by_id(str(custom_list.id), _PROFILE_ID)

        assert found is not None
        assert found.id == custom_list.id
        assert found.name.value == "Comedy"

    async def test_find_by_id_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_by_id(MISSING_LIST_ID, _PROFILE_ID)

        assert found is None

    async def test_find_by_id_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(name="Owned", profile_id=_PROFILE_ID)
        await repo.add(owner_list)

        other_view = await repo.find_by_id(str(owner_list.id), _OTHER_PROFILE_ID)

        assert other_view is None

    async def test_find_by_name_should_be_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Action Movies"))

        found = await repo.find_by_name("action movies", _PROFILE_ID)

        assert found is not None
        assert found.name.value == "Action Movies"

    async def test_find_by_name_should_strip_whitespace(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Action"))

        found = await repo.find_by_name("  Action  ", _PROFILE_ID)

        assert found is not None

    async def test_find_by_name_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_by_name("nonexistent", _PROFILE_ID)

        assert found is None

    async def test_find_by_name_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        # Same name in two profiles must not collide.
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Shared", profile_id=_PROFILE_ID))
        await repo.add(_create_list(name="Shared", profile_id=_OTHER_PROFILE_ID))

        owner_view = await repo.find_by_name("Shared", _PROFILE_ID)
        other_view = await repo.find_by_name("Shared", _OTHER_PROFILE_ID)

        assert owner_view is not None
        assert other_view is not None
        assert owner_view.profile_id == _PROFILE_ID
        assert other_view.profile_id == _OTHER_PROFILE_ID
        assert owner_view.id != other_view.id

    async def test_update_should_persist_changes(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="Original")
        await repo.add(custom_list)

        renamed = custom_list.rename("Renamed")
        updated = await repo.update(renamed)

        assert updated.name.value == "Renamed"

        found = await repo.find_by_id(str(custom_list.id), _PROFILE_ID)
        assert found is not None
        assert found.name.value == "Renamed"

    async def test_update_should_raise_when_list_not_found(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()

        with pytest.raises(ValueError, match="not found for update"):
            await repo.update(custom_list)

    async def test_remove_should_soft_delete(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="To Delete")
        await repo.add(custom_list)

        removed = await repo.remove(str(custom_list.id), _PROFILE_ID)

        assert removed is True
        found = await repo.find_by_id(str(custom_list.id), _PROFILE_ID)
        assert found is None

    async def test_remove_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        removed = await repo.remove(MISSING_LIST_ID, _PROFILE_ID)

        assert removed is False

    async def test_remove_should_not_touch_other_profiles_list(
        self, db_session: AsyncSession
    ) -> None:
        # A profile cannot delete another profile's list, even with its id.
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(name="Owned", profile_id=_PROFILE_ID)
        await repo.add(owner_list)

        removed = await repo.remove(str(owner_list.id), _OTHER_PROFILE_ID)

        assert removed is False
        # Original owner can still see it.
        still_there = await repo.find_by_id(str(owner_list.id), _PROFILE_ID)
        assert still_there is not None

    async def test_list_all_should_return_all_lists(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="A"))
        await repo.add(_create_list(name="B"))
        await repo.add(_create_list(name="C"))

        result = await repo.list_all(_PROFILE_ID)

        assert len(result) == 3
        names = {c.name.value for c in result}
        assert names == {"A", "B", "C"}

    async def test_list_all_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        active = _create_list(name="Active")
        deleted = _create_list(name="Deleted")
        await repo.add(active)
        await repo.add(deleted)
        await repo.remove(str(deleted.id), _PROFILE_ID)

        result = await repo.list_all(_PROFILE_ID)

        assert len(result) == 1
        assert result[0].name.value == "Active"

    async def test_list_all_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Mine", profile_id=_PROFILE_ID))
        await repo.add(_create_list(name="Theirs", profile_id=_OTHER_PROFILE_ID))

        owner_view = await repo.list_all(_PROFILE_ID)
        other_view = await repo.list_all(_OTHER_PROFILE_ID)

        assert {c.name.value for c in owner_view} == {"Mine"}
        assert {c.name.value for c in other_view} == {"Theirs"}

    async def test_count_should_return_active_lists(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="A"))
        await repo.add(_create_list(name="B"))

        count = await repo.count(_PROFILE_ID)

        assert count == 2

    async def test_count_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        deleted = _create_list(name="Deleted")
        await repo.add(_create_list(name="Active"))
        await repo.add(deleted)
        await repo.remove(str(deleted.id), _PROFILE_ID)

        count = await repo.count(_PROFILE_ID)

        assert count == 1

    async def test_count_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="A", profile_id=_PROFILE_ID))
        await repo.add(_create_list(name="B", profile_id=_PROFILE_ID))
        await repo.add(_create_list(name="C", profile_id=_OTHER_PROFILE_ID))

        owner_count = await repo.count(_PROFILE_ID)
        other_count = await repo.count(_OTHER_PROFILE_ID)

        assert owner_count == 2
        assert other_count == 1


@pytest.mark.integration
class TestSQLAlchemyCustomListRepositoryItems:
    """Tests for custom list item management."""

    async def test_add_item_should_persist(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item()

        saved = await repo.add_item(str(custom_list.id), item, _PROFILE_ID)

        assert saved.media_id == item.media_id

    async def test_add_item_should_raise_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        item = _create_item()

        with pytest.raises(ValueError, match="not found"):
            await repo.add_item(MISSING_LIST_ID, item, _PROFILE_ID)

    async def test_add_item_should_raise_when_list_belongs_to_other_profile(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(profile_id=_PROFILE_ID)
        await repo.add(owner_list)
        item = _create_item()

        with pytest.raises(ValueError, match="not found"):
            await repo.add_item(str(owner_list.id), item, _OTHER_PROFILE_ID)

    async def test_find_item_should_return_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add_item(str(custom_list.id), item, _PROFILE_ID)

        found = await repo.find_item(str(custom_list.id), SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_item_should_return_none_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_item(MISSING_LIST_ID, SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert found is None

    async def test_find_item_should_return_none_when_item_not_in_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        found = await repo.find_item(str(custom_list.id), MISSING_ITEM_ID, _PROFILE_ID)

        assert found is None

    async def test_find_item_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(profile_id=_PROFILE_ID)
        await repo.add(owner_list)
        await repo.add_item(str(owner_list.id), _create_item(), _PROFILE_ID)

        # Another profile can't see the item even with the right list_id.
        found = await repo.find_item(str(owner_list.id), SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID)

        assert found is None

    async def test_remove_item_should_soft_delete(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add_item(str(custom_list.id), item, _PROFILE_ID)

        removed = await repo.remove_item(str(custom_list.id), SAMPLE_MOVIE_ID, _PROFILE_ID)

        assert removed is True
        found = await repo.find_item(str(custom_list.id), SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert found is None

    async def test_remove_item_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        removed = await repo.remove_item(str(custom_list.id), MISSING_ITEM_ID, _PROFILE_ID)

        assert removed is False

    async def test_remove_item_should_not_touch_other_profiles_item(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(profile_id=_PROFILE_ID)
        await repo.add(owner_list)
        await repo.add_item(str(owner_list.id), _create_item(), _PROFILE_ID)

        removed = await repo.remove_item(str(owner_list.id), SAMPLE_MOVIE_ID, _OTHER_PROFILE_ID)

        assert removed is False
        # Original owner still sees it.
        still_there = await repo.find_item(str(owner_list.id), SAMPLE_MOVIE_ID, _PROFILE_ID)
        assert still_there is not None

    async def test_list_items_should_return_items_ordered_by_position(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_third0000000", position=2),
            _PROFILE_ID,
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_first0000000", position=0),
            _PROFILE_ID,
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_second000000", position=1),
            _PROFILE_ID,
        )

        items = await repo.list_items(str(custom_list.id), _PROFILE_ID)

        assert [item.media_id for item in items] == [
            "mov_first0000000",
            "mov_second000000",
            "mov_third0000000",
        ]

    async def test_list_items_should_return_empty_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        items = await repo.list_items(MISSING_LIST_ID, _PROFILE_ID)

        assert items == []

    async def test_list_items_should_isolate_by_profile(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owner_list = _create_list(profile_id=_PROFILE_ID)
        await repo.add(owner_list)
        await repo.add_item(str(owner_list.id), _create_item(), _PROFILE_ID)

        other_view = await repo.list_items(str(owner_list.id), _OTHER_PROFILE_ID)

        assert other_view == []

    async def test_get_next_position_should_return_zero_when_empty(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        position = await repo.get_next_position(str(custom_list.id), _PROFILE_ID)

        assert position == 0

    async def test_get_next_position_should_increment_max(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_first0000000", position=0),
            _PROFILE_ID,
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_second000000", position=1),
            _PROFILE_ID,
        )

        position = await repo.get_next_position(str(custom_list.id), _PROFILE_ID)

        assert position == 2

    async def test_get_next_position_should_return_zero_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        position = await repo.get_next_position(MISSING_LIST_ID, _PROFILE_ID)

        assert position == 0

    async def test_add_item_should_restore_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        original_item = _create_item(media_id=SAMPLE_MOVIE_ID, position=0)
        await repo.add_item(str(custom_list.id), original_item, _PROFILE_ID)
        await repo.remove_item(str(custom_list.id), SAMPLE_MOVIE_ID, _PROFILE_ID)

        new_item = _create_item(media_id=SAMPLE_MOVIE_ID, position=5)
        restored = await repo.add_item(str(custom_list.id), new_item, _PROFILE_ID)

        assert restored.media_id == SAMPLE_MOVIE_ID
        assert restored.position == 5


@pytest.mark.integration
class TestSQLAlchemyCustomListRepositoryDeleteAllForProfiles:
    """``delete_all_for_profiles`` — user-delete cascade."""

    async def test_should_soft_delete_lists_and_items_for_listed_profiles(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        owned = _create_list(name="Owned", profile_id=_PROFILE_ID)
        kept = _create_list(name="Kept", profile_id=_OTHER_PROFILE_ID)
        await repo.add(owned)
        await repo.add(kept)
        await repo.add_item(str(owned.id), _create_item(media_id=SAMPLE_MOVIE_ID), _PROFILE_ID)
        await repo.add_item(
            str(kept.id),
            _create_item(media_id=SAMPLE_MOVIE_ID),
            _OTHER_PROFILE_ID,
        )

        deleted = await repo.delete_all_for_profiles([_PROFILE_ID.value])

        assert deleted == 1
        assert await repo.find_by_id(str(owned.id), _PROFILE_ID) is None
        assert await repo.find_by_id(str(kept.id), _OTHER_PROFILE_ID) is not None
        # Items under the soft-deleted list are gone too.
        items = await repo.list_items(str(owned.id), _PROFILE_ID)
        assert items == []

    async def test_should_be_noop_on_empty_profile_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Owned"))

        deleted = await repo.delete_all_for_profiles([])

        assert deleted == 0

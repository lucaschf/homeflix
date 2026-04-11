"""Integration tests for SQLAlchemyCustomListRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.infrastructure.persistence.repositories import (
    SQLAlchemyCustomListRepository,
)
from src.shared_kernel.value_objects import CollectionMediaType

SAMPLE_MOVIE_ID = "mov_abc123def456"
MISSING_LIST_ID = "lst_nonexistent00"
MISSING_ITEM_ID = "mov_notinlist0000"


def _create_list(name: str = "Test List") -> CustomList:
    return CustomList.create(name=name)


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

    async def test_find_by_id_should_return_list(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="Comedy")
        await repo.add(custom_list)

        found = await repo.find_by_id(str(custom_list.id))

        assert found is not None
        assert found.id == custom_list.id
        assert found.name.value == "Comedy"

    async def test_find_by_id_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_by_id(MISSING_LIST_ID)

        assert found is None

    async def test_find_by_name_should_be_case_insensitive(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Action Movies"))

        found = await repo.find_by_name("action movies")

        assert found is not None
        assert found.name.value == "Action Movies"

    async def test_find_by_name_should_strip_whitespace(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="Action"))

        found = await repo.find_by_name("  Action  ")

        assert found is not None

    async def test_find_by_name_should_return_none_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_by_name("nonexistent")

        assert found is None

    async def test_update_should_persist_changes(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list(name="Original")
        await repo.add(custom_list)

        renamed = custom_list.rename("Renamed")
        updated = await repo.update(renamed)

        assert updated.name.value == "Renamed"

        found = await repo.find_by_id(str(custom_list.id))
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

        removed = await repo.remove(str(custom_list.id))

        assert removed is True
        found = await repo.find_by_id(str(custom_list.id))
        assert found is None

    async def test_remove_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        removed = await repo.remove(MISSING_LIST_ID)

        assert removed is False

    async def test_list_all_should_return_all_lists(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="A"))
        await repo.add(_create_list(name="B"))
        await repo.add(_create_list(name="C"))

        result = await repo.list_all()

        assert len(result) == 3
        names = {c.name.value for c in result}
        assert names == {"A", "B", "C"}

    async def test_list_all_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        active = _create_list(name="Active")
        deleted = _create_list(name="Deleted")
        await repo.add(active)
        await repo.add(deleted)
        await repo.remove(str(deleted.id))

        result = await repo.list_all()

        assert len(result) == 1
        assert result[0].name.value == "Active"

    async def test_count_should_return_active_lists(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        await repo.add(_create_list(name="A"))
        await repo.add(_create_list(name="B"))

        count = await repo.count()

        assert count == 2

    async def test_count_should_exclude_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        deleted = _create_list(name="Deleted")
        await repo.add(_create_list(name="Active"))
        await repo.add(deleted)
        await repo.remove(str(deleted.id))

        count = await repo.count()

        assert count == 1


@pytest.mark.integration
class TestSQLAlchemyCustomListRepositoryItems:
    """Tests for custom list item management."""

    async def test_add_item_should_persist(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item()

        saved = await repo.add_item(str(custom_list.id), item)

        assert saved.media_id == item.media_id

    async def test_add_item_should_raise_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        item = _create_item()

        with pytest.raises(ValueError, match="not found"):
            await repo.add_item(MISSING_LIST_ID, item)

    async def test_find_item_should_return_item(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add_item(str(custom_list.id), item)

        found = await repo.find_item(str(custom_list.id), SAMPLE_MOVIE_ID)

        assert found is not None
        assert found.media_id == SAMPLE_MOVIE_ID

    async def test_find_item_should_return_none_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        found = await repo.find_item(MISSING_LIST_ID, SAMPLE_MOVIE_ID)

        assert found is None

    async def test_find_item_should_return_none_when_item_not_in_list(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        found = await repo.find_item(str(custom_list.id), MISSING_ITEM_ID)

        assert found is None

    async def test_remove_item_should_soft_delete(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        item = _create_item(media_id=SAMPLE_MOVIE_ID)
        await repo.add_item(str(custom_list.id), item)

        removed = await repo.remove_item(str(custom_list.id), SAMPLE_MOVIE_ID)

        assert removed is True
        found = await repo.find_item(str(custom_list.id), SAMPLE_MOVIE_ID)
        assert found is None

    async def test_remove_item_should_return_false_when_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        removed = await repo.remove_item(str(custom_list.id), MISSING_ITEM_ID)

        assert removed is False

    async def test_list_items_should_return_items_ordered_by_position(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_third0000000", position=2),
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_first0000000", position=0),
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_second000000", position=1),
        )

        items = await repo.list_items(str(custom_list.id))

        assert [item.media_id for item in items] == [
            "mov_first0000000",
            "mov_second000000",
            "mov_third0000000",
        ]

    async def test_list_items_should_return_empty_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        items = await repo.list_items(MISSING_LIST_ID)

        assert items == []

    async def test_get_next_position_should_return_zero_when_empty(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)

        position = await repo.get_next_position(str(custom_list.id))

        assert position == 0

    async def test_get_next_position_should_increment_max(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_first0000000", position=0),
        )
        await repo.add_item(
            str(custom_list.id),
            _create_item(media_id="mov_second000000", position=1),
        )

        position = await repo.get_next_position(str(custom_list.id))

        assert position == 2

    async def test_get_next_position_should_return_zero_when_list_not_found(
        self, db_session: AsyncSession
    ) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)

        position = await repo.get_next_position(MISSING_LIST_ID)

        assert position == 0

    async def test_add_item_should_restore_soft_deleted(self, db_session: AsyncSession) -> None:
        repo = SQLAlchemyCustomListRepository(db_session)
        custom_list = _create_list()
        await repo.add(custom_list)
        original_item = _create_item(media_id=SAMPLE_MOVIE_ID, position=0)
        await repo.add_item(str(custom_list.id), original_item)
        await repo.remove_item(str(custom_list.id), SAMPLE_MOVIE_ID)

        new_item = _create_item(media_id=SAMPLE_MOVIE_ID, position=5)
        restored = await repo.add_item(str(custom_list.id), new_item)

        assert restored.media_id == SAMPLE_MOVIE_ID
        assert restored.position == 5

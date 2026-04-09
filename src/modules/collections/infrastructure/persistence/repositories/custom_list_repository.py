"""SQLAlchemy implementation of CustomListRepository."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.repositories import CustomListRepository
from src.modules.collections.infrastructure.persistence.mappers import (
    CustomListItemMapper,
    CustomListMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
)


class SQLAlchemyCustomListRepository(CustomListRepository):
    """SQLAlchemy implementation of CustomListRepository.

    Example:
        >>> repo = SQLAlchemyCustomListRepository(session)
        >>> lists = await repo.list_all()
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    # -- List CRUD -------------------------------------------------------------

    async def find_by_id(self, list_id: str) -> CustomList | None:
        """Find a custom list by its external ID."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == list_id,
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListMapper.to_entity(model)

    async def find_by_name(self, name: str) -> CustomList | None:
        """Find a custom list by name (case-insensitive)."""
        stmt = select(CustomListModel).where(
            func.lower(CustomListModel.name) == name.strip().lower(),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListMapper.to_entity(model)

    async def add(self, custom_list: CustomList) -> CustomList:
        """Persist a new custom list."""
        model = CustomListMapper.to_model(custom_list)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return CustomListMapper.to_entity(model)

    async def update(self, custom_list: CustomList) -> CustomList:
        """Update an existing custom list."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == str(custom_list.id),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            msg = f"CustomList {custom_list.id} not found for update"
            raise ValueError(msg)

        CustomListMapper.update_model(model, custom_list)
        await self._session.commit()
        await self._session.refresh(model)
        return CustomListMapper.to_entity(model)

    async def remove(self, list_id: str) -> bool:
        """Soft-delete a custom list and all its items."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == list_id,
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        # Soft-delete all items in the list
        items_stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == model.id,
            CustomListItemModel.deleted_at.is_(None),
        )
        items_result = await self._session.execute(items_stmt)
        for item_model in items_result.scalars().all():
            item_model.soft_delete()

        model.soft_delete()
        await self._session.commit()
        return True

    async def list_all(self) -> list[CustomList]:
        """List all custom lists ordered by most recently updated."""
        stmt = (
            select(CustomListModel)
            .where(CustomListModel.deleted_at.is_(None))
            .order_by(CustomListModel.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return [CustomListMapper.to_entity(m) for m in result.scalars().all()]

    async def count(self) -> int:
        """Count total active custom lists."""
        stmt = (
            select(func.count())
            .select_from(CustomListModel)
            .where(CustomListModel.deleted_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # -- Item management -------------------------------------------------------

    async def _get_list_internal_id(self, list_id: str) -> int | None:
        """Get the internal DB ID for a custom list by external ID.

        Args:
            list_id: External ID of the list.

        Returns:
            Internal ID if found, None otherwise.
        """
        stmt = select(CustomListModel.id).where(
            CustomListModel.external_id == list_id,
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_item(self, list_id: str, media_id: str) -> CustomListItem | None:
        """Find an item in a custom list."""
        internal_id = await self._get_list_internal_id(list_id)
        if internal_id is None:
            return None

        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == media_id,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListItemMapper.to_entity(model)

    async def add_item(self, list_id: str, item: CustomListItem) -> CustomListItem:
        """Add an item to a custom list."""
        internal_id = await self._get_list_internal_id(list_id)
        if internal_id is None:
            msg = f"CustomList {list_id} not found"
            raise ValueError(msg)

        # Check for soft-deleted record to restore
        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == item.media_id,
            CustomListItemModel.deleted_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.restore()
            existing.position = item.position
            existing.added_at = item.added_at
            await self._session.commit()
            await self._session.refresh(existing)
            return CustomListItemMapper.to_entity(existing)

        model = CustomListItemMapper.to_model(item, list_internal_id=internal_id)
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return CustomListItemMapper.to_entity(model)

    async def remove_item(self, list_id: str, media_id: str) -> bool:
        """Remove an item from a custom list."""
        internal_id = await self._get_list_internal_id(list_id)
        if internal_id is None:
            return False

        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == media_id,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.commit()
        return True

    async def list_items(self, list_id: str) -> list[CustomListItem]:
        """List all items in a custom list ordered by position."""
        internal_id = await self._get_list_internal_id(list_id)
        if internal_id is None:
            return []

        stmt = (
            select(CustomListItemModel)
            .where(
                CustomListItemModel.custom_list_id == internal_id,
                CustomListItemModel.deleted_at.is_(None),
            )
            .order_by(CustomListItemModel.position.asc())
        )
        result = await self._session.execute(stmt)
        return [CustomListItemMapper.to_entity(m) for m in result.scalars().all()]

    async def get_next_position(self, list_id: str) -> int:
        """Get the next available position via DB MAX query."""
        internal_id = await self._get_list_internal_id(list_id)
        if internal_id is None:
            return 0

        stmt = select(func.coalesce(func.max(CustomListItemModel.position), -1) + 1).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0


__all__ = ["SQLAlchemyCustomListRepository"]

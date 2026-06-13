"""SQLAlchemy implementation of CustomListRepository."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import CustomList, CustomListItem
from src.modules.collections.domain.repositories import CustomListRepository
from src.modules.collections.domain.value_objects import CollectionMediaId
from src.modules.collections.infrastructure.persistence.mappers import (
    CustomListItemMapper,
    CustomListMapper,
)
from src.modules.collections.infrastructure.persistence.models import (
    CustomListItemModel,
    CustomListModel,
)
from src.shared_kernel.value_objects import CollectionMediaType
from src.shared_kernel.value_objects.profile_id import ProfileId


class SQLAlchemyCustomListRepository(CustomListRepository):
    """SQLAlchemy implementation of CustomListRepository.

    Every read/delete query is scoped by ``profile_id`` so a profile
    can never see (or accidentally mutate) another profile's lists,
    even when armed with a known ``list_id``. ``add``/``update`` derive
    the profile from the entity, matching the contract.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- List CRUD -------------------------------------------------------------

    async def find_by_id(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> CustomList | None:
        """Find a non-deleted list owned by ``profile_id``."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == list_id,
            CustomListModel.profile_id == str(profile_id),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListMapper.to_entity(model)

    async def find_by_name(
        self,
        name: str,
        profile_id: ProfileId,
    ) -> CustomList | None:
        """Find by name (case-insensitive) within the profile."""
        stmt = select(CustomListModel).where(
            func.lower(CustomListModel.name) == name.strip().lower(),
            CustomListModel.profile_id == str(profile_id),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListMapper.to_entity(model)

    async def add(self, custom_list: CustomList) -> CustomList:
        """Persist a new custom list."""
        model = CustomListMapper.to_model(custom_list)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return CustomListMapper.to_entity(model)

    async def update(self, custom_list: CustomList) -> CustomList:
        """Update an existing custom list (scoped to its own profile)."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == str(custom_list.id),
            CustomListModel.profile_id == str(custom_list.profile_id),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            msg = f"CustomList {custom_list.id} not found for update"
            raise ValueError(msg)

        CustomListMapper.update_model(model, custom_list)
        await self._session.flush()
        await self._session.refresh(model)
        return CustomListMapper.to_entity(model)

    async def remove(self, list_id: str, profile_id: ProfileId) -> bool:
        """Soft-delete a list and its items, scoped to ``profile_id``."""
        stmt = select(CustomListModel).where(
            CustomListModel.external_id == list_id,
            CustomListModel.profile_id == str(profile_id),
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
        await self._session.flush()
        return True

    async def list_all(self, profile_id: ProfileId) -> list[CustomList]:
        """List the profile's custom lists ordered by most recently updated."""
        stmt = (
            select(CustomListModel)
            .where(
                CustomListModel.profile_id == str(profile_id),
                CustomListModel.deleted_at.is_(None),
            )
            .order_by(CustomListModel.updated_at.desc())
        )
        result = await self._session.execute(stmt)
        return [CustomListMapper.to_entity(m) for m in result.scalars().all()]

    async def count(self, profile_id: ProfileId) -> int:
        """Count active custom lists for the profile."""
        stmt = (
            select(func.count())
            .select_from(CustomListModel)
            .where(
                CustomListModel.profile_id == str(profile_id),
                CustomListModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # -- Item management -------------------------------------------------------

    async def _get_list_internal_id(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> int | None:
        """Resolve internal DB id, scoped to the owning profile."""
        stmt = select(CustomListModel.id).where(
            CustomListModel.external_id == list_id,
            CustomListModel.profile_id == str(profile_id),
            CustomListModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_item(
        self,
        list_id: str,
        media_id: CollectionMediaId,
        profile_id: ProfileId,
    ) -> CustomListItem | None:
        """Find an item, only if the parent list belongs to the profile."""
        internal_id = await self._get_list_internal_id(list_id, profile_id)
        if internal_id is None:
            return None

        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == media_id.value,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else CustomListItemMapper.to_entity(model)

    async def add_item(
        self,
        list_id: str,
        item: CustomListItem,
        profile_id: ProfileId,
    ) -> CustomListItem:
        """Persist an item under a list owned by ``profile_id``."""
        internal_id = await self._get_list_internal_id(list_id, profile_id)
        if internal_id is None:
            msg = f"CustomList {list_id} not found"
            raise ValueError(msg)

        # Check for soft-deleted record to restore
        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == item.media_id.value,
            CustomListItemModel.deleted_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.restore()
            existing.position = item.position
            existing.added_at = item.added_at
            await self._session.flush()
            await self._session.refresh(existing)
            return CustomListItemMapper.to_entity(existing)

        model = CustomListItemMapper.to_model(item, list_internal_id=internal_id)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return CustomListItemMapper.to_entity(model)

    async def remove_item(
        self,
        list_id: str,
        media_id: CollectionMediaId,
        profile_id: ProfileId,
    ) -> bool:
        """Soft-delete an item from a list owned by ``profile_id``."""
        internal_id = await self._get_list_internal_id(list_id, profile_id)
        if internal_id is None:
            return False

        stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.media_id == media_id.value,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            return False

        model.soft_delete()
        await self._session.flush()
        return True

    async def list_items(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> list[CustomListItem]:
        """List items in a list, scoped to the owning profile."""
        internal_id = await self._get_list_internal_id(list_id, profile_id)
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

    async def get_next_position(
        self,
        list_id: str,
        profile_id: ProfileId,
    ) -> int:
        """Compute next position via MAX query, scoped to the owning profile."""
        internal_id = await self._get_list_internal_id(list_id, profile_id)
        if internal_id is None:
            return 0

        stmt = select(func.coalesce(func.max(CustomListItemModel.position), -1) + 1).where(
            CustomListItemModel.custom_list_id == internal_id,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def delete_all_for_profiles(self, profile_ids: list[str]) -> int:
        """Soft-delete every list + items owned by the given profiles."""
        if not profile_ids:
            return 0
        list_stmt = select(CustomListModel).where(
            CustomListModel.profile_id.in_(profile_ids),
            CustomListModel.deleted_at.is_(None),
        )
        list_result = await self._session.execute(list_stmt)
        list_models = list_result.scalars().all()
        if not list_models:
            return 0
        list_internal_ids = [m.id for m in list_models]
        item_stmt = select(CustomListItemModel).where(
            CustomListItemModel.custom_list_id.in_(list_internal_ids),
            CustomListItemModel.deleted_at.is_(None),
        )
        item_result = await self._session.execute(item_stmt)
        item_models = item_result.scalars().all()
        for item in item_models:
            item.soft_delete()
        for lst in list_models:
            lst.soft_delete()
        await self._session.flush()
        return len(list_models)

    async def rewrite_item_media_id(
        self,
        from_media_id: CollectionMediaId,
        to_media_id: CollectionMediaId,
        to_media_type: CollectionMediaType,
    ) -> int:
        """Repoint every list item (cross-list, cross-profile) to a new media id."""
        stmt = select(CustomListItemModel).where(
            CustomListItemModel.media_id == from_media_id.value,
            CustomListItemModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.media_id = to_media_id.value
            model.media_type = to_media_type.value
        if models:
            await self._session.flush()
        return len(models)


__all__ = ["SQLAlchemyCustomListRepository"]

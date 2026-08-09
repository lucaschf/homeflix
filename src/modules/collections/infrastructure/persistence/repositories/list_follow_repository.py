"""SQLAlchemy implementation of ``ListFollowRepository``."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.collections.domain.entities import ListFollow
from src.modules.collections.domain.repositories import ListFollowRepository
from src.modules.collections.domain.value_objects import ListId
from src.modules.collections.infrastructure.persistence.mappers import ListFollowMapper
from src.modules.collections.infrastructure.persistence.models import ListFollowModel
from src.shared_kernel.value_objects.profile_id import ProfileId


class SQLAlchemyListFollowRepository(ListFollowRepository):
    """SQLAlchemy implementation of ``ListFollowRepository``.

    Every query filters out soft-deleted rows so an unfollowed row
    never resurfaces. The ``(follower_profile_id, list_id)`` natural
    key drives the idempotent find/remove.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, follow: ListFollow) -> ListFollow:
        """Persist a new follow, restoring a soft-deleted row if present."""
        # Reuse a prior soft-deleted follow so re-following the same
        # list doesn't accumulate dead rows (mirrors ``add_item``).
        stmt = select(ListFollowModel).where(
            ListFollowModel.follower_profile_id == str(follow.follower_profile_id),
            ListFollowModel.list_id == str(follow.list_id),
            ListFollowModel.deleted_at.is_not(None),
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.restore()
            await self._session.flush()
            await self._session.refresh(existing)
            return ListFollowMapper.to_entity(existing)

        model = ListFollowMapper.to_model(follow)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ListFollowMapper.to_entity(model)

    async def find(
        self,
        follower_profile_id: ProfileId,
        list_id: ListId,
    ) -> ListFollow | None:
        """Look up a single live follow by its natural key."""
        stmt = select(ListFollowModel).where(
            ListFollowModel.follower_profile_id == str(follower_profile_id),
            ListFollowModel.list_id == str(list_id),
            ListFollowModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else ListFollowMapper.to_entity(model)

    async def remove(
        self,
        follower_profile_id: ProfileId,
        list_id: ListId,
    ) -> bool:
        """Soft-delete a follow by its natural key (unfollow)."""
        stmt = select(ListFollowModel).where(
            ListFollowModel.follower_profile_id == str(follower_profile_id),
            ListFollowModel.list_id == str(list_id),
            ListFollowModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return False
        model.soft_delete()
        await self._session.flush()
        return True

    async def list_for_follower(self, follower_profile_id: ProfileId) -> list[ListFollow]:
        """List every live follow owned by ``follower_profile_id``."""
        stmt = (
            select(ListFollowModel)
            .where(
                ListFollowModel.follower_profile_id == str(follower_profile_id),
                ListFollowModel.deleted_at.is_(None),
            )
            .order_by(ListFollowModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [ListFollowMapper.to_entity(m) for m in result.scalars().all()]

    async def remove_all_for_list(self, list_id: ListId) -> int:
        """Soft-delete every live follow of a single list."""
        stmt = select(ListFollowModel).where(
            ListFollowModel.list_id == str(list_id),
            ListFollowModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)

    async def delete_all_for_followers(self, follower_profile_ids: list[str]) -> int:
        """Soft-delete every live follow made by the given profiles."""
        if not follower_profile_ids:
            return 0
        stmt = select(ListFollowModel).where(
            ListFollowModel.follower_profile_id.in_(follower_profile_ids),
            ListFollowModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        for model in models:
            model.soft_delete()
        if models:
            await self._session.flush()
        return len(models)


__all__ = ["SQLAlchemyListFollowRepository"]

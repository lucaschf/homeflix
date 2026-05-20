"""SQLAlchemy implementation of ``NotificationRepository``."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.repositories import NotificationRepository
from src.modules.notifications.domain.value_objects import NotificationId
from src.modules.notifications.infrastructure.persistence.mappers import NotificationMapper
from src.modules.notifications.infrastructure.persistence.models import NotificationModel


class SQLAlchemyNotificationRepository(NotificationRepository):
    """SQLAlchemy implementation of ``NotificationRepository``.

    Example:
        >>> repo = SQLAlchemyNotificationRepository(session)
        >>> rows = await repo.list_for_user("usr_alice", limit=20)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self._session = session

    async def add(self, notification: Notification) -> Notification:
        """Persist a new notification."""
        model = NotificationMapper.to_model(notification)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return NotificationMapper.to_entity(model)

    async def update(self, notification: Notification) -> Notification:
        """Update an existing notification."""
        stmt = select(NotificationModel).where(
            NotificationModel.external_id == str(notification.id),
            NotificationModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            msg = f"Notification {notification.id} not found for update"
            raise ValueError(msg)

        NotificationMapper.update_model(model, notification)
        await self._session.flush()
        await self._session.refresh(model)
        return NotificationMapper.to_entity(model)

    async def find_by_id_for_user(
        self,
        notification_id: NotificationId,
        recipient_user_id: str,
    ) -> Notification | None:
        """Look up a notification scoped to its owner."""
        stmt = select(NotificationModel).where(
            NotificationModel.external_id == str(notification_id),
            NotificationModel.recipient_user_id == recipient_user_id,
            NotificationModel.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return None if model is None else NotificationMapper.to_entity(model)

    async def list_for_user(
        self,
        recipient_user_id: str,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[Notification]:
        """List notifications addressed to a user, newest first."""
        stmt = (
            select(NotificationModel)
            .where(
                NotificationModel.recipient_user_id == recipient_user_id,
                NotificationModel.deleted_at.is_(None),
            )
            .order_by(NotificationModel.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        result = await self._session.execute(stmt)
        return [NotificationMapper.to_entity(m) for m in result.scalars().all()]

    async def count_unread_for_user(self, recipient_user_id: str) -> int:
        """Return the unread-badge count for a user."""
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.recipient_user_id == recipient_user_id,
                NotificationModel.read_at.is_(None),
                NotificationModel.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)


__all__ = ["SQLAlchemyNotificationRepository"]

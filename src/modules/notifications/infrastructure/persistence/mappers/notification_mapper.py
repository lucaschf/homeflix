"""Mapper between ``Notification`` entity and ``NotificationModel``."""

from src.modules.notifications.domain.entities import Notification
from src.modules.notifications.domain.value_objects import (
    NotificationId,
    NotificationKind,
)
from src.modules.notifications.infrastructure.persistence.models import NotificationModel


class NotificationMapper:
    """Bidirectional mapper between domain aggregate and ORM model.

    Example:
        >>> model = NotificationMapper.to_model(entity)
        >>> entity = NotificationMapper.to_entity(model)
    """

    @staticmethod
    def to_model(entity: Notification) -> NotificationModel:
        """Convert ``Notification`` entity to ORM model.

        Args:
            entity: The domain aggregate. Must have an ``id``.

        Returns:
            SQLAlchemy model ready for persistence.

        Raises:
            ValueError: When ``entity.id`` is ``None``.
        """
        if entity.id is None:
            msg = "Cannot map entity without ID to model"
            raise ValueError(msg)

        return NotificationModel(
            external_id=str(entity.id),
            recipient_user_id=entity.recipient_user_id.value,
            kind=entity.kind.value,
            title=entity.title,
            body=entity.body,
            payload=dict(entity.payload),
            read_at=entity.read_at,
        )

    @staticmethod
    def to_entity(model: NotificationModel) -> Notification:
        """Convert ORM model to domain aggregate."""
        return Notification(
            id=NotificationId(model.external_id),
            recipient_user_id=model.recipient_user_id,
            kind=NotificationKind(model.kind),
            title=model.title,
            body=model.body,
            payload=dict(model.payload or {}),
            read_at=model.read_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def update_model(
        model: NotificationModel,
        entity: Notification,
    ) -> NotificationModel:
        """Update an existing ORM model with entity data.

        Only ``read_at`` is mutable today — ``recipient_user_id``,
        ``kind``, ``title``, ``body``, and ``payload`` are
        write-once on the create path, so updating them would be
        a bug.
        """
        model.read_at = entity.read_at
        return model


__all__ = ["NotificationMapper"]

"""Notifications bounded context dependency container."""

from dependency_injector import containers, providers

from src.modules.notifications.application.use_cases import (
    CreateNotificationUseCase,
    ListUserNotificationsUseCase,
    MarkNotificationReadUseCase,
)
from src.modules.notifications.infrastructure.acl import NotificationPublisherAdapter
from src.modules.notifications.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyNotificationsUnitOfWorkFactory,
)


class NotificationsContainer(containers.DeclarativeContainer):  # type: ignore[misc]
    """Container for the Notifications bounded context.

    Exposes:
        - The ``NotificationsUnitOfWorkFactory`` used by every use
          case in this BC.
        - Use case providers wired into the ``/notifications`` REST
          routes.
        - The ``NotificationPublisherAdapter`` factory the
          Catalog Requests BC consumes via its
          ``NotificationPublisherPort`` (ADR-009).
    """

    session_factory = providers.Dependency()

    # =========================================================================
    # Unit of Work
    # =========================================================================

    notifications_unit_of_work_factory = providers.Singleton(
        SqlAlchemyNotificationsUnitOfWorkFactory,
        session_factory=session_factory,
    )

    # =========================================================================
    # Use Cases
    # =========================================================================

    create_notification = providers.Factory(
        CreateNotificationUseCase,
        uow_factory=notifications_unit_of_work_factory,
    )

    list_user_notifications = providers.Factory(
        ListUserNotificationsUseCase,
        uow_factory=notifications_unit_of_work_factory,
    )

    mark_notification_read = providers.Factory(
        MarkNotificationReadUseCase,
        uow_factory=notifications_unit_of_work_factory,
    )

    # =========================================================================
    # Anti-corruption layer (cross-BC publisher adapter)
    # =========================================================================

    notification_publisher = providers.Factory(
        NotificationPublisherAdapter,
        create_notification=create_notification,
    )
